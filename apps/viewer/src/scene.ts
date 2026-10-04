import * as THREE from "three";
import type { CustomLight, LightingData, SceneEntity, ScenePackage } from "./types";

/**
 * Source scene packages imply Unity's Y-up, left-handed convention
 * (unenforced by the schema, but ScenePackageMetadata.unity_version /
 * target_platform are always Unity/Android). Three.js is Y-up, right-handed.
 * Flipping the Z axis on every position/waypoint converts between them.
 */
export function toThreeVec3([x, y, z]: [number, number, number]): THREE.Vector3 {
  return new THREE.Vector3(x, y, -z);
}

const ROOM_COLOR = 0x3a3f4b;
const FLOOR_COLOR = 0x22252e;
const POI_COLOR = 0xff6b6b;
const NAV_POINT_COLOR = 0x4ea1ff;

// Bounded label cache: identical labels share one canvas texture AND one
// SpriteMaterial instead of allocating a material per sprite. Entries are
// refcounted: eviction and teardown dispose a texture/material only once no
// live sprite references it — never while still in use.
interface LabelEntry {
  texture: THREE.CanvasTexture;
  material: THREE.SpriteMaterial;
  refs: number;
}
const labelCache = new Map<string, LabelEntry>();
const MAX_LABEL_CACHE = 64;

function makeLabelSprite(text: string): THREE.Sprite {
  let entry = labelCache.get(text);
  if (!entry) {
    if (labelCache.size >= MAX_LABEL_CACHE) {
      // Evict the oldest UNREFERENCED entry. If every entry is still
      // referenced, keep them all (a bounded temporary overrun beats
      // disposing a texture a live sprite is sampling).
      for (const [key, candidate] of labelCache) {
        if (candidate.refs === 0) {
          candidate.texture.dispose();
          candidate.material.dispose();
          labelCache.delete(key);
          break;
        }
      }
    }
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 64;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "rgba(10,10,15,0.75)";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.font = "28px system-ui, sans-serif";
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(text, canvas.width / 2, canvas.height / 2);
    const texture = new THREE.CanvasTexture(canvas);
    entry = { texture, material: new THREE.SpriteMaterial({ map: texture, depthTest: false }), refs: 0 };
    labelCache.set(text, entry);
  }
  entry.refs += 1;
  const sprite = new THREE.Sprite(entry.material);
  sprite.userData.labelKey = text;
  sprite.scale.set(2, 0.5, 1);
  return sprite;
}

/** Releases label sprites under `root` (call on viewer teardown). Shared
 * textures/materials are disposed only when their last referencing sprite
 * is released. */
export function releaseLabelSprites(root: THREE.Object3D): void {
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Sprite)) return;
    const key = (obj.userData as { labelKey?: unknown } | undefined)?.labelKey;
    if (typeof key !== "string") return;
    const entry = labelCache.get(key);
    if (!entry) return;
    entry.refs = Math.max(0, entry.refs - 1);
    if (entry.refs === 0) {
      labelCache.delete(key);
      entry.texture.dispose();
      entry.material.dispose();
    }
  });
}

/** No real GLB assets exist yet (generation is JSON-only by design) - this is
 * the single seam to replace with real asset loading once a GLB pipeline
 * exists. Everything else in the viewer is asset-format agnostic. */
function resolveGeometry(entity: SceneEntity): THREE.Object3D {
  const group = new THREE.Group();
  const props = entity.properties || {};

  switch (entity.type) {
    case "room": {
      const width = Number(props.width) || 4;
      const depth = Number(props.depth) || 4;
      const height = Number(props.height) || 2.7;

      const floor = new THREE.Mesh(
        new THREE.PlaneGeometry(width, depth),
        new THREE.MeshStandardMaterial({ color: FLOOR_COLOR, side: THREE.DoubleSide })
      );
      floor.rotation.x = -Math.PI / 2;
      group.add(floor);

      const shell = new THREE.Mesh(
        new THREE.BoxGeometry(width, height, depth),
        new THREE.MeshStandardMaterial({
          color: ROOM_COLOR,
          wireframe: true,
          transparent: true,
          opacity: 0.35,
        })
      );
      shell.position.y = height / 2;
      group.add(shell);

      group.add(makeLabelSprite(entity.name).translateY(height + 0.5));
      break;
    }
    case "poi": {
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.25, 16, 16),
        new THREE.MeshStandardMaterial({ color: POI_COLOR, emissive: POI_COLOR, emissiveIntensity: 0.4 })
      );
      group.add(marker);
      group.add(makeLabelSprite(entity.name).translateY(0.6));
      break;
    }
    case "navigation_point": {
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(0.1, 8, 8),
        new THREE.MeshBasicMaterial({ color: NAV_POINT_COLOR, transparent: true, opacity: 0.6 })
      );
      group.add(marker);
      break;
    }
    case "door":
    case "window": {
      const box = new THREE.Mesh(
        new THREE.BoxGeometry(1, 2, 0.1),
        new THREE.MeshStandardMaterial({ color: entity.type === "door" ? 0x8b5e3c : 0x87ceeb })
      );
      group.add(box);
      break;
    }
    case "light":
      // Actual light added separately in buildLighting/entity light handling below.
      break;
    default: {
      const box = new THREE.Mesh(
        new THREE.BoxGeometry(0.6, 0.6, 0.6),
        new THREE.MeshStandardMaterial({ color: 0x777777 })
      );
      group.add(box);
    }
  }
  return group;
}

function addEntity(parent: THREE.Object3D, entity: SceneEntity) {
  const obj = resolveGeometry(entity);
  obj.position.copy(toThreeVec3(entity.position));
  if (entity.rotation) {
    const [rx, ry, rz] = entity.rotation;
    // Best-effort handedness approximation: yaw (Y) is the axis that matters
    // most for a walkthrough and is negated to match the Z-flip above; pitch
    ///roll are passed through unconverted since nothing in the schema
    // documents a strict convention to invert against.
    obj.rotation.set(
      THREE.MathUtils.degToRad(rx),
      THREE.MathUtils.degToRad(-ry),
      THREE.MathUtils.degToRad(rz)
    );
  }
  if (entity.scale) obj.scale.set(...entity.scale);
  if (entity.type === "light") {
    const color = new THREE.Color(0xfff4e0);
    const light = new THREE.PointLight(color, 1.0, 20);
    obj.add(light);
  }
  parent.add(obj);
  for (const child of entity.children || []) addEntity(obj, child);
}

function addLighting(scene: THREE.Scene, lighting: LightingData) {
  scene.add(new THREE.AmbientLight(0xffffff, lighting.ambient_intensity ?? 0.5));

  const sunDir = toThreeVec3(lighting.sun_direction ?? [0.5, -1, 0.3]);
  const sun = new THREE.DirectionalLight(0xffffff, 1.0);
  sun.position.copy(sunDir.clone().negate().multiplyScalar(10));
  scene.add(sun);

  for (const custom of lighting.custom_lights || []) {
    scene.add(makeCustomLight(custom));
  }
}

function makeCustomLight(custom: CustomLight): THREE.Light {
  const color = custom.color
    ? new THREE.Color(custom.color[0], custom.color[1], custom.color[2])
    : new THREE.Color(0xffffff);
  const intensity = custom.intensity ?? 1;
  let light: THREE.Light;
  if (custom.type === "spot") {
    light = new THREE.SpotLight(color, intensity, custom.range ?? 20, THREE.MathUtils.degToRad(custom.angle ?? 45));
  } else if (custom.type === "point") {
    light = new THREE.PointLight(color, intensity, custom.range ?? 20);
  } else {
    light = new THREE.DirectionalLight(color, intensity);
  }
  light.position.copy(toThreeVec3(custom.position));
  return light;
}

export function buildScene(pkg: ScenePackage): THREE.Scene {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0a0a0f);

  addLighting(scene, pkg.lighting);

  const root = new THREE.Group();
  for (const entity of pkg.entities) addEntity(root, entity);
  scene.add(root);

  return scene;
}

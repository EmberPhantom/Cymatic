import * as THREE from "three";
import { isLoggedIn, login, logout, tryRestoreSession } from "./auth";
import { fetchSceneForViewing, listPublishedProjects } from "./api";
import { buildScene, releaseLabelSprites } from "./scene";
import { Walkthrough } from "./navigation";
import type { WalkthroughFrame } from "./navigation";
import type { Project } from "./types";

const app = document.getElementById("app")!;

// Active viewer teardown: renderViewer registers its RAF loop, window
// listeners, and GL resources here so the back button (and any screen
// transition) disposes them instead of leaking a second renderer loop.
let activeViewerCleanup: (() => void) | null = null;

function teardownActiveViewer() {
  if (!activeViewerCleanup) return;
  const cleanup = activeViewerCleanup;
  activeViewerCleanup = null;
  try {
    cleanup();
  } catch {
    // Best effort — never break navigation on teardown errors.
  }
}

/** Frees geometries and per-mesh materials of a built scene. Shared label
 * SpriteMaterials are refcounted (see releaseLabelSprites) and never
 * disposed here. */
function disposeSceneResources(scene: THREE.Scene) {
  releaseLabelSprites(scene);
  scene.traverse((obj) => {
    const withGeometry = obj as unknown as { geometry?: { dispose?: () => void } };
    if (withGeometry.geometry && typeof withGeometry.geometry.dispose === "function") {
      withGeometry.geometry.dispose();
    }
    const withMaterial = obj as unknown as { material?: unknown };
    const material = withMaterial.material;
    if (material instanceof THREE.SpriteMaterial) return; // shared, refcounted
    if (Array.isArray(material)) {
      for (const m of material) {
        if (m instanceof THREE.SpriteMaterial) continue;
        (m as THREE.Material).dispose();
      }
    } else if (material instanceof THREE.Material) {
      material.dispose();
    }
  });
}

type ElProps<K extends keyof HTMLElementTagNameMap> = Partial<
  Omit<HTMLElementTagNameMap[K], "style">
> & { style?: string };

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: ElProps<K> = {},
  children: (Node | string)[] = []
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  const { style, ...rest } = props;
  Object.assign(node, rest);
  if (style) node.style.cssText = style;
  for (const child of children) node.append(child);
  return node;
}

function labeledInput(label: string, props: ElProps<"input">): HTMLElement {
  const input = el("input", { ...props, id: `login-${label.toLowerCase().replace(/[^a-z]+/g, "")}` });
  const lab = el("label", {
    textContent: label,
    // Visually tie label to input; screen readers get the association.
    ...( { htmlFor: (input as HTMLInputElement).id } as Record<string, string>),
    style: "font-size:14px;color:#ccc;text-align:left;",
  });
  return el("div", { style: "display:flex;flex-direction:column;gap:4px;" }, [lab, input]);
}

function statusLine(): HTMLParagraphElement {
  const p = el("p", { style: "color:#f66;min-height:1.2em" });
  p.setAttribute("role", "status");
  p.setAttribute("aria-live", "polite");
  return p;
}

function actionButton(text: string, style = ""): HTMLButtonElement {
  return el("button", { textContent: text, style: `min-height:48px;${style}` });
}

function renderLoginScreen() {
  teardownActiveViewer();
  app.innerHTML = "";
  const status = statusLine();
  const emailWrap = labeledInput("Email", { type: "email", placeholder: "Email", autocomplete: "username" });
  const passwordWrap = labeledInput("Password", { type: "password", placeholder: "Password", autocomplete: "current-password" });
  const emailInput = emailWrap.querySelector("input") as HTMLInputElement;
  const passwordInput = passwordWrap.querySelector("input") as HTMLInputElement;
  const submit = actionButton("Log in");

  const form = el(
    "form",
    { style: "display:flex;flex-direction:column;gap:12px;width:min(320px,90vw)" },
    [emailWrap, passwordWrap, submit, status]
  );
  form.onsubmit = async (e) => {
    e.preventDefault();
    submit.setAttribute("disabled", "true");
    status.textContent = "";
    try {
      await login(emailInput.value, passwordInput.value);
      renderProjectPicker();
    } catch (err) {
      status.textContent = err instanceof Error ? err.message : "Login failed";
    } finally {
      submit.removeAttribute("disabled");
    }
  };

  app.append(
    el(
      "div",
      {
        style:
          "height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:20px;color:#eee",
      },
      [el("h1", { textContent: "CYMATIC Walkthrough", style: "font-size:20px;margin:0" }), form]
    )
  );
}

async function renderProjectPicker() {
  teardownActiveViewer();
  app.innerHTML = "";
  const status = statusLine();
  const list = el("div", { style: "display:flex;flex-direction:column;gap:8px;width:min(360px,90vw)" });

  app.append(
    el(
      "div",
      {
        style:
          "height:100%;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;color:#eee;overflow-y:auto;padding:20px 0",
      },
      [
        el("h1", { textContent: "Published Simulations", style: "font-size:20px;margin:0" }),
        list,
        status,
        (() => {
          const b = actionButton("Log out");
          b.onclick = () => { logout(); renderLoginScreen(); };
          return b;
        })(),
      ]
    )
  );

  try {
    const projects = await listPublishedProjects();
    if (projects.length === 0) {
      status.style.color = "#aaa";
      status.textContent = "No published projects yet.";
      return;
    }
    for (const project of projects) {
      const b = actionButton(
        `${project.name} (${project.domain})`,
        "padding:14px;font-size:16px;width:100%;"
      );
      b.onclick = () => renderViewer(project);
      list.append(b);
    }
  } catch (err) {
    status.textContent = err instanceof Error ? err.message : "Failed to load projects";
  }
}

async function renderViewer(project: Project) {
  teardownActiveViewer();
  app.innerHTML = "";
  const status = statusLine();
  status.textContent = "Loading walkthrough...";
  status.style.cssText = "position:absolute;top:12px;left:12px;color:#eee;margin:0;z-index:2;";
  const backBtn = actionButton(
    "← Projects",
    "position:absolute;top:12px;right:12px;z-index:2;"
  );
  backBtn.onclick = () => {
    teardownActiveViewer();
    renderProjectPicker();
  };
  const playBtn = actionButton(
    "Pause",
    "position:absolute;bottom:20px;left:50%;transform:translateX(-50%);z-index:2;"
  );
  playBtn.setAttribute("aria-pressed", "true");
  const container = el("div", { style: "position:relative;width:100%;height:100%;" }, [status, backBtn, playBtn]);
  app.append(container);

  let view;
  try {
    view = await fetchSceneForViewing(project.id);
  } catch (err) {
    status.textContent = err instanceof Error ? err.message : "Failed to load scene";
    return;
  }

  const scene = buildScene(view.scene_package);
  const walkthrough = new Walkthrough(view.scene_package.navigation);

  // Explicit empty state instead of a black canvas: a package with no
  // walkthrough path renders a message, not a silent WebGL frame.
  if (!walkthrough.hasPath) {
    playBtn.remove();
    status.style.cssText =
      "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#aaa;margin:0;z-index:2;padding:24px;text-align:center;";
    status.textContent = "No walkthrough path in this package";
    disposeSceneResources(scene);
    return;
  }
  status.remove();

  const camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.05, 500);
  camera.position.copy(walkthrough.startPosition());

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  container.prepend(renderer.domElement);
  const canvas = renderer.domElement;

  let disposed = false;

  // Debounced resize: coalesce bursts into one layout per frame.
  let resizeQueued = false;
  const onResize = () => {
    if (disposed || resizeQueued) return;
    resizeQueued = true;
    requestAnimationFrame(() => {
      if (disposed) {
        resizeQueued = false;
        return;
      }
      resizeQueued = false;
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });
  };
  window.addEventListener("resize", onResize);

  // Touch/mouse drag-to-look, layered on top of the auto-fly path: the
  // walkthrough drives camera *position*, this drives an additional look
  // offset so the viewer can glance around without leaving the guided path.
  let lookYaw = 0;
  let lookPitch = 0;
  let dragging = false;
  let lastX = 0;
  let lastY = 0;
  // Coalesce pointer events: at most one look update per frame.
  let pendingDX = 0;
  let pendingDY = 0;
  let lookQueued = false;
  const flushLook = () => {
    lookQueued = false;
    if (disposed) {
      pendingDX = 0;
      pendingDY = 0;
      return;
    }
    lookYaw -= pendingDX * 0.005;
    lookPitch = THREE.MathUtils.clamp(lookPitch - pendingDY * 0.005, -1.2, 1.2);
    pendingDX = 0;
    pendingDY = 0;
  };
  const onDragStart = (x: number, y: number) => {
    dragging = true;
    lastX = x;
    lastY = y;
  };
  const onDragMove = (x: number, y: number) => {
    if (!dragging || disposed) return;
    pendingDX += x - lastX;
    pendingDY += y - lastY;
    lastX = x;
    lastY = y;
    if (!lookQueued) {
      lookQueued = true;
      requestAnimationFrame(flushLook);
    }
  };
  const onDragEnd = () => {
    dragging = false;
  };
  const onMouseDown = (e: MouseEvent) => onDragStart(e.clientX, e.clientY);
  const onMouseMove = (e: MouseEvent) => onDragMove(e.clientX, e.clientY);
  const onTouchStart = (e: TouchEvent) => {
    const t = e.touches[0];
    onDragStart(t.clientX, t.clientY);
  };
  const onTouchMove = (e: TouchEvent) => {
    const t = e.touches[0];
    onDragMove(t.clientX, t.clientY);
    e.preventDefault();
  };
  canvas.addEventListener("mousedown", onMouseDown);
  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onDragEnd);
  canvas.addEventListener("touchstart", onTouchStart);
  canvas.addEventListener("touchmove", onTouchMove, { passive: false });
  canvas.addEventListener("touchend", onDragEnd);

  playBtn.onclick = () => {
    walkthrough.togglePlay();
    playBtn.textContent = walkthrough.playing ? "Pause" : "Play";
    playBtn.setAttribute("aria-pressed", String(walkthrough.playing));
  };

  // Reused frame temps: no per-frame allocation at 60 fps.
  const _up = new THREE.Vector3(0, 1, 0);
  const _dir = new THREE.Vector3();
  const _right = new THREE.Vector3();
  const _target = new THREE.Vector3();
  const frame: WalkthroughFrame = { position: new THREE.Vector3(), lookAt: new THREE.Vector3() };
  const clock = new THREE.Clock();
  let rafId = 0;
  function animate() {
    if (disposed) return;
    rafId = requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.1);
    walkthrough.update(dt, frame);
    const { position, lookAt } = frame;
    camera.position.copy(position);

    _dir.copy(lookAt).sub(position).normalize();
    _dir.applyAxisAngle(_up, lookYaw);
    _right.crossVectors(_dir, _up).normalize();
    _dir.applyAxisAngle(_right, lookPitch);
    camera.lookAt(_target.copy(position).add(_dir));

    renderer.render(scene, camera);
  }
  animate();

  // Back button (and every screen transition) must cancel the RAF loop,
  // remove window/canvas listeners, and free GL resources.
  activeViewerCleanup = () => {
    disposed = true;
    cancelAnimationFrame(rafId);
    window.removeEventListener("resize", onResize);
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onDragEnd);
    canvas.removeEventListener("mousedown", onMouseDown);
    canvas.removeEventListener("touchstart", onTouchStart);
    canvas.removeEventListener("touchmove", onTouchMove);
    canvas.removeEventListener("touchend", onDragEnd);
    try {
      disposeSceneResources(scene);
    } finally {
      renderer.dispose();
      renderer.domElement.remove();
    }
  };
}

// Session restore is async (cookie validation, like apps/web's authReady):
// show the picker only when a live session exists.
if (isLoggedIn()) {
  renderProjectPicker();
} else {
  void tryRestoreSession().then((restored) => {
    if (restored) renderProjectPicker();
    else renderLoginScreen();
  });
}

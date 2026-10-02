import * as THREE from "three";
import { isLoggedIn, login, logout } from "./auth";
import { fetchSceneForViewing, listPublishedProjects } from "./api";
import { buildScene } from "./scene";
import { Walkthrough } from "./navigation";
import type { Project } from "./types";

const app = document.getElementById("app")!;

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
  app.innerHTML = "";
  const status = statusLine();
  status.textContent = "Loading walkthrough...";
  status.style.cssText = "position:absolute;top:12px;left:12px;color:#eee;margin:0;z-index:2;";
  const backBtn = actionButton(
    "← Projects",
    "position:absolute;top:12px;right:12px;z-index:2;"
  );
  backBtn.onclick = () => renderProjectPicker();
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
  status.remove();

  const scene = buildScene(view.scene_package);
  const walkthrough = new Walkthrough(view.scene_package.navigation);

  const camera = new THREE.PerspectiveCamera(70, window.innerWidth / window.innerHeight, 0.05, 500);
  camera.position.copy(walkthrough.startPosition());

  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  container.prepend(renderer.domElement);

  // Debounced resize: coalesce bursts into one layout per frame.
  let resizeQueued = false;
  window.addEventListener("resize", () => {
    if (resizeQueued) return;
    resizeQueued = true;
    requestAnimationFrame(() => {
      resizeQueued = false;
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    });
  });

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
    if (!dragging) return;
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
  renderer.domElement.addEventListener("mousedown", (e) => onDragStart(e.clientX, e.clientY));
  window.addEventListener("mousemove", (e) => onDragMove(e.clientX, e.clientY));
  window.addEventListener("mouseup", onDragEnd);
  renderer.domElement.addEventListener("touchstart", (e) => {
    const t = e.touches[0];
    onDragStart(t.clientX, t.clientY);
  });
  renderer.domElement.addEventListener("touchmove", (e) => {
    const t = e.touches[0];
    onDragMove(t.clientX, t.clientY);
    e.preventDefault();
  }, { passive: false });
  renderer.domElement.addEventListener("touchend", onDragEnd);

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
  const clock = new THREE.Clock();
  function animate() {
    requestAnimationFrame(animate);
    const dt = Math.min(clock.getDelta(), 0.1);
    const { position, lookAt } = walkthrough.update(dt);
    camera.position.copy(position);

    _dir.copy(lookAt).sub(position).normalize();
    _dir.applyAxisAngle(_up, lookYaw);
    _right.crossVectors(_dir, _up).normalize();
    _dir.applyAxisAngle(_right, lookPitch);
    camera.lookAt(_target.copy(position).add(_dir));

    renderer.render(scene, camera);
  }
  animate();
}

if (isLoggedIn()) {
  renderProjectPicker();
} else {
  renderLoginScreen();
}

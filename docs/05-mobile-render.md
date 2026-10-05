# 05 — Mobile Render (Native On-Device)

> Pivot: Unity/WebRTC streaming is frozen. Android renders on-device with
> Filament stereo SBS, online-first (scene JSON + assets from API, no server
> GPU). See `docs/27-mobile-render-pivot.md` for status/plan.

## 1. Native rendering architecture

- `ui/render/RenderActivity` — owns lifecycle: create render session →
  fetch `scene-package/view` → build scene → start tour/heartbeat → end
  session. Degrades to data preview if Filament runtime absent.
- `render/FilamentSceneBuilder` — engine/renderer/scene, UiHelper SwapChain,
  side-by-side left/right views + per-eye cameras (IPD from prefs), sun +
  capped custom lights from `LightingPresets`, indexed box/plane geometry
  (outward-CCW winding), per-entity `MaterialInstance`, Choreographer loop.
  Ubershader source: `android/client/materials/ubershader.mat` → build with
  matc to `res/raw/ubershader.filamat` (git-ignored).
- `render/EntityMapper` — entity → `RenderCommand`; GLB from
  `asset_manifest` if downloadable, else procedural primitive fallback.
- `render/SceneCoords` — Unity left-handed → OpenGL right-handed (Z-flip).
- `render/LightingPresets` — preset/time-of-day table; `TourGuide` —
  1.2 m/s legs + 3 s dwell.
- `SensorFusion` head pose at 20 Hz (IMU orientation → stereo cameras);
  thermal scaling from `render_quality` pref (reduce resolution/effects,
  keep single active session).

## 2. Input model (no hand tracking in core path)

- Gaze dwell: `GazeSelector` — 3D angular dwell 2 s within 5° over POI
  markers/nav beacons; gaze confirm teleports. Reticle + dwell fill UI.
- Controller: select confirms at reticle (edge-triggered), menu opens/
  closes menu, PTT button hold-to-talk. Works without hand tracking.
- Voice PTT only: `RenderVoiceHelper` — hold-to-talk PCM → multipart
  `voice/audio` → TTS reply playback; taps <0.1 s ignored. No wake word,
  no always-on. Telugu selectable; text transcript fallback.
- Experimental (flagged off): wired UVC camera + MediaPipe gestures
  (pinch=select, palm=menu, fist=cancel, swipe=navigate). Low confidence
  → hide hands, fall back to gaze/controller.

## 3. Backend render endpoints

- `POST /v1/render/sessions` — device auto-registry, 426 stale app,
  403 revoked device, PUBLISHED + org checks, 409 single-session guard,
  returns `scene_url`. Shares `stream_sessions` table.
- `POST /v1/render/sessions/{id}/heartbeat` — PENDING→ACTIVE on first
  beat; sweeps silent sessions (>600 s) to DISCONNECTED.
- `POST /v1/render/sessions/{id}/end` — closes; new session allowed after.
- `POST /v1/render/sessions/{id}/voice/audio` — multipart PCM/WAV →
  router STT → copilot chat → TTS base64 reply.
- `GET scene-package/view` — spec-derived scene JSON + `asset_manifest`
  (GLB-or-primitive source). Migration `008` (`mobile_devices`,
  `device_id`, `last_heartbeat_at`).

## 4. Web viewer (preview only)

- Vite walkthrough viewer renders the same scene JSON for builder preview.
  Not a shipping runtime; parity target is POI/tour/lighting, not pixels.
  Device truth is `RenderActivity` on phone in headset.

## 5. Performance policy (low-end first)

- Low-poly assets, baked lighting presets, adaptive quality, 30 fps min,
  latency-first. One concurrent session (409 guard). Thermal: scale down
  before dropping session; disable experimental inputs first.

---

## Frozen appendix: Unity/WebRTC (do not extend)

Condensed from the pre-pivot doc; reference only. Security fixes only.

- Stereo rig: left/right eye cameras, configurable IPD, head pose from
  phone IMU; side-by-side `[ Left | Right ]` frame; H.264 HW encode,
  adaptive quality, 30 fps min / 60 fps aim.
- Streamer: Unity Render Server (native Windows app on gaming laptop, LAN,
  not containerized) loaded scene package, rendered stereo, ran WebRTC
  session, received input packets, executed permitted agent commands.
- Signaling: legacy `offer/answer/candidate` endpoints + WS
  `SignalingClient`; Android `WebRTCManager`/`StreamingService` received
  video and sent compact input (gaze/controller/PTT/UVC-optional).
- Do NOT touch: `unity/`, `WebRTCManager`, `StreamingService`,
  `SignalingClient`, legacy signaling endpoints. Removal only after
  two-device native proof per doc 27 §P6.

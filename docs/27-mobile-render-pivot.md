# Mobile Render Pivot (Unity-free) — status and plan

**Decision:** retire Unity/WebRTC streaming; the Android app renders on-device.
Locked choices: native Android 3D (Google Filament) · stereo SBS VR ·
online-first · Unity frozen-then-removed.

## Backend (P1 — DONE, verified)

- `POST /v1/render/sessions` — device auto-registry, 426 stale app,
  403 revoked device, PUBLISHED + org checks, 409 single-session guard,
  returns `scene_url`. Shares `stream_sessions` with streaming.
- `POST /v1/render/sessions/{id}/heartbeat` — PENDING→ACTIVE on first beat,
  sweeps silent sessions (>600s) to DISCONNECTED.
- `POST /v1/render/sessions/{id}/end` — closes; new session allowed after.
- `POST /v1/render/sessions/{id}/voice/audio` — multipart PCM/WAV → router
  STT → copilot chat → TTS base64 reply.
- Migration `008` (`mobile_devices`, `device_id`, `last_heartbeat_at`).
  Suite: 48/48 container tests. Live: 12/12 lifecycle matrix.

## Android renderer (P2 — implemented, device verification pending)

- `network/model/RenderModels.kt` — render session DTOs + full `cymatic_v1`
  scene DTOs (62 Gson keys cross-checked against backend payloads).
- `ApiClient` — render endpoints + `scene-package/view` + multipart voice.
- `render/` pure logic (JVM unit-tested, no SDK needed for logic):
  `SceneCoords` (Unity LH→GL RH Z-flip), `EntityMapper` (entity→RenderCommand,
  GLB-or-primitive fallback via `asset_manifest`), `LightingPresets`
  (preset/time-of-day table), `TourGuide` (1.2 m/s legs + 3 s dwell).
- `ui/render/RenderActivity` — session→scene→commands→lighting→tour→heartbeat;
  degrades to data preview if Filament absent. Launcher button + manifest.
- Gradle: `filament-android` + `gltfio-android` 1.57.1.
- Tests: `app/src/test/...` (SceneCoords, TourGuide, EntityMapper, Lighting).

## P3 status (implemented, device verification pending)

- `FilamentSceneBuilder`: engine/renderer/scene, UiHelper SwapChain,
  SBS left/right views + per-eye cameras (IPD from prefs), sun + capped
  custom lights from `LightingPresets`, indexed box/plane geometry with
  **computationally verified outward-CCW winding** (see scratch check),
  per-entity `MaterialInstance` colors, Choreographer frame loop.
- `GazeSelector`: 3D angular dwell (2 s, 5°) over POI markers/nav beacons;
  gaze confirm teleports, controller select confirms at reticle (edge-triggered).
- `RenderVoiceHelper`: hold-to-talk PCM → `voice/audio` multipart → TTS reply
  playback; <0.1 s taps ignored.
- `RenderActivity`: SensorFusion head pose at 20 Hz, tour auto-advance,
  thermal scale from `render_quality` pref, heartbeat loop, graceful
  preview-mode degradation without `.filamat`.
- Ubershader: `android/client/materials/ubershader.mat` source (baseColor +
  roughness, position-only); build with matc into `res/raw/ubershader.filamat`
  (git-ignored, command in the .mat header).

## Not yet done (needs Android SDK machine / device)

- `./gradlew :app:testDebugUnitTest` + `assembleDebug` (no JDK/SDK on this host).
- P3b: gltfio Model loading, floating POI label sprites, lens-distortion mesh.
- P4: already wired at activity level (voice helper live); needs device proof.
- P6: Unity + WebRTC removal after two-device proof (criteria in plan).
- Backend gap for P2: `asset_manifest` URIs → downloadable IDs (resolver
  endpoint or manifest enrichment in `scene-package/view`).

## Frozen (do not extend)

`unity/`, `WebRTCManager`, `StreamingService`, WS `SignalingClient`,
legacy `offer/answer/candidate` endpoints. Security/maintenance fixes only.

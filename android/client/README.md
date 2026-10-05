# CYMATIC Android Client (native on-device VR renderer)

Kotlin app: account login → project picker → **native Filament stereo
rendering** of published simulations (`ui/render/RenderActivity`), plus
voice copilot (PTT), gaze/controller input, diagnostics. The legacy
WebRTC streaming player (`ui/vr/`) is frozen pending removal.

## Layout

- `ui/main/` — launcher (VR / Render 3D / Diagnostics / Settings)
- `ui/render/` — `RenderActivity`, `FilamentSceneBuilder` (engine, SBS
  views, lights, primitive meshes, frame loop)
- `render/` — pure scene logic: `SceneCoords`, `EntityMapper`,
  `LightingPresets`, `TourGuide`, `GazeSelector`, `RenderQuality`,
  `RenderSessionManager`, `RenderVoiceHelper`
- `network/` — Retrofit `ApiService` + Gson models (render + stream + copilot)
- `sensor|input|voice|audio/` — head tracking, gaze/controller, PTT, TTS
- `materials/ubershader.mat` — Filament material source (build `.filamat`
  with `matc`, output git-ignored under `res/raw/`)
- `app/src/test/` — JVM unit tests for `render/` logic

## Contracts

- Backend: `POST /v1/render/sessions` → `scene-package/view` → heartbeat
  loop → `end`; voice via `voice/audio`. See `docs/27`.
- Scene packages are `cymatic_v1` JSON; GLB-or-primitive fallback is mandatory.

## Build / test (needs Android SDK + JDK)

```bash
./gradlew :app:testDebugUnitTest :app:assembleDebug
```

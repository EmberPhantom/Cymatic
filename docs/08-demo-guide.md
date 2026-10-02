# CYMATIC Demo Guide (Unity-free, on-device rendering)

> No Unity, no WebRTC streaming, no GPU render server. The Android app
> renders natively (Filament, stereo SBS) from the scene package served
> by the API. See `docs/27-mobile-render-pivot.md`. Legacy Unity path is frozen.

## Architecture (demo)

```text
Builder (web :3000) -> API (:8000) -> Worker (:8002) -> MinIO (:9000)
Android app (Filament, on-device) <- scene JSON + assets from API
Viewer (:8090) = fallback 2D preview only, not VR
```

## Pre-demo checklist (30 min before)

- [ ] Docker stack healthy: `docker compose ps` shows `cymatic-postgres`,
      `cymatic-redis`, `cymatic-minio`, `cymatic-api`, `cymatic-worker`,
      `cymatic-llm-router`, `cymatic-web`, `cymatic-viewer` healthy.
- [ ] DB migrated: `migrate` service completed with exit 0
      (`docker compose ps migrate` or `docker compose logs migrate`).
- [ ] API keys in `.env`: `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `SARVAM_API_KEY`
      (+ `NVIDIA_NIM_API_KEY` / `OPENAI_API_KEY` if routed).
- [ ] MinIO bucket exists (`cymatic`); console at `:9001` reachable.
- [ ] 2 published projects ready (1 real-estate, 1 heritage) + test login
      (`demo@cymatic.dev` / `demo123`).
- [ ] Android phone charged, app installed, Bluetooth controller paired,
      same LAN as API host. Have backup phone ready.
- [ ] Viewer fallback checked: `http://localhost:8090` loads a published project.

## Scenario 1: Real-estate prompt-to-publish (5 min, builder web UI)

1. Open `http://localhost:3000` -> "Get Started".
2. Prompt: *"Create a modern 3-bedroom apartment walkthrough with warm lighting and a guided tour."*
3. Clarify: Modern, 3 bed / 2 bath, 1500 sqft, $500K-1M.
4. Click "Generate Specification"; watch Intake -> Research -> Architect -> Composer -> Validation.
5. Review spec preview -> click "Publish". Confirm project status = PUBLISHED.

## Scenario 2: Heritage prompt-to-publish (5 min, builder web UI)

1. New project. Prompt: *"Create a heritage temple courtyard walkthrough with guided narration in Telugu."*
2. Clarify: South-Indian temple, Chola period, POIs (Gopuram, Mandapa, Garbhagriha, Tank), Telugu narration on.
3. Generate -> Validate -> Publish. Confirm status = PUBLISHED.

## Scenario 3: On-device walkthrough (Android app, ~5 min per project)

1. Launch CYMATIC app, log in (`demo@cymatic.dev`).
2. Select published project -> "Render 3D" (native Filament walkthrough).
3. App flow: `POST /v1/render/sessions` -> `scene_url` -> scene JSON -> Filament scene + lighting + tour.
4. Show interactions:
   - Gaze: dwell ~2 s on POI marker/nav beacon to select/teleport.
   - Controller: reticle + trigger to confirm selection.
   - PTT copilot: hold-to-talk ("Show me the kitchen" / "What is the garbhagriha?"), release for TTS reply (EN/Telugu).
   - Guided tour auto-advance (~1.2 m/s legs, 3 s dwell); heartbeat keeps session ACTIVE.
5. End session from UI (`.../end`); new session allowed after close.
6. Fallback preview (no headset): open `http://localhost:8090`, pick the same published project for a 2D walkthrough.

## Performance targets

| Metric | Target | Where to check |
|--------|--------|----------------|
| On-device FPS | >= 30 fps | RenderActivity stats / Choreographer |
| Phone temp | < 45 C | thermal readout; quality pref scales down |
| Session startup | < 10 s | login -> first frame |
| Voice copilot reply | < 2 s | STT + LLM + TTS round-trip |
| Single session | 1 active / device | second open returns 409 |

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `POST /v1/render/sessions` -> 409 | session already active (single-session guard) | end stale session (`.../end`) or wait for sweep (>600 s silent -> DISCONNECTED) |
| `.../render/sessions` -> 426 | stale app version (device auto-registry) | update Android app, retry |
| `.../render/sessions` -> 403 | device revoked / project not PUBLISHED / wrong org | re-register device, publish project, check tenant |
| Scene view -> 400 unpublished | project not published | Publish in builder first; viewer and app need PUBLISHED |
| Empty/data preview, no 3D | Filament assets missing (`.filamat` not built) | build ubershader with `matc` into `res/raw/ubershader.filamat`, reinstall |
| No copilot reply | STT/TTS or router key | check `SARVAM_API_KEY`, router health (`:8001/health`), mic permission; taps <0.1 s ignored |
| Low FPS / hot phone | high poly / lights | lower `render_quality` pref, baked lighting, fewer custom lights |
| Scene assets 404/403 | MinIO bucket/URL | verify `cymatic` bucket, `S3_ENDPOINT`, `:9000` reachable |

## Post-demo

- Collect feedback; save session + `cymatic-api` logs.
- Test login: `demo@cymatic.dev` / `demo123`. Pre-create 2-3 published projects for fast demos.
- Env needed: `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `SARVAM_API_KEY` (see `.env.example`).

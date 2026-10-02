# CYMATIC Roadmap and Task Breakdown

## Phase 0: Repository and Environment Foundation

### Goal
Create a stable monorepo and local development environment.

### Tasks
- create monorepo structure
- add README, CLAUDE.md, AGENTS.md
- add Docker Compose base
- add environment templates
- add Postgres/Redis/MinIO services
- add basic CI/lint/test placeholders

### Acceptance Criteria
- repo structure is clean
- Docker Compose starts core infrastructure
- docs are readable by agents
- environment variables are documented

---

## Phase 1: Core Backend Skeleton

### Goal
Build the backend control plane.

### Tasks
- implement auth skeleton
- implement organizations/users
- implement projects CRUD
- implement simulation spec storage
- implement asset upload metadata
- implement audit logging
- implement job queue foundation

### Acceptance Criteria
- API starts cleanly
- project creation works
- spec records can be saved
- auth and tenant scoping are enforced

---

## Phase 2: Simulation Spec Engine

### Goal
Create structured generation core.

### Tasks
- define Simulation Spec schema
- implement spec validation
- implement draft spec generation endpoint
- implement clarification flow
- implement spec versioning

### Acceptance Criteria
- prompt can produce structured spec
- invalid specs are rejected
- spec can be reviewed and edited

---

## Phase 3: LLM Router

### Goal
Centralize AI model access.

### Tasks
- configure LiteLLM or equivalent
- add provider keys
- implement routing policy layer
- implement task-based routing
- implement sensitivity rules
- implement usage logs

### Acceptance Criteria
- one internal API can call multiple providers
- fallback works
- free provider policy is enforced
- usage is logged

---

## Phase 4: Real Estate Generation Pipeline

### Goal
Generate real estate walkthrough from prompt.

### Tasks
- intake agent
- clarification agent
- real estate domain rules
- template-based scene assembly
- furniture/material presets
- navigation point generation
- validation rules

### Acceptance Criteria
- prompt produces walkthrough spec
- generated scene package is valid
- navigation points exist
- scene is publishable

---

## Phase 5: Native Render Backend (olesale Unity replacement)

### Goal
Serve scenes + assets to the on-device renderer (no server GPU).

### Tasks
- render session API (device registry, heartbeat, end)
- scene package serving (`scene-package/view`) + asset downloads
- voice audio endpoint (multipart PCM → STT → copilot → TTS)
- session guards (single active session, app-version gate)

### Acceptance Criteria
- session create returns `scene_url`
- heartbeat flips PENDING→ACTIVE
- voice round-trip returns transcript + TTS audio
- stale sessions swept after timeout

(Status: DONE — P1, see `docs/27-mobile-render-pivot.md`. Legacy Unity
render-server work under this phase number is frozen, not deleted.)

---

## Phase 6: Android Native Renderer

### Goal
Create playable on-device VR walkthrough (Filament, stereo SBS).

### Tasks
- Filament engine + SBS camera rig + primitive/GLB scene build
- IMU orientation tracking (SensorFusion head pose)
- controller input + gaze dwell selection
- voice PTT capture + TTS playback
- thermal resolution scaling
- diagnostics screen

### Acceptance Criteria
- scene renders from package on-device ≥30 FPS
- gaze selection works
- controller selection works
- voice capture works
- thermal stays <45 °C with scaling

(Status: P2/P3 implemented, device verification pending. Legacy WebRTC
player path under this phase number is frozen.)

---

## Phase 7: Voice Copilot

### Goal
Implement mandatory voice interaction.

### Tasks
- PTT flow
- STT integration
- TTS integration
- language selection
- copilot intent routing
- voice session logging

### Acceptance Criteria
- user can press button and speak
- transcript is generated
- copilot responds
- response is spoken aloud
- Telugu support is configurable

---

## Phase 8: Manual Editing

### Goal
Enable basic scene editing.

### Tasks
- object selection
- move/rotate/delete
- material swap
- AI prompt editing
- save new spec version

### Acceptance Criteria
- user can make simple edits
- edits persist
- edited scene can be republished

---

## Phase 9: Heritage Templates

### Goal
Add heritage visualization category.

### Tasks
- heritage categories
- heritage templates
- prompt-to-heritage flow
- heritage labels/copilot content
- optimization pass

### Acceptance Criteria
- heritage walkthrough can be generated
- performance remains stable
- heritage mode is feature-flagged

---

## Phase 10: Experimental Hand Tracking

### Goal
Add optional UVC camera hand tracking module.

### Tasks
- UVC camera support validation
- MediaPipe hand tracking test
- gesture mapping
- virtual hand rendering
- feature flag
- fallback behavior

### Acceptance Criteria
- module can be disabled completely
- if supported, basic gestures work
- gaze/controller remains primary

---

## Phase 11: Stabilization

### Goal
Prepare for demo/pilot.

### Tasks
- latency tuning
- device diagnostics
- analytics dashboard
- credit metering validation
- security review
- demo script
- pilot documentation

### Acceptance Criteria
- one-stream demo is stable
- core input works reliably
- voice works
- usage is tracked
- documentation is complete

---

## Current Status (as of 2026-10-02 — mobile-render pivot, see docs/27)

### Completed Phases
- ✅ Phase 0: Repository and Environment Foundation
- ✅ Phase 1: Core Backend Skeleton
- ✅ Phase 2: Simulation Spec Engine
- ✅ Phase 3: LLM Router
- ✅ Phase 4: Real Estate Generation Pipeline
- ✅ Phase 5: Native Render Backend — render sessions, heartbeat, voice/audio (P1)
- ✅ Phase 6: Android Native Renderer — Filament SBS, gaze/controller/voice (P2/P3, device proof pending)
- ✅ Phase 7: Voice Copilot (core, incl. render voice endpoint)
- ✅ Phase 8: Manual Editing (core)
- ✅ Phase 9: Heritage Templates (core)
- ✅ Phase 10: Experimental Hand Tracking (core)
- ✅ Phase 11: Stabilization (core: suites 62/35/46, live E2E green)

### Frozen (Unity/WebRTC path — do not schedule)
- Unity Render Server work (scene generator, H.264, signaling, NavMesh, copilot, pooling)
- WebRTC player / H.264 pipeline / signaling (server + Android)
- Unity Scene Loader work (Addressables, instantiation, runtime events)

### Remaining Work
- [ ] P3b: gltfio Model loading, POI label sprites, lens-distortion mesh
- [ ] Device proof: two device classes, ≥30 FPS, <45 °C (then P6 Unity removal)
- [ ] Asset manifest URI → download-ID resolution (backend, for P2 GLB loading)
- [ ] Android Client - UVC camera hand tracking (optional)
- [ ] Circuit breaker for LLM Router (done in code — verify on device-era load)
- [ ] Job queue race conditions fix
- [ ] Connection pooling for MinIO (done in code — verify)
- [ ] Checkpointing in pipelines
- [ ] Thermal management tuning on device (beyond pref scaling)
- [ ] Structured logging with correlation IDs (api done — extend worker/router)
- [ ] Comprehensive test coverage (viewer smoke + android CI job open)
- [ ] Security audit (worker /metrics open; see tech-debt)
- [ ] Performance benchmarks (device FPS/thermal)
- [ ] Documentation polish (this pass)

### Next Sprint Priorities
1. Device build + `./gradlew :app:testDebugUnitTest :app:assembleDebug`
2. P3b renderer gaps (gltfio, labels, distortion)
3. Asset manifest URI resolution endpoint
4. Two-device proof → P6 Unity/WebRTC removal
5. Code dedup batch (schemas, MinIO, queue — see tech-debt)

---

*Last updated: 2026-08-18*
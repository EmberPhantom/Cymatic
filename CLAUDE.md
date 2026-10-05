# Claude Code Instructions for CYMATIC

You are working on **CYMATIC**, an AI Simulation Builder platform.

CYMATIC is a no-code AI simulation generation system that creates real estate and heritage walkthrough experiences rendered on-device in an Android phone-based VR headset (native Filament renderer; legacy Unity/WebRTC path frozen — see `docs/27-mobile-render-pivot.md`).

Your job is to help design, implement, refactor, test, and document the platform in a way that is modular, secure, and executable by a development team.

---

## Mandatory Reading Order

Before making implementation decisions, read these files in order:

1. `README.md`
2. `AGENTS.md`
3. `docs/00-product-scope.md`
4. `docs/01-architecture.md`
5. `docs/02-repo-and-setup.md`
6. `docs/03-data-model-api.md`
7. `docs/04-ai-agents-llm-router.md`
8. `docs/05-mobile-render.md` (+ `docs/27-mobile-render-pivot.md`)
9. `docs/06-roadmap-tasks.md`
10. `docs/07-security-testing.md`

---

## Project Constraints

You must always respect the following constraints:

### Product Constraints
- MVP focuses on real estate and heritage only.
- Medical and other domains are future scope, not current implementation.
- The MVP is single-user.
- Voice interaction is mandatory.
- The builder must be no-code.

### Technical Constraints
- Backend is Python FastAPI.
- Frontend is Next.js.
- Simulation runtime is native on-device rendering (Filament, stereo SBS).
- Android client is native Kotlin.
- Database is PostgreSQL.
- Cache/queue is Redis.
- Object storage is MinIO.
- No local LLM is required in MVP.
- LLM access must go through an LLM Router.
- No server GPU: scene JSON + assets come from the API; the phone renders.
- Development environment is Windows + WSL2 + Docker Desktop.
- Docker Compose is used for local development.
- Kubernetes may be introduced later via k3d/k3s.

### Interaction Constraints
- Primary input is gaze dwell + controller buttons + voice.
- Hand tracking is experimental and disabled by default.
- External hand tracking camera must be wired UVC, not wireless.
- The system must remain usable without hand tracking.

---

## Implementation Rules

When asked to implement a feature:

1. First identify the affected domain:
   - frontend
   - backend
   - worker
   - LLM router
   - Unity
   - Android
   - infra
   - docs

2. Then propose:
   - files to add/modify
   - data schema changes
   - API changes
   - service changes
   - tests
   - documentation updates

3. Then implement only after the plan is clear.

---

## Coding Standards

- Prefer explicit, typed, modular code.
- Prefer Pydantic models for API payloads in FastAPI.
- Prefer server-side validation for all critical operations.
- Prefer feature flags for experimental functionality.
- Prefer async jobs for long-running generation tasks.
- Prefer structured JSON outputs from LLM calls.
- Avoid hardcoding secrets.
- Avoid sending sensitive data to free LLM providers.
- Avoid direct AI-to-engine mutation paths.
- Avoid overbuilding marketplace/plugin systems before MVP stability.

---

## Definition of Done

A task is complete only if:
- it aligns with the documented architecture
- schemas are validated
- security implications are considered
- performance implications are considered
- documentation is updated
- tests or test plan are included where practical
- no experimental feature is made mandatory unless specified

---

## Preferred Response Style

When working on this repository:
- be precise
- be structured
- avoid generic advice
- prefer executable implementation steps
- prefer file-by-file changes
- prefer schemas and contracts before UI/logic
- always call out risks and assumptions

---

## High-Value Tasks for Claude Code

You are especially useful for:
- scaffolding the CYMATIC monorepo
- creating FastAPI service skeletons
- creating Pydantic schemas
- defining database models
- designing LLM router policies
- writing agent orchestration flows
- creating Docker Compose configs
- writing test plans
- generating implementation prompts
- updating documentation

---

## Critical Safety Rule

Do not generate code that:
- bypasses validation
- exposes secrets
- allows untrusted arbitrary code execution
- sends sensitive tenant data to unauthorized LLM providers
- breaks the gaze/controller/voice fallback path

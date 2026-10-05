# CYMATIC Investigation Report

**Investigation date:** 2026-08-21
**Compared with:** [`docs/12-latest-investigation.md`](12-latest-investigation.md)

## Executive Verdict

CYMATIC is **not fully fixed, execution-ready, or production-ready**.

The latest changes resolved meaningful structural issues, but the repository still fails core verification gates. The frontend production build fails on the current Windows environment, the worker pipeline tests fail because async functions are called synchronously, API and LLM-router tests cannot collect in the active environment because declared dependencies are missing, and the streaming/API deployment configuration still contains failure-masking and service-address defects.

## Verification Matrix

| Check | Result | Assessment |
|---|---|---|
| `python -m compileall -q services schemas packages/cymatic-shared` | Passed | Python syntax is valid |
| Shared package import smoke test | Passed | Shared package boundary is importable |
| `import app.main` from worker | Passed | Previous import-time worker blocker is resolved |
| Worker pipeline tests | Failed | `process_intake()` returns a coroutine but tests use it synchronously; later DB-dependent tests also require live infrastructure |
| API tests | Blocked during collection | Active environment lacks `jose`; requirements declare `python-jose` |
| LLM-router tests | Blocked during collection | Active environment lacks `litellm`; requirements declare it |
| Web `npm run type-check` | Passed | TypeScript checks successfully |
| Web `npm run build` | Failed | Next SWC Windows binary is invalid: `not a valid Win32 application` |
| `docker compose ... config` | Passed | Compose YAML resolves with local `.env` |
| Git staging dry-run | Passed | Ignored secrets/generated paths are excluded |
| Android build | Unverified | Kotlin DSL/settings exist, but wrapper scripts/JAR and a real build were not found/verified |
| Unity build/device streaming | Unverified | No editor/device runtime verification was available |

## Previous Findings: Resolution Status

| Finding from prior report | Status now | Evidence |
|---|---|---|
| LLM-router syntax error | Resolved | Compileall passes |
| Worker imports deleted local models | Resolved | Worker generation imports `cymatic_shared.models`; worker import smoke test passes |
| Worker import-time MinIO failure | Resolved for import | `import app.main` now passes without MinIO running |
| Shared package import boundary | Improved/resolved structurally | Shared import smoke test passes |
| Frontend lockfile and standalone output | Resolved structurally | Lockfile exists; standalone output remains configured |
| Frontend production build | Still open | Invalid Windows SWC native binary |
| Android Groovy/Kotlin DSL mismatch | Resolved structurally | Kotlin DSL files/settings are present |
| Android Gradle wrapper | Still open/unverified | No `gradlew`, `gradlew.bat`, or wrapper JAR was found in the project scan |
| Refresh-token flow | Implemented structurally | `/refresh`, token type checks, rotation, and in-memory revocation now exist; persistence and multi-instance behavior remain open |
| Streaming forwarding | Still unsafe | Broad exception handlers return fallback success responses |
| WebSocket authorization | Partially implemented | Token is parsed, but connection authorization and session ownership need end-to-end verification |
| Asset processing | Partially implemented | Worker updates processing status and metadata, but processing remains placeholder-level rather than a verified asset pipeline |
| Analytics aggregation | Implemented structurally | Aggregation code exists; correctness and production query performance remain untested |
| Runtime `create_all` | Still open in tests | API tests create schema directly instead of validating Alembic migrations |
| GitHub upload hygiene | Resolved structurally | Dry-run staging excludes local secrets and generated outputs; changes remain uncommitted |

## Open Issues

### C-01: Frontend production build is blocked

**Severity:** Critical

`apps/web` type-checks, but `npm run build` fails while loading `@next/swc-win32-x64-msvc` with `not a valid Win32 application`. Until a clean dependency installation or supported build environment produces a successful production build, the web artifact cannot be considered releasable. Check lockfile integrity, native package architecture, and clean-install behavior in CI.

### C-02: Worker pipeline tests violate the async API contract

**Severity:** Critical

`services/worker/tests/test_pipeline.py` calls `process_intake()` synchronously, while the shared implementation defines it as `async`. The first test therefore receives a coroutine and fails with `AttributeError: 'coroutine' object has no attribute 'detected_domain'`; the coroutine is also never awaited. Align the tests and callers with the async contract, or deliberately provide a synchronous boundary. Do not suppress the warning.

### C-03: API and LLM-router test environments are incomplete

**Severity:** High

API pytest collection fails because `jose` is unavailable, and LLM-router collection fails because `litellm` is unavailable. The packages are declared in service requirements, so the repository does not currently prove that a clean environment can install and run all test suites. CI must install each service and the shared package from a documented, reproducible setup.

### C-04: Compose API points to localhost for the LLM router

**Severity:** High

The resolved Compose configuration sets the API `LLM_ROUTER_URL` to `http://localhost:8001`, while the router is a separate Compose service. Inside the API container, this points back to the API container rather than `llm-router`. Use the service DNS name and add a connectivity/readiness check.

### C-05: Streaming endpoints mask failures as successful responses

**Severity:** High

`services/api/app/api/v1/endpoints/streaming.py` contains handlers such as `except (httpx.ConnectError, Exception)`. Since `Exception` already catches `httpx.ConnectError` and nearly every other runtime failure, the endpoints return friendly fallback payloads instead of reliable HTTP errors. This can leave clients believing signaling, chat, or voice operations succeeded when they did not. Catch expected transport/status errors explicitly and return appropriate 4xx/5xx responses.

### C-06: WebSocket signaling authorization needs ownership enforcement

**Severity:** High

The WebSocket route accepts a query token and validates JWT shape, but the audit did not prove that the authenticated subject is authorized for the requested stream session or that the client type is allowed for that session. Enforce token validation, session existence, organization ownership, participant role, and expiry before accepting or routing messages.

### C-07: Runtime readiness and migration verification remain incomplete

**Severity:** High

Tests use `Base.metadata.create_all`, which bypasses the Alembic migration path. Compose also relies on service startup ordering in places where readiness is required. A production readiness check must run migrations against PostgreSQL, start services only after dependencies are healthy, and exercise the actual API/worker queue path.

### C-08: Android and Unity runtime gates are unverified

**Severity:** High

The Android project has Kotlin DSL/settings files, but no complete Gradle wrapper was found and no APK build or device/WebRTC test was run. Unity scripts retain environment-specific localhost defaults and the render/streaming path was not built or exercised. The headset delivery path is therefore not execution-ready.

### C-09: Asset and analytics implementations are not production-proven

**Severity:** Medium

The worker now transitions asset statuses and records processing metadata, and analytics aggregation code exists. However, no integration test proves real asset conversion/storage failure handling, idempotency, or correct aggregation across organizations and time ranges. These paths should not be described as production-ready until backed by database and MinIO integration tests.

### C-10: Refresh-token revocation is process-local

**Severity:** Medium

Refresh-token rotation and revocation now exist, but revocations are held in an in-memory set in `services/api/app/core/security.py`. Revocation is lost on restart and is not shared across API replicas. Use a persistent store such as Redis or a database table before horizontal scaling or security-sensitive production use.

### C-11: Repository upload preparation is incomplete

**Severity:** Medium

Git ignore/staging hygiene passes, but the worktree still contains uncommitted application changes and deletions. No commit or push was performed. Before GitHub upload, review the complete diff, run the clean-install/CI checks, commit intentionally, and verify that no required generated wrapper or deployment file was omitted.

## Readiness Assessment

| Area | Status |
|---|---|
| Source syntax/importability | **Partially ready** |
| Frontend development checks | **Ready for type-check only** |
| Frontend production artifact | **Blocked** |
| API testability | **Blocked by environment; behavior not fully verified** |
| Worker pipeline | **Blocked by failing async tests and infrastructure-dependent tests** |
| LLM routing | **Blocked by missing test dependency and unverified provider policy paths** |
| Docker Compose configuration | **Parses, but API router address is incorrect** |
| Database migration lifecycle | **Not production-ready** |
| Authentication/session security | **Not production-ready** |
| Android client | **Unverified/not execution-ready** |
| Unity renderer and WebRTC | **Unverified/not execution-ready** |
| GitHub upload hygiene | **Structurally ready, pending intentional commit** |
| Overall | **Not execution-ready; not production-ready** |

## Required Exit Gates

1. Produce a successful clean `npm run build` on the supported build platform.
2. Install all declared Python dependencies in isolated environments and collect/run API, worker, router, and shared tests.
3. Fix the async worker test/caller contract and run the full worker suite with PostgreSQL, Redis, and MinIO.
4. Change the Compose API router URL to `http://llm-router:8001` and verify health/readiness behavior.
5. Replace broad streaming exception handlers with explicit error handling and test failed render/router responses.
6. Prove WebSocket authorization and session ownership with negative tests.
7. Run Alembic migrations in a clean PostgreSQL database and remove schema-creation assumptions from runtime tests.
8. Build the Android client with a complete Gradle wrapper and exercise Unity/WebRTC signaling on a supported device/runtime.
9. Add integration coverage for asset processing, analytics, token revocation, retries, and idempotency.
10. Review and commit the intended GitHub upload surface only after the gates above pass.

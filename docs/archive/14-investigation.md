# CYMATIC Follow-up Investigation

**Investigation date:** 2026-08-21
**Compared with:** [`docs/13-investigation.md`](13-investigation.md)

## Verdict

CYMATIC has improved, but it is **still not execution-ready or production-ready**.

The latest changes fixed the worker test callers to await intake and clarification operations, corrected the API container's LLM router address, and preserved the successful Python compilation, worker import, frontend type-check, Compose parsing, and staging-hygiene checks. The production web build still fails. API tests now stop on a missing `passlib` dependency, worker pipeline tests hang while trying to call the live LLM router, and LLM-router tests fail during collection because `CircuitBreaker` declares a private Pydantic field with an incompatible v1 pattern.

## Verification Results

| Check | Result | Status |
|---|---|---|
| Python compileall | Passed | Resolved |
| Worker `import app.main` | Passed | Previous worker import blocker remains resolved |
| Web `npm run type-check` | Passed | TypeScript checks |
| Web `npm run build` | Failed | Invalid `@next/swc-win32-x64-msvc` binary remains a release blocker |
| Docker Compose config | Passed | Compose parses |
| Compose API `LLM_ROUTER_URL` | Corrected | Resolves to `http://llm-router:8001` |
| Worker intake tests | No assertion failure reached | Test execution hangs on live LLM request; test isolation/fallback timeout remains inadequate |
| API pytest collection | Failed | `ModuleNotFoundError: No module named 'passlib'` |
| LLM-router pytest collection | Failed | Pydantic v2 rejects `_lock: Lock = Field(...)` in `CircuitBreaker` |
| Android Gradle wrapper/build | Unverified | Only settings/build files and wrapper properties were found |
| Unity/WebRTC/device path | Unverified | No runtime build or device test |
| GitHub staging hygiene | Previously passed | Worktree still has uncommitted changes |

## Prior Finding Status

| Prior finding | Status now | Evidence |
|---|---|---|
| Frontend production build | Still open | Next SWC binary is not a valid Win32 application |
| Worker async/sync contract | Fixed in tests | `test_pipeline.py` now awaits async intake; execution still depends on an available router or bounded fallback |
| API/router missing dependencies | Still open, changed failure | API now fails on missing `passlib`; router reaches a Pydantic model error instead of missing `litellm` |
| Compose API router URL | Fixed | Resolved Compose output contains `http://llm-router:8001` for API |
| Streaming failure masking | Still open | Broad `except Exception` handlers remain in streaming endpoints |
| WebSocket/session authorization | Still unverified | JWT parsing exists, but end-to-end ownership and participant authorization are not tested |
| Migration/readiness lifecycle | Still open | Tests use `Base.metadata.create_all`; readiness integration was not run |
| Android/Unity runtime | Still unverified | No complete Android build or Unity/WebRTC test |
| Process-local token revocation | Still open | Revocation remains in an in-memory set |

## Current Issues

### C-01: Frontend production build remains blocked

**Severity:** Critical

`npm run build` fails loading `apps/web/node_modules/@next/swc-win32-x64-msvc/next-swc.win32-x64-msvc.node` because the native module is not a valid Win32 application. Type-checking passing is insufficient: no deployable Next production artifact has been proven. Validate the lockfile and native dependency installation in a clean supported CI environment, then rerun the build.

### C-02: Worker tests are coupled to a live LLM router and can hang

**Severity:** Critical

The previous coroutine assertion is fixed, but `TestIntakeAgent` does not isolate the LLM client. `process_intake()` attempts the configured router with a 120-second HTTP timeout before falling back. With no router running, the test command does not complete within the investigation window. Tests need mocked router responses or a short, explicit connection timeout; production fallback behavior also needs bounded latency.

### C-03: API test collection still lacks declared runtime dependencies

**Severity:** High

API collection now fails on `ModuleNotFoundError: No module named 'passlib'`. `services/api/requirements.txt` declares `passlib[bcrypt]==1.7.4`, so the active test environment is not reproducible from the declared dependency set. A clean isolated install and complete API suite remain unverified.

### C-04: LLM-router is incompatible with the active Pydantic v2 runtime

**Severity:** Critical

`services/llm-router/app/routing/circuit_breaker.py` declares `_lock: Lock = Field(default_factory=Lock, exclude=True)` inside a `BaseModel`. Pydantic v2 rejects this with `NameError: Fields must not use names with leading underscores`. Use `PrivateAttr(default_factory=Lock)` or move synchronization state outside the Pydantic model, then rerun router collection and runtime tests.

### C-05: Streaming endpoints still mask operational failures

**Severity:** High

`services/api/app/api/v1/endpoints/streaming.py` retains broad `except Exception as e` handlers across render, chat, voice, and signaling paths. These handlers return fallback payloads for unexpected failures, making failed operations look successful to clients. Narrow exception handling and explicit error status contracts are required.

### C-06: WebSocket authorization is not end-to-end proven

**Severity:** High

The signaling endpoint accepts a token query parameter and decodes it, but the audit still lacks tests proving that the token subject owns the requested session, belongs to the correct organization, and is permitted to use the declared client type. Add negative authorization tests before exposing signaling to clients.

### C-07: Database migration and service readiness gates remain unverified

**Severity:** High

API test fixtures call `Base.metadata.create_all`, bypassing Alembic. Compose parsing passes, but API/worker readiness and migration startup were not exercised against fresh PostgreSQL, Redis, and MinIO services. This is not sufficient for a production deployment claim.

### C-08: Android and Unity delivery remains unverified

**Severity:** High

The Android tree contains Kotlin DSL files and `gradle-wrapper.properties`, but no complete wrapper executable/JAR was found in the scan. No APK, Unity render server, WebRTC signaling, stereo output, or Android device test was run.

### C-09: Security and scale hardening remain incomplete

**Severity:** Medium

Refresh-token revocation is process-local and disappears on restart or across API replicas. Streaming/session behavior, MinIO asset processing, analytics aggregation, retries, and idempotency also lack integration verification. These paths should remain classified as pre-production until tested with real service dependencies.

### C-10: GitHub upload is not yet a completed release operation

**Severity:** Medium

Ignore rules and staging dry-run hygiene remain good, but the worktree contains uncommitted modifications, deletions, and investigation reports. No intentional commit or push was performed, and the repository cannot be called upload-complete until the final diff is reviewed and the build/test gates pass.

## Readiness Matrix

| Area | Readiness |
|---|---|
| Python syntax/imports | Partially ready |
| Frontend type-check | Ready |
| Frontend production artifact | Blocked |
| API tests | Blocked |
| Worker tests | Blocked/hanging without router and infrastructure |
| LLM router | Blocked by Pydantic model error |
| Compose syntax/config | Ready for parsing only |
| Database migrations/readiness | Not ready |
| Auth/session security | Not production-ready |
| Android client | Unverified |
| Unity/WebRTC runtime | Unverified |
| Overall | **Not execution-ready; not production-ready** |

## Required Next Gates

1. Fix `CircuitBreaker` private state for Pydantic v2 and rerun router tests.
2. Install API dependencies in a clean environment and run the complete API suite.
3. Mock or bound LLM calls in worker tests and run the full suite with service integration tests separately.
4. Resolve the Next SWC installation/build failure and produce a successful production build.
5. Replace broad streaming exception handling and add failure-response tests.
6. Add WebSocket session ownership and organization authorization tests.
7. Run Alembic migrations on a clean database and verify Compose readiness ordering.
8. Complete the Android wrapper/build and validate Unity/WebRTC/device streaming.
9. Review, commit, and push only the intended GitHub repository contents.

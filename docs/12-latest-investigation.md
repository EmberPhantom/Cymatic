# CYMATIC Latest Investigation

**Investigation date:** 2026-08-20  
**Baseline:** [`docs/11-current-investigation.md`](11-current-investigation.md)

## Verdict

CYMATIC is **not fully fixed and is not execution-ready**.

There is measurable progress since the prior audit:

- Python compilation passes.
- Worker task imports now use `cymatic_shared.models` instead of the deleted worker-local project/spec modules.
- The shared package imports successfully.
- Docker Compose now parses successfully with the local `.env` present.
- Frontend TypeScript checking passes.
- Android Kotlin DSL/settings files have been added and the previous Groovy-in-`.kts` issue appears resolved.
- GitHub upload hygiene was added and the dry-run staging surface excludes local secrets and generated artifacts.

The project still cannot be called execution-ready because worker startup performs a live MinIO network request during module import, API/router test environments are incomplete, the frontend production build fails, the web Dockerfile conflicts with the repository-root Compose build context, and the main authentication, streaming, asset, analytics, and production database gaps remain.

## Verification Results

| Check | Result | Status |
|---|---|---|
| `python -m compileall -q services schemas packages/cymatic-shared` | Passed | Resolved syntax-level blocker |
| Shared package import smoke test | Passed | Shared package is importable in the current interpreter |
| API pytest collection | Failed: `ModuleNotFoundError: No module named 'jose'` | Test environment remains incomplete |
| Worker pytest collection | Failed: MinIO connection refused during import | Confirmed import-time side effect |
| Worker `import app.main` | Failed: MinIO request to `localhost:9000` refused | Worker startup blocked without MinIO and is not import-safe |
| LLM-router pytest collection | Failed: `ModuleNotFoundError: No module named 'litellm'` | Test environment remains incomplete |
| Frontend `npm run type-check` | Passed | TypeScript currently checks successfully |
| Frontend `npm run build` | Failed: invalid Windows SWC binary | Production web build remains blocked |
| Docker Compose config | Passed | Compose resolves with the local `.env` |
| Git staging dry-run | Passed | No `.env`, caches, node modules, build outputs, or benchmark artifacts would be staged |
| Android Gradle syntax | Improved/unverified | Kotlin DSL/settings exist; wrapper scripts/JAR and actual build were not verified |
| Unity build/runtime | Unverified | Unity editor/device runtime unavailable |

## Previous Findings: Status

| Finding | Current status | Evidence |
|---|---|---|
| LLM-router syntax error | **Resolved** | Python compilation passes |
| Worker missing model imports | **Partially resolved** | Generation task now imports `cymatic_shared.models`; worker startup reaches MinIO instead of missing project module |
| Shared package boundary | **Improved** | `packages/cymatic-shared` imports successfully and is referenced by API/worker requirements and Dockerfiles |
| Frontend lockfile | **Resolved** | `apps/web/package-lock.json` exists and TypeScript runs |
| Next standalone output | **Resolved** | `output: 'standalone'` remains configured |
| Frontend production build | **Still blocked** | SWC native binary is invalid for current Windows environment |
| Android Groovy/Kotlin DSL issue | **Resolved structurally** | Kotlin syntax and `settings.gradle.kts` are present |
| Android wrapper | **Still incomplete** | Only `gradle-wrapper.properties` was found; no `gradlew`, `gradlew.bat`, or wrapper JAR was found |
| Refresh tokens | **Still unresolved** | Refresh-token endpoint remains unimplemented/unsupported |
| Streaming forwarding | **Partially implemented but unsafe** | HTTP/WebSocket forwarding exists, but broad exception handling still returns success after failures |
| WebSocket authorization | **Unverified/open risk** | Signaling route does not visibly authenticate before accepting connections |
| Asset processing | **Still unresolved** | Worker retains TODO processing and can mark assets ready without processing |
| Analytics aggregation | **Still unresolved** | Aggregation task remains placeholder logic |
| Worker wildcard CORS | **Resolved structurally** | Worker uses configured origins |
| Runtime `create_all` | **Still unresolved** | API/worker DB startup still creates schema directly |
| GitHub upload hygiene | **Resolved structurally** | Git initialized on `main`; ignore/staging dry-run passed; no commit or push made |

## Critical Findings

### C-01: Worker startup performs a live MinIO request during import

**Severity:** Critical  
**Evidence:** `services/worker/app/services/minio_client.py`, `packages/cymatic-shared/cymatic_shared/services/minio_client.py`.

Importing `app.main` imports the worker generation tasks, which creates a global `MinIOClient`. Its constructor calls `_ensure_bucket()`, which performs `bucket_exists()` immediately. With MinIO unavailable, import fails with a connection-refused exception.

This breaks test collection, health checks, local startup diagnostics, and any command that imports the worker before infrastructure is ready. Client construction must be lazy or connection failures must be handled outside import time. Bucket initialization belongs in an explicit startup/readiness step with bounded retries.

### C-02: API and router test dependencies are not installed in the active environment

**Severity:** High  
**Evidence:** current pytest output; `services/api/requirements.txt`; `services/llm-router/requirements.txt`.

API tests fail before collection because `python-jose` is unavailable. Router tests fail because `litellm` is unavailable. The requirements declare these packages, so either the active environment was not installed from requirements or the setup process is not being followed consistently. A clean CI run remains unproven.

### C-03: Web production build remains broken

**Severity:** High  
**Evidence:** `npm run build` output.

Next.js cannot load `@next/swc-win32-x64-msvc`; the installed native module is reported as not a valid Win32 application. Type-check success is insufficient. The repository needs a clean lockfile-based install and successful production build on the supported development/CI platform.

### C-04: Web Dockerfile does not match the current repository-root build context

**Severity:** Critical; Docker build verification pending  
**Evidence:** `infra/docker/docker-compose.yml:115-116`, `apps/web/Dockerfile:9-12`.

Compose builds the web service with repository root as context and `apps/web/Dockerfile`, but the Dockerfile runs `COPY package*.json ./` and `COPY . .`, which now read from the repository root rather than `apps/web`. The root does not contain the web package manifest in the expected location. The Dockerfile must either use `apps/web` as its context or copy `apps/web/package*.json` and `apps/web/` explicitly.

### C-05: Container service URLs are inconsistent

**Severity:** High  
**Evidence:** resolved Compose output and `.env`-derived environment values.

Inside the Compose network, API configuration still uses `LLM_ROUTER_URL=http://localhost:8001`, while worker configuration uses `http://llm-router:8001`. API-to-router calls from the API container will target the API container itself, not the router. Similar localhost defaults remain in signaling, MinIO, Unity, and Android configurations. Container-internal service URLs must use service DNS names and be separated from host/device development URLs.

## Expanded Findings

### Streaming failures are still converted into false success

`services/api/app/api/v1/endpoints/streaming.py` still catches broad exception tuples such as `(httpx.ConnectError, Exception)` and returns statuses like `answer_forwarded`, `candidate_forwarded`, or `input_forwarded`. A downstream timeout or 500 can therefore be reported as a successful operation. This makes the stream state unreliable and prevents clients from retrying correctly.

### WebSocket signaling authorization remains an open security risk

The WebSocket signaling route accepts a session identifier and client type, but no visible authenticated-user dependency is enforced before accepting the socket. REST session creation checks project organization, but the socket room itself must verify the bearer/session credential and ownership before joining.

### Worker task lifecycle remains unsafe

- `publish_scene` must verify package readiness, project/spec ownership, and artifact availability before publishing.
- Spec version generation still needs a database unique constraint and collision-safe allocation.
- Asset processing still marks records ready around unimplemented processing work.
- Analytics aggregation remains incomplete.
- Job payloads use IDs, but tenant ownership must be validated in worker handlers before mutation.

### Database migration authority remains ambiguous

API and worker sessions still call `Base.metadata.create_all` while Alembic migrations exist. This can hide missing migrations and create divergent schemas. Production startup should require migrations to be applied and should not create tables implicitly.

### Authentication remains incomplete

- Refresh-token rotation, persistence, revocation, and reuse detection remain absent.
- Registration still accepts a caller-supplied organization ID without a visible invitation/admin authorization flow.
- Router management, cache invalidation, quota, usage, and worker diagnostics require explicit authentication and role checks.

### Android is structurally improved but not upload/build complete

The previous Kotlin DSL syntax problem appears fixed and `settings.gradle.kts` is present. However, no Gradle wrapper scripts or wrapper JAR were found, and no APK build was run. Android still contains emulator-only URLs and cleartext development settings. Device authentication, signaling, and WebRTC behavior remain unverified.

### Unity remains unverified

Unity scripts still default to localhost backend, MinIO, and signaling endpoints. No Unity project build, scene/package load, WebRTC handshake, or low-end-device performance test has passed in this environment.

### GitHub upload readiness is partial

The repository is now a Git worktree on `main` tracking `origin/main`, and the staging dry-run excludes local secrets and generated artifacts. There are still uncommitted source changes, including deletions and modifications in API/worker files. No commit or push was made. Those changes must be reviewed intentionally before upload.

## Readiness Matrix

| Area | Status | Current reason |
|---|---|---|
| Python syntax | Pass | Compilation succeeds |
| Shared package | Pass structurally | Import smoke test succeeds |
| API tests | Blocked | Missing `python-jose` in active environment |
| Worker startup | **Blocked** | Import-time MinIO connection failure |
| Router tests | Blocked | Missing `litellm` in active environment |
| Frontend type-check | Pass | `tsc --noEmit` succeeds |
| Frontend production build | Blocked | Invalid SWC binary |
| Docker Compose config | Pass | Services resolve with `.env` |
| Docker images | Unverified/likely web failure | Web Dockerfile/context mismatch; Docker build not run |
| Android | Partial/unverified | DSL improved; wrapper/build/device validation incomplete |
| Unity | Unverified | No editor/runtime validation |
| Authentication | Partial | Access-token path exists; refresh/revocation incomplete |
| Generation pipeline | Blocked | Worker cannot import/start without MinIO and still needs lifecycle validation |
| Streaming | Partial but unsafe | Forwarding code exists; errors/auth remain problematic |
| GitHub upload | Prepared but not final | Hygiene passes; uncommitted changes require review |
| Production readiness | No | Critical runtime, build, security, and integration gaps remain |

## Required Gates

1. Make worker and API imports side-effect free; initialize MinIO only in controlled startup/readiness code.
2. Install and lock all Python dependencies in clean service environments; run all tests from CI-equivalent contexts.
3. Fix the web Docker build context and produce a clean production image.
4. Repair service-internal URLs for Compose networking.
5. Make streaming error responses truthful and authenticate WebSocket signaling.
6. Implement refresh-token rotation/revocation and protect administrative endpoints.
7. Remove runtime `create_all` from production startup and validate Alembic migrations from an empty database.
8. Complete Android wrapper/build and Unity/Android one-stream smoke testing.
9. Review the current Git diff, then commit and push only after source changes are intentional and tests pass.

## Limitations

- Docker image builds, Android builds, Unity builds, external databases, and device tests were not available.
- The active Python environment is not fully installed from the declared requirements.
- The current frontend environment has dependencies installed but its SWC binary is invalid.
- No application code was changed during this investigation; only this report was added.

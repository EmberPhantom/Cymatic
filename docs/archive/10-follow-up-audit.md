# CYMATIC Follow-Up Codebase Audit

**Audit date:** 2026-08-19
**Baseline:** [`docs/09-codebase-audit.md`](09-codebase-audit.md)
**Scope:** re-validation of all baseline findings plus expanded dependency, package, API, queue, database, CI, security, client, and runtime-contract analysis.

## Executive Verdict

The repository has made partial progress, but it is still **not execution-ready, demo-ready, pilot-ready, or production-ready**.

The LLM router syntax failure is resolved and several missing worker modules now exist. The current repository still cannot demonstrate a complete generation-to-VR path. Test collection is blocked by missing runtime dependencies/import configuration, the worker Docker boundary is incomplete, the Android project remains structurally invalid, and core streaming/authentication features remain placeholders.

## Verification Results

| Check | Current result | Classification |
|---|---|---|
| `python -m compileall -q services schemas` | Passed | Prior LLM-router syntax blocker resolved |
| API tests from `services/api` | Collection failed: `ModuleNotFoundError: No module named 'jose'` | Environment/dependency blocker; test environment is not reproducible |
| Worker tests from `services/worker` | Collection failed: `ModuleNotFoundError: No module named 'minio'` | Worker dependency installation or environment is incomplete |
| LLM-router tests from `services/llm-router` | Collection failed: `ModuleNotFoundError: No module named 'services'` | Test import-root failure |
| Frontend `npm run type-check` | Failed: `tsc` not recognized | Dependencies/lockfile still unavailable |
| Frontend build | Not successfully verified | Requires installed Node dependencies |
| Docker image build | Not successfully verified | Docker Desktop engine unavailable during audit |
| Repository Git status | Unavailable | `P:\Cymatic` is not recognized as a Git repository |

The successful compilation check proves that Python source is syntactically valid. It does not prove that service imports, dependencies, databases, queues, external providers, Unity, or Android builds work.

## Baseline Finding Status

| Baseline finding | Status | Current evidence |
|---|---|---|
| LLM router syntax error | **Resolved** | `compileall` now passes; malformed control flow was corrected |
| Worker missing `app.models`/`app.services` modules | **Partially resolved** | Worker model/service files now exist, but the service still has duplicated/incomplete models and dependency/package-boundary failures |
| Worker queue module missing | **Resolved structurally, not operationally** | `services/worker/app/core/queue.py` exists, but queue behavior and cross-service compatibility are not integration-tested |
| Worker validator importing API service | **Resolved** | Worker now imports `app.services.spec_validator` |
| Frontend lockfile missing | **Still open** | CI and Docker still use `npm ci`; no lockfile was found; local `tsc` is unavailable |
| Next standalone output missing | **Resolved structurally** | `apps/web/next.config.js` now has `output: 'standalone'` |
| Web Docker production build | **Partially resolved** | Dockerfile now aligns with standalone output, but build remains blocked by missing lockfile/dependencies and unavailable Docker engine |
| Android Gradle syntax/project structure | **Still open** | `.kts` files still contain Groovy syntax; no complete Gradle settings/wrapper was verified |
| Refresh tokens | **Still open** | API refresh endpoint still returns HTTP 501 |
| WebRTC signaling forwarding | **Still open** | API streaming endpoints retain TODOs and false-success responses |
| Copilot and voice routing | **Still open** | Placeholder responses remain in streaming endpoints |
| Asset processing | **Still open** | Worker explicitly leaves processing as TODO, then marks assets ready |
| Analytics aggregation | **Still open** | Worker aggregation handler remains a placeholder |
| Wildcard LLM-router CORS | **Resolved** | Router uses configured `CORS_ORIGINS` |
| Wildcard worker CORS | **Still open** | Worker still uses `allow_origins=["*"]` with credentials enabled |
| Development credentials/insecure defaults | **Still open** | Compose and service settings still contain default passwords and localhost/cleartext assumptions |
| Startup `create_all` competing with Alembic | **Still open** | API and worker database sessions still call `Base.metadata.create_all` |

## Critical and High-Severity Findings

### F-01: Worker Docker image still cannot resolve the root shared schema package

**Severity:** Critical
**Evidence:** `services/worker/Dockerfile`, worker agents/pipelines importing `schemas.simulation_spec`.

The worker Dockerfile copies `requirements.txt` and `app/` only. The worker source imports `schemas.simulation_spec`, but the root `schemas/` directory is outside the Docker build context `./services/worker` and is not installed as a package. A worker image built from the documented command cannot import the shared schema module.

The new worker-local models and services address only part of the previous import failure. The shared schema must become an installable dependency or the Docker build must use a deliberate monorepo packaging strategy. The same interface must be used by API, worker, and frontend generation contracts.

### F-02: API and worker maintain divergent database model sets

**Severity:** Critical
**Evidence:** `services/api/app/models`, `services/worker/app/models`, `services/api/app/db/session.py`, `services/worker/app/db/session.py`.

The worker now has local copies of `Project`, `SimulationSpec`, `Asset`, and `ScenePackage`, but does not contain the API's `Organization`, `User`, stream, audit, credit, or runtime-event models. Its models still reference tables such as `organizations` and `users` through foreign keys. This creates schema drift and can make worker metadata creation or queries fail against a database defined by the API models.

There must be one authoritative model/migration contract. Shared models should be packaged explicitly, and the worker should not own a competing ORM definition.

### F-03: Test environments are not reproducible

**Severity:** High
**Evidence:** current pytest output; `services/api/requirements.txt`, `services/worker/requirements.txt`, `services/llm-router/requirements.txt`, CI workflow.

The active environment lacks `python-jose` for API tests and `minio` for worker tests, while the requirements files declare them. This means dependencies were not installed consistently or the documented setup does not control the test interpreter. In addition, the LLM-router test module imports `services.llm_router...` when run from the service directory, causing an import-root failure.

CI must install dependencies from clean environments and run tests using a consistent package layout. Each service needs an import smoke test from the same working directory used by its Docker entrypoint.

### F-04: Frontend CI still cannot install deterministically

**Severity:** High
**Evidence:** `.github/workflows/ci.yml:29-32`, `apps/web/Dockerfile:9-10`.

CI and Docker both use `npm ci` and reference `apps/web/package-lock.json`, but the repository does not contain a lockfile. The Next.js standalone configuration is now present, so that sub-finding is resolved, but installation remains a hard blocker.

### F-05: Android build remains invalid

**Severity:** Critical
**Evidence:** `android/client/build.gradle.kts`, `android/client/app/build.gradle.kts`.

The Kotlin DSL files still contain Groovy constructs such as `id '...'`, single-quoted dependency declarations, and Groovy-style plugin/dependency syntax. The Android project inventory still lacks a verified `settings.gradle(.kts)` and Gradle wrapper. No clean APK build can be claimed.

### F-06: Core streaming endpoints still report success without doing the work

**Severity:** Critical
**Evidence:** `services/api/app/api/v1/endpoints/streaming.py:97`, `:138`, `:160`, `:182`, `:213`, `:247`, `:284`.

Offer, answer, candidate, input, copilot, and voice paths retain TODOs or placeholder responses. The API persists/returns session-shaped data but does not implement the required forwarding to Unity, Android, peers, or the LLM router. The advertised VR workflow remains nonfunctional.

### F-07: Refresh-token contract remains unimplemented

**Severity:** High
**Evidence:** `services/api/app/api/v1/endpoints/auth.py:151-157`.

The endpoint still returns HTTP 501. The documented authentication contract advertises refresh tokens, but clients cannot renew sessions or revoke/rotate refresh credentials.

## Expanded Findings

### Queue and job-processing contract

- API and worker each maintain their own queue implementation. This duplicates serialization, retry, status, and key conventions rather than exposing one shared queue contract.
- The worker queue has no demonstrated integration test against the API's enqueue format.
- The API generation endpoint changes project state after enqueueing, but failure to enqueue or worker rejection must be handled transactionally; otherwise projects can remain in `SPEC_GENERATING` without a durable job.
- Job payloads are ID-based, while worker tasks do not consistently verify tenant ownership before mutation.
- Retry/idempotency behavior is not proven for spec version creation, scene package upload, publish, or asset processing.

### Specification and generation integrity

- Worker generation assigns versions using `MAX(version) + 1`; this is unsafe under concurrent generation unless backed by a unique constraint and a transaction-safe retry strategy.
- `publish_scene_task` sets a project to `PUBLISHED` without verifying the supplied scene package exists, is ready, belongs to the project, references a valid spec, and is stored successfully.
- `generate_scene_task` accepts a spec by ID and project by ID but does not visibly enforce that the spec belongs to the project before generating.
- Asset processing marks assets ready despite the actual processing steps remaining unimplemented, allowing invalid artifacts into scene generation.
- Structured LLM output helpers can return an empty object after JSON parsing failure; downstream schema validation must reject this rather than treating it as a usable proposal.

### Authentication, tenancy, and authorization

- Registration still permits a caller-provided `organization_id`; membership in an existing organization needs an authenticated invitation/admin workflow.
- Project status updates accept arbitrary status values through the project patch endpoint. Lifecycle transitions should be controlled by trusted services and validated against the current state.
- Router provider, policy, usage, quota, cache-statistics, and cache-invalidation endpoints have no visible authentication/authorization dependency.
- Worker `/stats` is exposed without visible authentication and may disclose queue/worker state.
- Worker CORS remains wildcard with credentials enabled.
- Tenant predicates are present in many API project queries, but worker tasks frequently load records by bare ID. Queue payloads need tenant binding and ownership validation.

### Configuration and deployment

- API and worker still default to `DEBUG=True` and use bind-all interfaces in development entrypoints.
- Compose still provides default PostgreSQL and MinIO credentials.
- Android still enables cleartext traffic and defaults to emulator-only URLs (`10.0.2.2`).
- Unity scripts still default to localhost API, MinIO, and signaling endpoints.
- Compose defines infrastructure only; it does not provide API, worker, router, or frontend service definitions despite the project describing a Docker-based full local stack.
- MinIO bucket creation/bootstrap is not shown, so first-run asset uploads may fail unless an external manual step exists.

### Database and migrations

- API and worker still invoke `Base.metadata.create_all` at application startup while Alembic is also present.
- Worker-local ORM models do not represent the full migrated schema.
- The migration has no visible unique constraint on `(project_id, version)` for simulation specs.
- Several important lifecycle invariants are implemented only in Python endpoint logic, not enforced by database constraints or transactional state-transition services.
- Tests create/drop schema directly and do not validate `alembic upgrade head` from an empty database.

### Frontend contract and delivery

- The frontend dependency manifest contains a broad set of libraries, but no lockfile or installed dependency tree is available for validation.
- The API rewrite and image configuration remain localhost/MinIO-specific and are not environment-safe for LAN, staging, or production deployments.
- The visible frontend remains substantially smaller than the documented builder surface; no verified implementation was found for the complete prompt-to-spec-to-publish workflow, 3D preview, analytics, or manual editing experience.

### CI/CD and supply chain

- CI's API job requires PostgreSQL, Redis, and MinIO test services, but service provisioning must be verified before tests can pass in a clean runner.
- CI job names and commands need to be checked for parity: worker/router jobs install pytest but current local test imports fail; no successful clean-run evidence exists.
- Docker build tests do not include application startup/import smoke tests.
- The security workflow uses floating third-party action references such as `@master`; action versions should be pinned to immutable commits or trusted tags.
- The security scan must fail or gate merges on actionable critical findings rather than merely uploading SARIF.

### Android and Unity runtime integration

- Android signaling defaults use `ws://10.0.2.2:8080/ws`, while API configuration uses `ws://localhost:8000/v1/stream`; the clients and backend do not share a verified signaling contract.
- The Android client has no verified device authentication/session handshake tied to API stream sessions.
- Unity scripts use independent serialized endpoint defaults rather than a single deployment configuration.
- The Unity project lacks a verified build/scene/package load test in this environment.
- UVC hand tracking remains explicitly placeholder code and must stay feature-flagged and optional.

## Readiness Matrix

| Capability | Status | Current reason |
|---|---|---|
| Python syntax | Partial pass | Compilation passes, but imports/dependencies are not reproducible |
| API service | Blocked/unverified | Missing `python-jose` in active test environment; DB/integration unavailable |
| Worker service | Blocked | Missing `minio` in active test environment; root schemas not included in Docker context; model drift |
| LLM router | Syntax resolved, execution unverified | Test import root and dependency environment fail |
| Frontend | Blocked | Missing lockfile/dependencies; type-check cannot run |
| Web Docker image | Partial | Standalone setting fixed; install/build not verified |
| CI | Not passing/verified | Missing lockfile and clean service test execution |
| Database/migrations | Risky | `create_all` competes with Alembic; worker schema diverges |
| Authentication | Partial | Login/access tokens exist; refresh remains 501 |
| Generation pipeline | Blocked | Worker packaging, model, queue, and artifact contracts incomplete |
| Streaming | Not implemented end to end | Forwarding and copilot/voice paths remain placeholders |
| Android | Blocked | Invalid Gradle project and no device verification |
| Unity | Unverified/incomplete | No build/runtime integration verification |
| Production readiness | No | Critical execution, security, integration, and operational gaps remain |

## Priority Remediation

### Immediate blockers

1. Package shared schemas and authoritative ORM models so API and worker use the same installable interfaces.
2. Make all service tests runnable from clean environments with correct package roots and locked dependencies.
3. Add the frontend lockfile and make CI/Docker installation deterministic.
4. Repair Android Kotlin DSL/project structure and produce a clean debug build.
5. Implement real stream signaling and remove false-success placeholders.
6. Fix refresh-token rotation/revocation and organization membership authorization.

### Before a stakeholder demo

1. Make queue enqueue/dequeue/retry/idempotency behavior shared and integration-tested.
2. Enforce spec/project ownership and publish preconditions.
3. Make scene/asset storage and package loading verifiable with MinIO.
4. Provide a mocked-provider end-to-end generation test and a one-stream WebRTC smoke test.
5. Configure one LAN deployment profile shared by API, Unity, and Android.

### Before pilot or production

1. Remove insecure defaults and reject development secrets in staging/production.
2. Restrict all administrative endpoints and worker diagnostics.
3. Make Alembic the only production schema authority.
4. Add tenant-isolation, credit atomicity, audit, retry, and authorization tests.
5. Add health/readiness probes, structured error handling, metrics, tracing, and alerting.
6. Validate Unity/Android performance and thermal behavior on the target low-end devices.

## Acceptance Gates

The project should not be called execution-ready until all of these pass from clean environments:

- API, worker, and router imports from their Docker/runtime entrypoints;
- dependency installation from committed lockfiles/requirements;
- Python compile, lint, type-check, and all service tests;
- frontend lint, type-check, production build, and browser smoke test;
- `alembic upgrade head` against an empty PostgreSQL database;
- queue integration test between API enqueue and worker dequeue;
- tenant-isolation and authorization tests for all ID-based jobs/endpoints;
- generation/publish precondition and idempotency tests;
- actual Unity/API/Android signaling test;
- Android debug/release build and device smoke test;
- one concurrent WebRTC stream with gaze/controller/voice paths;
- security scan that gates critical findings.

## Limitations

- Docker Desktop, external databases, Unity editor, Android SDK/device hardware, and provider credentials were unavailable for this audit.
- Node and Python dependency environments were incomplete, so some failures are environment-confirmed rather than source-confirmed.
- The repository is not recognized as a Git worktree, so diff history and ignored-file policy could not be audited.
- No application code was changed during this follow-up audit; only this report was added.

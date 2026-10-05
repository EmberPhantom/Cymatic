# CYMATIC Codebase Audit

**Audit date:** 2026-08-19
**Repository:** `P:\Cymatic`
**Scope:** frontend, API, worker, LLM router, shared schemas, Docker/CI, Unity render server, Android client, tests, migrations, security, documentation, and end-to-end execution paths.

## Executive Verdict

CYMATIC is **not execution-ready, demo-ready, pilot-ready, or production-ready** in its current state.

The repository contains a broad architectural skeleton and many useful domain models, but core services do not currently form an executable pipeline. The most severe blockers are:

1. The LLM router contains a Python syntax error and cannot compile.
2. The API test suite cannot import the application from the repository root because package imports assume a different `PYTHONPATH`.
3. The worker references modules that do not exist in the worker service or in a declared shared package.
4. The frontend has no lockfile or installed dependencies, so CI's `npm ci` and local type/build checks cannot run.
5. The Android Gradle files use Groovy syntax in `.kts` files and the project lacks standard Gradle settings/wrapper files.
6. Streaming signaling, copilot, voice, refresh tokens, asset processing, and analytics contain explicit placeholders or TODO implementations.

The implementation status claims in `PROJECT_SUMMARY.md` substantially overstate operational completeness. The code is best described as an incomplete prototype/foundation requiring stabilization before a stakeholder demo that depends on the actual generation-to-VR path.

## Verification Performed

### Commands and results

| Check | Result |
|---|---|
| `python -m compileall -q services schemas` | **Failed**: syntax error in `services/llm-router/app/providers/litellm_client.py:247` |
| `python -m pytest services/api/tests services/worker/tests services/llm-router/tests -q` | **Failed during collection**: `ModuleNotFoundError: No module named 'app'` from API imports |
| `npm run type-check` | **Could not run**: `tsc` not installed; no dependencies are installed |
| `npm run build` | **Could not run**: `next` not installed; no dependencies are installed |
| `docker compose -f infra/docker/docker-compose.yml config` | Parsed successfully with obsolete `version` warning |
| `docker build -t cymatic-worker-audit ./services/worker` | **Could not run**: Docker Desktop Linux engine unavailable |
| Git status/history | **Unavailable**: configured workspace is not recognized as a Git repository |

The inability to run frontend and Docker execution checks is itself recorded as an environment/readiness gap, not treated as proof that every frontend or image defect is runtime-confirmed.

## Critical Blockers

### C-01: LLM router has a syntax error

**Severity:** Critical
**Evidence:** `services/llm-router/app/providers/litellm_client.py:247`
**Observed:** Python compilation reports `SyntaxError: expected 'except' or 'finally' block`.

The router cannot be imported or started. Any worker agent that calls it, and any CI job that compiles or type-checks it, is blocked. Fix the malformed exception/control-flow block, then add an import smoke test that imports `app.main` and the provider client.

### C-02: Worker service has broken module boundaries

**Severity:** Critical
**Evidence:** `services/worker/app/main.py:9`, `services/worker/app/tasks/generation.py:2-9`, `services/worker/app/agents/validation_agent.py:4`
**Observed:** Worker code imports `app.core.queue`, `app.models.*`, and `app.services.minio_client`, but the worker tree does not contain those modules. It also imports `services.api.app.services.spec_validator` directly.

The worker Dockerfile copies only `services/worker/app`, so these imports cannot be satisfied inside the worker image. The worker and worker tests also use inconsistent import roots (`app.*` versus `services.worker.app.*`). This breaks worker startup and generation execution.

Create an explicit shared package for database models, queue contracts, and schema validation, or make the worker depend on a correctly packaged API library. Do not solve this by copying arbitrary API source into the worker image; establish ownership and versioned interfaces.

### C-03: CI frontend installation is guaranteed to fail without a lockfile

**Severity:** Critical
**Evidence:** `.github/workflows/ci.yml:30-36`, `apps/web/Dockerfile:6-7`
**Observed:** CI uses `npm ci` and caches `apps/web/package-lock.json`, but no `package-lock.json`, `pnpm-lock.yaml`, or `yarn.lock` exists in the repository.

Both CI and the web Docker build are blocked before compilation. Generate and commit the lockfile using the chosen package manager, then keep CI and Docker aligned with that package manager.

### C-04: Android project is not a valid Kotlin Gradle project as written

**Severity:** Critical
**Evidence:** `android/client/build.gradle.kts:2-4`, `android/client/app/build.gradle.kts:1-3`, `android/client/app/build.gradle.kts:98`, `android/client/app/build.gradle.kts:116-120`
**Observed:** `.kts` files contain Groovy syntax such as `id '...'`, single-quoted dependency declarations, and Groovy-style `kapt`. No `settings.gradle(.kts)`, Gradle wrapper, or standard project entrypoint is present in the file inventory.

Android compilation is not execution-ready. Convert the files consistently to Kotlin DSL or rename/use Groovy build files consistently, add project settings and a wrapper, and verify a clean debug build.

### C-05: Production web Docker image expects unconfigured Next.js standalone output

**Severity:** High
**Evidence:** `apps/web/Dockerfile:19-22`, `apps/web/next.config.js:2-25`
**Observed:** The runtime stage copies `.next/standalone`, but `next.config.js` does not set `output: 'standalone'`. The image also assumes `public` exists.

The production image is likely to fail during the copy stage or lack the expected `server.js`. Configure standalone output and test the image, or change the Dockerfile to match the selected Next.js deployment mode.

## End-to-End Pipeline Findings

### API to worker job handoff

The API exposes generation endpoints and a Redis-backed queue abstraction, but the worker cannot import its queue/models/storage dependencies. The advertised flow `Create -> Generate -> Publish -> Stream` therefore stops before reliable worker execution.

The worker also calls `Base.metadata.create_all` at startup while the API has Alembic migrations. This creates two competing schema authorities and can cause drift between local, test, and production databases. Production services should use migrations as the schema authority and fail clearly when required migrations are absent.

### Specification-first behavior

The repository has Python and TypeScript simulation schemas, but the worker imports the root `schemas` package while the API and worker also maintain service-local models. There is no verified package/build step that guarantees the same schema version is available to every service. Generated TypeScript files and the claimed shared-package structure are not reflected in the file inventory.

Preserve the required flow `Agent Proposal -> Schema Validation -> Trusted Service -> State Change`, but make the shared schema package installable and test it from each service boundary.

### Generation and scene publishing

`services/worker/app/tasks/generation.py` contains generation handlers, but the imports are currently broken. The scene path also relies on MinIO and database models not present in the worker image. Asset processing marks assets ready while explicitly leaving thumbnail, LOD, conversion, and metadata processing as TODOs.

`publish_scene` changes project status to published without verifying that the referenced scene package exists, is ready, belongs to the project, or has passed validation. This violates the intended trusted-service state transition and can publish incomplete state.

### Streaming

`services/api/app/api/v1/endpoints/streaming.py` contains TODOs for signaling Unity, forwarding offers/answers/candidates, forwarding input, and routing events. Several endpoints return success-shaped responses such as `offer_received`, `answer_received`, and `input_received` without performing the forwarding operation.

Copilot and voice endpoints return placeholder responses rather than invoking the LLM router or Unity/Android event path. This means the documented VR interaction loop is not implemented end to end.

Unity defaults point to localhost (`EventBridge.cs`, `CopilotAgent.cs`, `RenderServer.cs`, `SceneLoader.cs`, `SignalingClient.cs`), and Android defaults point to `10.0.2.2`. These are development-only assumptions and do not describe a deployable LAN/device configuration.

### Authentication and authorization

`services/api/app/api/v1/endpoints/auth.py:151-157` explicitly returns HTTP 501 for refresh tokens. The README and project summary advertise refresh tokens, so the documented authentication contract is incomplete.

Registration accepts a caller-supplied `organization_id` without an authenticated organization-admin flow. A user can potentially join an existing organization by guessing an ID. Registration should create a new organization or require an authorized invitation/token for membership in an existing organization.

Project update accepts arbitrary status transitions and does not enforce lifecycle ordering. Publish and generation transitions need trusted service checks rather than user-controlled status mutation.

### Tenant and access-control review

Several project queries visibly scope by `organization_id`, which is a good foundation, but the audit could not establish complete coverage across every endpoint because worker models and imports are incomplete. The worker task queries shown in `generation.py` select by IDs without organization joins. Job payloads must be authenticated, tenant-bound, and checked against the owning project before state changes.

## Security Findings

### High: insecure development defaults can be deployed accidentally

`infra/docker/docker-compose.yml` defaults PostgreSQL and MinIO credentials to `cymatic` and `minioadmin`. Worker and API settings repeat these defaults. The Android manifest enables cleartext traffic, and the LLM router and worker use wildcard CORS with credentials enabled.

These defaults may be acceptable for isolated local development, but production startup should reject them, CORS should be explicit, and cleartext should be disabled in release builds. Secrets should be required through deployment configuration rather than silently defaulted.

### High: LLM router management endpoints have no visible authentication

The router exposes provider listing, routing policies, usage statistics, quotas, cache statistics, and cache invalidation under `/v1/router/*`. The shown router application does not add authentication or authorization middleware. These endpoints can disclose provider configuration and usage data and allow cache invalidation.

Protect administrative endpoints with service authentication and role checks; keep provider keys and sensitive routing details out of public health responses.

### Medium: raw passthrough is not a real passthrough

`services/llm-router/app/main.py:169-184` reads the incoming request body and headers but ignores them, then sends a hardcoded prompt to `gpt-3.5-turbo`. This is misleading behavior and can route requests outside intended task/sensitivity policy. Remove it or implement a validated, policy-aware passthrough.

### Medium: API configuration defaults to debug/reload

`services/api/app/core/config.py` defaults `DEBUG=True` and `API_RELOAD=True`, while binding to `0.0.0.0`. Production configuration must fail closed, disable docs/debug/reload, and ensure secrets and CORS are explicitly configured.

## Frontend Findings

The web app inventory contains a single main page and basic layout/styles, while the documented builder workflow describes prompt intake, clarification, spec review, manual editing, publishing, analytics, and 3D preview. The implementation surface visible in the repository does not demonstrate those workflows or API integrations.

The app declares React Query, Zustand, forms, and validation dependencies but no lockfile or installed dependency tree is present. The reported frontend status cannot be accepted until lint, type-check, production build, and an actual browser workflow are run.

The Next.js image configuration is limited to localhost/MinIO and the API rewrite defaults to localhost. Deployment configuration for LAN, staging, and production origins is not documented or validated.

## LLM and AI Pipeline Findings

- Router syntax failure blocks every LLM-backed feature.
- Worker LLM client has no lifecycle guarantee for its global `httpx.AsyncClient`.
- Structured-output helpers parse invalid JSON into `{}` instead of failing validation, which can allow downstream agents to operate on empty proposals.
- Router management endpoints lack visible access control.
- Provider routing and sensitivity policy require integration tests proving tenant-sensitive requests cannot fall through to free providers.
- Usage, quota, and credit accounting need atomicity/idempotency tests; the current audit did not find a demonstrated end-to-end billing invariant.
- Agent outputs must be validated before persistence or runtime mutation. Placeholder streaming endpoints currently bypass the meaningful trusted-service path.

## Unity Render Server Findings

The Unity tree contains scripts and project settings, but the file inventory does not show a complete scene, generated asset catalog, build configuration, or verified WebRTC signaling deployment. `Packages/manifest.json` and scripts require a Unity editor/build validation that was not available in this environment.

The render server uses hardcoded localhost backend, MinIO, and signaling defaults. The stream contract between API, Unity, and Android is not verified. Scene loading, package integrity, asset availability, and publish authorization need a real one-stream integration test.

Hand tracking is feature-flagged in documentation, but the Android UVC manager explicitly identifies USB camera enumeration as a placeholder. This should remain optional and must not be counted as implemented MVP functionality.

## Android Findings

- Build structure is incomplete and Kotlin DSL syntax is invalid as currently written.
- API and signaling URLs default to Android emulator-only addresses.
- Manifest permits cleartext traffic.
- No verified authentication/session bootstrap flow is shown for the Android client.
- WebRTC, IMU, gaze, controller, voice, and editing code require device builds and hardware tests; none were executable in this environment.
- Optional UVC/hand tracking must remain disabled by default and should fail gracefully when unavailable.

## Infrastructure and CI Findings

- Compose configuration parses, but uses `version: '3.8'`, which Docker reports as obsolete.
- Compose starts only PostgreSQL, Redis, and MinIO; it does not define API, worker, LLM router, or frontend services despite documentation describing a Docker-based local stack.
- Compose has no explicit dependency health conditions for the MinIO console and no bucket/bootstrap job for the application bucket.
- Docker images for Python services copy only their local service directories despite cross-service imports.
- CI's worker job does not run pytest despite its name and the project definition of done requiring tests.
- CI's LLM router job also does not run its test suite.
- CI's API tests expect a PostgreSQL test database but the workflow does not start PostgreSQL or create `cymatic_test`.
- CI's Docker build job can build images independently, but no container startup smoke test validates imports or health endpoints.
- The security scan produces SARIF but does not visibly fail the job on findings; secret scanning behavior should be confirmed and pinned rather than using floating third-party action refs such as `@master`.
- Makefile commands use Unix paths and shells (`.venv/bin`, `rm -rf`, `read -p`) while the stated primary environment is Windows/PowerShell. The documented commands are not cross-platform as written.

## Database and Migration Findings

- API and worker call `Base.metadata.create_all` on startup, bypassing Alembic as the authoritative migration path.
- Worker and API do not share the same model package, so metadata may differ.
- Generation version assignment uses a `MAX(version)+1` pattern with a row lock on a select expression; this should be replaced with a database-enforced unique constraint plus a transaction-safe allocation strategy.
- State transitions need database constraints and service-level validation.
- Tests use a PostgreSQL URL but do not provision the database in the repository test command or CI workflow.

## Documentation and Leftover-Code Findings

`PROJECT_SUMMARY.md` claims phases 0-10 are complete and calls the architecture production-ready, but the executable checks and source review contradict that status. The report should be treated as historical/aspirational until updated.

Other stale or incomplete areas include:

- refresh token TODO;
- streaming forwarding TODOs;
- copilot and voice placeholders;
- asset processing TODO;
- analytics aggregation TODO;
- Android settings TODO;
- UVC enumeration placeholder;
- unused or duplicated service-local/shared schema concepts;
- generated Python bytecode and benchmark/security reports in the repository inventory, which should be reviewed for source-control policy and freshness.

## Readiness Matrix

| Area | Status | Reason |
|---|---|---|
| API import/startup | Blocked/unverified | Root import path failed in test collection; runtime dependencies/database not validated |
| Worker startup | Blocked | Missing imported modules and broken package boundary |
| LLM router | Blocked | Python syntax error |
| Frontend development | Blocked/unverified | Dependencies/lockfile absent; `tsc` and `next` unavailable |
| Frontend production image | Blocked/unverified | Lockfile absent; standalone output mismatch |
| Database migrations | Risky | Startup `create_all` competes with Alembic |
| Docker Compose infrastructure | Partial | Compose parses; application services are absent and daemon was unavailable |
| CI | Blocked | Missing lockfile, missing test infrastructure, incomplete worker/router test execution |
| Android build | Blocked | Invalid Kotlin DSL/project structure |
| Unity build/streaming | Unverified and incomplete | No editor/runtime validation; signaling contract has placeholders |
| Authentication | Partial | Access tokens exist; refresh endpoint is 501; registration organization membership is unsafe |
| Generation pipeline | Blocked | Worker imports and storage/model boundaries fail |
| WebRTC streaming | Not implemented end to end | Forwarding endpoints are placeholders |
| Production readiness | No | Critical build, security, integration, and operational gaps |

## Prioritized Remediation Roadmap

### Immediate blockers

1. Fix the LLM router syntax error and add import/startup smoke tests.
2. Establish shared package boundaries for schemas, models, queue contracts, and storage interfaces.
3. Make worker imports consistent and build the worker image from a reproducible package layout.
4. Add and commit the frontend lockfile; run install, lint, type-check, and production build.
5. Repair the Android Gradle project and produce a clean debug APK.
6. Fix API test import configuration and provision PostgreSQL/Redis/MinIO in CI.

### Before any real demo

1. Implement authenticated refresh-token rotation/revocation.
2. Implement generation job status, retries, idempotency, tenant binding, and failure recovery.
3. Replace streaming success placeholders with actual API-Unity-Android signaling.
4. Route copilot and voice through the LLM router with validated action proposals.
5. Enforce publish preconditions: validated spec, ready scene package, ownership, and artifact integrity.
6. Add a single scripted end-to-end test from project creation through scene streaming.

### Before pilot/production

1. Remove insecure defaults and reject development secrets in staging/production.
2. Restrict CORS and administrative router endpoints.
3. Disable cleartext traffic in release Android builds and configure TLS/WSS.
4. Make Alembic the sole production schema authority.
5. Add observability for jobs, provider calls, stream lifecycle, credits, and tenant audit events.
6. Run dependency, secret, container, API authorization, and tenant-isolation tests in CI.
7. Validate Unity and Android performance on the target low-end devices under one-stream thermal limits.

## Recommended Acceptance Gates

The project should not be labeled execution-ready until all of the following pass:

- clean API, worker, and router imports from their deployed execution contexts;
- Python compile, Ruff, mypy, and pytest checks;
- frontend lockfile installation, lint, type-check, and production build;
- Docker image builds and health checks with application services included;
- Alembic migration from an empty database;
- authenticated tenant-isolation and refresh-token tests;
- generation pipeline test using a mocked LLM provider and real queue/storage contracts;
- end-to-end streaming signaling test;
- Android debug/release builds and device smoke test;
- Unity scene/package load and one concurrent WebRTC stream test;
- security scan that fails on actionable critical findings.

## Assumptions and Limitations

- The audit was performed against the files available under `P:\Cymatic` on 2026-08-19.
- No application source was modified other than this report.
- Docker Desktop was not running, so image build and container execution could not be verified.
- Node dependencies were not installed, so frontend compilation could not be verified.
- Unity editor, Android SDK/device hardware, PostgreSQL, Redis, MinIO, and external LLM provider credentials were not available for full integration execution.
- The workspace was not recognized as a Git repository, so changes/history and ignored-file state could not be audited.
- Findings marked as confirmed are supported by source inspection or command output; findings marked unverified require the named environment check before final classification.

# CYMATIC Current Investigation

**Investigation date:** 2026-08-20
**Compared against:** [`docs/10-follow-up-audit.md`](10-follow-up-audit.md)

## Current Verdict

CYMATIC is **not fully fixed and is not execution-ready**.

The repository has improved in several areas: Python syntax compilation passes, the frontend TypeScript check passes, a shared Python package has been introduced, Docker Compose now defines the application services, and the streaming API has gained forwarding/WebSocket code. However, the worker currently fails a direct startup import because required model modules are absent, the frontend production build fails on the local SWC binary, Compose requires a missing `.env`, and core authentication, streaming reliability, asset processing, analytics, and production-hardening issues remain.

## Verification Results

| Check | Result | Meaning |
|---|---|---|
| `python -m compileall -q services schemas` | Passed | Python syntax is currently valid |
| API pytest collection | Failed before tests | Missing `jose` in the active interpreter |
| Worker pytest collection | Failed before tests | Missing `minio` in the active interpreter |
| Worker `import app.main` | **Failed in source** | `app.models.project` cannot be imported because the module is absent |
| API `import app.main` | Failed without environment | Required `JWT_SECRET_KEY` is not supplied |
| Frontend `npm run type-check` | Passed | TypeScript currently type-checks with installed local dependencies |
| Frontend `npm run build` | Failed | Installed SWC binary is not a valid Win32 application |
| Docker Compose config | Failed | `P:\Cymatic\.env` is required by service `env_file` and is absent |
| Shared package import smoke test | Passed | `cymatic_shared`, models, schemas, and agents import successfully |
| Docker image build | Not run successfully | Docker Desktop engine was unavailable |
| Android build | Not verified | Android SDK/Gradle project remains incomplete |
| Unity build/runtime | Not verified | Unity editor and streaming runtime unavailable |

## Previous Findings: Current Status

| Finding from previous audit | Status | Evidence |
|---|---|---|
| LLM-router syntax error | **Resolved** | `compileall` passes |
| Shared package absent | **Resolved structurally** | `packages/cymatic-shared` exists and imports successfully |
| API/worker shared model boundary | **Still broken** | Worker tasks import missing local model modules instead of consistently using shared models |
| Worker Docker context/schema packaging | **Partially resolved** | Docker build context moved to repository root and shared package is copied; image build was not possible, and requirements contain a relative shared-package path that needs validation |
| Frontend lockfile/deterministic install | **Still unresolved** | CI/Docker use `npm ci`; no lockfile was found in the current file scan |
| Next standalone output | **Resolved** | `apps/web/next.config.js` sets `output: 'standalone'` |
| Frontend type-check | **Resolved locally** | `npm run type-check` passes |
| Frontend production build | **Still blocked** | Next build cannot load the installed Windows SWC binary |
| Android Gradle structure | **Still unresolved** | `.kts` files retain Groovy syntax and no verified wrapper/settings project is present |
| Refresh token implementation | **Still unresolved** | Endpoint remains HTTP 501 |
| Streaming forwarding | **Partially implemented** | HTTP forwarding and WebSocket signaling code now exists, but failures are swallowed and success is returned even when forwarding fails |
| Copilot/voice routing | **Partially implemented** | HTTP calls to router were added, but failure handling and runtime authorization are incomplete |
| Asset processing | **Still unresolved** | Worker still marks assets ready around TODO processing logic |
| Analytics aggregation | **Still unresolved** | Worker aggregation remains a placeholder |
| LLM-router wildcard CORS | **Resolved** | Router uses configured origins |
| Worker wildcard CORS | **Resolved structurally** | Worker now uses configured origins, but deployment policy remains unverified |
| Startup `create_all` vs Alembic | **Still unresolved** | API and worker sessions still call `Base.metadata.create_all` |

## Critical Findings

### C-01: Worker cannot start because generation imports absent model modules

**Severity:** Critical
**Evidence:** `services/worker/app/tasks/generation.py:5-8`; current worker model inventory contains only `__init__.py`, `asset.py`, and `scene_package.py`.

Direct execution of `python -c "import app.main"` from `services/worker` fails with:

```text
ModuleNotFoundError: No module named 'app.models.project'
```

The worker imports `app.models.project` and `app.models.simulation_spec`, but those modules are absent. The shared package exists, yet the task code has not been migrated consistently to it. This is a startup blocker, not merely a test-environment issue.

### C-02: Worker still has inconsistent model ownership

**Severity:** Critical
**Evidence:** `packages/cymatic-shared/cymatic_shared/models`, `services/worker/app/models`, and `services/worker/app/tasks/generation.py`.

The shared package now contains the authoritative-looking model set, while worker-local wrappers/files and task imports still disagree. The worker must use one model namespace and one `Base.metadata` contract. Until that is true, migrations, relationships, foreign keys, and runtime queries cannot be trusted.

### C-03: Docker requirements reference a relative shared package that may resolve outside the image

**Severity:** High; build verification pending Docker availability
**Evidence:** `services/api/requirements.txt:20`, `services/worker/requirements.txt:15`, API/worker Dockerfiles.

The Dockerfiles copy the shared package to `/app/packages/cymatic-shared`, then install requirements from `/app`. The requirements reference `../../packages/cymatic-shared`. That path resolves differently from the Dockerfile copy location and may point outside the image. The image build must be run from a clean Docker daemon and the requirement should use the already-installed package or a correct absolute/build-relative strategy.

### C-04: Frontend production build is still broken in the current environment

**Severity:** High
**Evidence:** `npm run build` output.

Next.js fails to load `@next/swc-win32-x64-msvc` because the installed native module is not a valid Win32 application. TypeScript passes, but production readiness requires a clean dependency install and successful build. This may be local dependency corruption or an architecture mismatch, but it is not resolved until a clean install/build succeeds.

### C-05: Compose requires a non-committed `.env` and cannot validate from the repository state

**Severity:** High for local execution
**Evidence:** `infra/docker/docker-compose.yml:60`, `:82`, `:103`; current command output.

`docker compose config` fails because `P:\Cymatic\.env` is missing. The project has `.env.example`, but Compose service `env_file` entries require `.env` directly. A first-run setup must create the file automatically or Compose must use a documented, validated fallback. Production secrets must still be explicitly supplied.

> **Resolution note (2026-09-12):** related shadowing fixed — `ENABLE_LOCAL_LLM: ${...:-false}` was removed from the `worker`/`llm-router` `environment:` blocks because Compose interpolates against `infra/docker/.env` (missing), not the root `.env`, and `environment:` wins over `env_file:`. The root `.env` via `env_file:` is now the single source of truth for that flag. First-run `.env` creation (`make setup`) is still required.

## Expanded Findings

### Streaming error semantics are unsafe

The streaming implementation now makes HTTP calls, but multiple handlers catch `(httpx.ConnectError, Exception)`, which is effectively a catch-all. Candidate and input paths can return `candidate_forwarded` or `input_forwarded` after any exception, including malformed payloads, timeouts, and server errors. This creates false-positive state for clients and makes operational failures invisible.

Forwarding failures must return an explicit 5xx/503 response or a durable pending state, and only successful downstream acknowledgements should produce a forwarded status.

### WebSocket signaling has an authorization gap

The WebSocket route accepts a `session_id` and client type from query parameters. A visible dependency on the authenticated user is absent in the signaling route. REST endpoints verify project organization for session creation, but a caller that knows or guesses a session ID may be able to attach to the signaling room. WebSocket authentication and ownership checks must occur before `accept()`.

### Worker has additional missing-model risk

`services/worker/app/tasks/generation.py` also imports `app.models.stream_session` and `app.models.runtime_event` in the analytics path, while those worker-local modules are absent. Even after the first project-model import is fixed, analytics execution will fail unless all model imports use the shared package consistently.

### Shared package and service configuration are coupled indirectly

The shared LLM agent client attempts to import `cymatic_shared.config` and falls back to `app.core.config`. The shared package has no visible `config.py`, so behavior depends on which service imports it and whether a service-local `app` package is on `sys.path`. Shared code should receive an explicit client/settings interface rather than dynamically discovering service modules.

### Authentication remains incomplete

- Refresh-token endpoint remains unimplemented.
- Access and refresh tokens are created with the same signing key and no visible refresh-token persistence/revocation store.
- Registration still accepts an organization ID from the request body; existing-organization membership needs invitation/admin authorization.
- Administrative router, worker statistics, and cache-management endpoints require explicit authentication and role checks.

### Generation and publishing remain insufficiently guarded

- Worker scene generation and publish handlers use ID-based payloads and need project/spec ownership checks.
- Publishing must verify that the scene package is ready, belongs to the project, references a valid spec, and has an accessible storage artifact.
- Spec version allocation still relies on `MAX(version) + 1` without a demonstrated database unique constraint on `(project_id, version)`.
- Asset processing continues to mark records ready without performing conversion, thumbnail, LOD, or metadata work.
- Analytics aggregation remains a placeholder.

### Database startup still bypasses migrations

Both API and worker database sessions call `Base.metadata.create_all`. This remains incompatible with a migration-authoritative production process and can hide missing migrations during startup. The worker and API must run the same Alembic schema or use a controlled migration job before application startup.

### CI and dependency reproducibility remain unproven

- CI still uses `npm ci` and references `apps/web/package-lock.json`, but no lockfile was found.
- Local frontend dependencies exist sufficiently for TypeScript but fail the native production build, indicating the environment is not clean/reproducible.
- API and worker tests fail before collection because required dependencies are absent from the active interpreter.
- Router tests need a stable package/import root consistent with CI and Docker.
- No clean CI run has demonstrated API, worker, and router test success with PostgreSQL, Redis, and MinIO provisioned.

### Android and Unity remain unverified

- Android still contains emulator-only API/signaling defaults and cleartext traffic configuration.
- UVC hand tracking remains placeholder code and must remain optional.
- Unity scripts retain localhost backend, MinIO, and signaling defaults.
- No Android APK, Unity build, scene load, or WebRTC device smoke test was executed.

## Readiness Matrix

| Area | Status | Reason |
|---|---|---|
| Python syntax | Pass | Compilation succeeds |
| Shared package imports | Pass | Shared models/schemas/agents import successfully |
| API startup | Blocked without configuration | Missing `JWT_SECRET_KEY` in current environment; full dependency/database startup unverified |
| Worker startup | **Blocked by source** | Missing `app.models.project` import |
| LLM router startup | Unverified | Syntax fixed; clean import/dependency check not completed |
| Frontend type-check | Pass | `tsc --noEmit` succeeds |
| Frontend production build | Blocked | Invalid SWC native binary |
| Docker Compose | Blocked from repository state | Required `.env` absent |
| Docker image builds | Unverified | Docker daemon unavailable |
| CI | Not ready | Lockfile and clean test execution remain unresolved |
| Authentication | Partial | Login works in code; refresh/revocation incomplete |
| Generation pipeline | Blocked | Worker startup/import failure |
| Streaming | Partial but unsafe | Forwarding added; errors are swallowed and WebSocket auth is unverified |
| Android | Blocked/unverified | Gradle/device validation incomplete |
| Unity | Unverified | No editor/runtime validation |
| Production readiness | No | Critical worker, build, configuration, security, and integration gaps remain |

## Required Next Gates

1. Remove all missing worker imports and make `python -c "import app.main"` pass in the worker image context.
2. Build API, worker, router, and web images from a clean Docker environment.
3. Commit a frontend lockfile and prove a clean `npm ci && npm run lint && npm run type-check && npm run build`.
4. Provision test services in CI and run all API, worker, router, and shared-package tests.
5. Make streaming failures observable and authenticate WebSocket signaling.
6. Implement refresh-token rotation/revocation and authorization for admin/diagnostic endpoints.
7. Enforce one shared ORM/migration contract and remove runtime `create_all` from production startup.
8. Run an end-to-end test from project creation through generation, scene publish, signaling, and one Android/Unity stream.

## Limitations

- Docker Desktop, Unity, Android SDK/device hardware, external databases, and LLM provider credentials were unavailable.
- The active Python environment lacks at least `jose` and `minio`, so service test suites could not execute.
- The active frontend dependency tree is present but the native SWC binary is invalid for the current Windows environment.
- The repository is not recognized as a Git worktree, so history and diff provenance could not be checked.
- No application code was changed during this investigation; only this report was added.

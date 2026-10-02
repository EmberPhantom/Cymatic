# CYMATIC Containerization Investigation

**Investigation date:** 2026-08-21
**Scope:** Local development and testing containerization

## Verdict

The Compose design has the right broad service shape, but it is **not currently build-ready or test-ready**.

PostgreSQL, Redis, MinIO, API, worker, LLM router, and web are represented, service DNS is used for most internal connections, and the web build context is correct. However, the LLM-router image has a context/Dockerfile mismatch that will prevent the image from building. Actual image builds could not proceed because Docker Desktop's Linux engine is unavailable on this machine.

## Verification

| Check | Result |
|---|---|
| `docker compose ... config` | Passed |
| `docker compose ... build --no-cache api worker llm-router web` | Not executed: Docker engine unavailable |
| API/worker Dockerfile context relationship | Correct: repository root context and service paths |
| Web Dockerfile context relationship | Correct: `apps/web` context |
| LLM-router Dockerfile context relationship | Broken |
| Internal API router URL | Correct: `http://llm-router:8001` |
| Database/Redis/MinIO service definitions | Present with healthchecks |
| Fresh database migration flow | Not provided/verified |
| Containerized test command | Not provided |
| Hot reload/source mounts | Not provided |

## Findings

### C-01: LLM-router image cannot build with the configured context

**Severity:** Critical

Compose uses the repository root as the LLM-router build context:

```yaml
context: ../..
dockerfile: services/llm-router/Dockerfile
```

But `services/llm-router/Dockerfile` contains:

```dockerfile
COPY requirements.txt .
COPY app/ ./app/
```

Those paths are relative to the repository root during a Compose build, where the expected files are under `services/llm-router`. The build should either use `context: ../../services/llm-router` or change the Dockerfile copies to `services/llm-router/requirements.txt` and `services/llm-router/app/`.

### C-02: Docker image builds are unverified because the engine is unavailable

**Severity:** High

`docker compose build --no-cache api worker llm-router web` failed before building because the Docker Desktop Linux engine named pipe was not available. Therefore no image has been proven to install dependencies, import the application, or start successfully.

### C-03: Compose does not provide a migration service or test profile

**Severity:** High

Compose starts PostgreSQL and then the API, worker, and router, but does not define an Alembic migration job, a test database, or a `test` profile. Local tests therefore depend on host-installed Python packages and external/manual infrastructure rather than a reproducible container command.

### C-04: Dependency readiness is incomplete

**Severity:** High

API waits for healthy PostgreSQL and Redis but only `service_started` for MinIO. Worker waits only for API and LLM-router startup. Startup ordering does not prove application readiness, database migrations, MinIO bucket availability, or router provider readiness. Use health-based dependencies and bounded retry behavior in service startup.

### C-05: Development workflow is not represented

**Severity:** Medium

The service images copy source into immutable images and run production-style commands. There are no bind mounts, development overrides, reload commands, or documented profiles for local iteration. This is acceptable for a production-like smoke stack but inefficient for local development.

### C-06: Container networking and host networking are mixed

**Severity:** Medium

API and worker use service DNS correctly for PostgreSQL, Redis, MinIO, and the router. The router itself still has localhost defaults for database, MinIO, and its own router URL, and frontend runtime/public URLs require different host-facing values than container-to-container URLs. The environment contract should explicitly separate internal URLs from browser/host URLs.

### C-07: Containerized test isolation is missing

**Severity:** Medium

No disposable test database/volume, test runner service, coverage output, or CI Compose profile exists. Existing test fixtures use `Base.metadata.create_all`, which bypasses the migration path. This prevents a reliable local command such as “start dependencies, migrate, run all tests, tear down.”

## Readiness Matrix

| Area | Status |
|---|---|
| Compose syntax | Ready |
| Service inventory | Structurally present |
| API/worker image definitions | Plausible, unverified |
| LLM-router image definition | Blocked |
| Web image definition | Plausible, web build currently blocked by SWC |
| Dependency health/readiness | Incomplete |
| Local development iteration | Incomplete |
| Containerized testing | Missing |
| Fresh database bootstrap | Unverified/not ready |
| Overall local container stack | **Not build-ready** |

## Required Fixes

1. Fix the LLM-router build context/Dockerfile path mismatch.
2. Start Docker Desktop and build every image with `docker compose build --no-cache`.
3. Add a migration job or documented migration command against a fresh PostgreSQL volume.
4. Add healthchecks and health-based dependencies for MinIO, API, and LLM-router where required.
5. Add a `docker-compose.dev.yml` override with source mounts and reload commands, or document the intended development workflow.
6. Add a `test` Compose profile with disposable PostgreSQL/Redis/MinIO dependencies and a test runner.
7. Define internal container URLs separately from browser-facing host URLs.
8. Verify clean startup, API health, worker health, router health, web health, migration success, and test execution from a clean checkout.

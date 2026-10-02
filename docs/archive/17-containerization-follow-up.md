# CYMATIC Containerization Follow-up

**Investigation date:** 2026-08-21  
**Compared with:** [`docs/16-containerization-follow-up.md`](16-containerization-follow-up.md)

## Verdict

Containerization has **materially improved** and the primary Compose design defects are largely addressed, but the stack is not fully verified for local development and testing yet.

The LLM-router Dockerfile now uses repository-qualified copy paths, eliminating the previously confirmed context mismatch. Compose now includes health-based dependency ordering for the API and worker, a setup-profile migration service, and a development override with bind mounts and reload commands. Docker builds reached real image build steps and no longer failed at the former LLM-router `COPY` paths, but the complete multi-image build did not finish within the available execution window. API test collection still fails in the active host environment because `python-multipart` is unavailable.

## Verification Matrix

| Check | Result | Status |
|---|---|---|
| Production Compose config | Passed | Resolved structurally |
| Development Compose config | Passed | Override resolves with bind mounts/reload |
| LLM-router context mismatch | Fixed | Dockerfile now copies `packages/cymatic-shared` and `services/llm-router/...` from root context |
| LLM-router Docker build start | Passed | Dockerfile/context loaded and build proceeded to dependency installation |
| Full image build | Incomplete | Build did not finish within the investigation window |
| API/worker readiness dependencies | Improved | Health conditions now cover PostgreSQL, Redis, MinIO, API, and router where declared |
| Migration workflow | Added | `migrate` service exists under `setup` profile; API image includes Alembic files/entrypoint |
| Development workflow | Added | `docker-compose.dev.yml` mounts API/shared/router code and enables reload |
| API test collection | Failed | `python-multipart` missing in active host environment |
| Worker test collection | Previously passed | 18 tests collected after test fixture changes |
| Containerized test runner | Still missing | No dedicated test service/profile |

## Prior Finding Status

| Prior finding | Status now |
|---|---|
| LLM-router Dockerfile/context mismatch | **Resolved structurally** |
| Docker engine unavailable | Resolved enough to start builds; complete build remains unverified |
| Missing API `email-validator` | Resolved in requirements; next collection blocker is `python-multipart` in the active environment |
| Migration service/profile | Added, but not executed against a fresh database |
| Dependency readiness ordering | Improved substantially |
| Development override/source mounts | Added for API, shared package, and router |
| Containerized test isolation | Still missing |

## Remaining Issues

### C-01: Full image build has not completed successfully

**Severity:** High

The build now passes the former LLM-router path boundary and reaches base-image/dependency installation, which confirms the context fix is syntactically viable. However, the complete `api`, `worker`, `llm-router`, and `web` build did not produce a recorded successful completion. Run each image independently or with a longer timeout and verify startup healthchecks.

### C-02: API host test environment remains incomplete

**Severity:** High

API collection fails with FastAPI's form-data guard because `python-multipart` is not installed in the current host interpreter. The requirement is present in `services/api/requirements.txt`, so the repository dependency declaration is improved, but clean isolated installation and test execution remain unverified.

### C-03: Migration behavior is duplicated and unverified

**Severity:** High

The API image entrypoint runs `alembic upgrade head` on every API container start, while a separate `migrate` service also runs migrations under the `setup` profile. This can be intentional, but it is redundant and has not been tested for concurrent startup, fresh volumes, downgrade/upgrade behavior, or failure recovery. Choose one authoritative migration strategy and verify it against a clean PostgreSQL volume.

### C-04: No containerized test runner exists

**Severity:** Medium

The setup profile migrates the database but does not run API, worker, router, shared, or frontend tests. The local workflow still lacks a reproducible command that starts disposable dependencies, runs tests inside matching images, exports coverage, and tears down safely.

### C-05: Development override coverage is incomplete

**Severity:** Medium

The development override mounts API, shared package, and router code, but does not provide equivalent source mounts/reload behavior for the worker or web frontend. Frontend and worker iteration still requires rebuilding or host-side development processes.

### C-06: Runtime configuration still mixes container and browser URLs

**Severity:** Medium

Internal service URLs now use Compose DNS in API and worker. Browser-facing `NEXT_PUBLIC_*` values and router defaults still include localhost-oriented values in the shared environment. Verify values from inside containers and from a browser on the host separately; do not use container DNS names in browser bundles.

## Readiness Matrix

| Area | Status |
|---|---|
| Compose syntax | Ready |
| LLM-router build context | Fixed |
| API/worker image definitions | Build started; completion unverified |
| Web image | Unverified; frontend production build remains a separate blocker |
| Dependency readiness | Improved, integration unverified |
| Migration bootstrap | Added, unverified |
| Development API/router workflow | Ready structurally |
| Development worker/web workflow | Incomplete |
| Containerized tests | Missing |
| Overall | **Improved but not fully verified/test-ready** |

## Required Exit Gates

1. Complete and record successful builds for all four application images.
2. Start the full stack on fresh volumes and verify every healthcheck.
3. Run migrations exactly once through the chosen authoritative path.
4. Add a containerized test runner/profile for API, worker, router, shared, and web checks.
5. Add worker and web support to the development override.
6. Verify internal versus browser-facing environment variables from both execution contexts.
7. Install declared dependencies in a clean host environment and rerun API collection and all service suites.

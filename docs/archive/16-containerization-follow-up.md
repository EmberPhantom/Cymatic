# CYMATIC Containerization Follow-up

**Investigation date:** 2026-08-21  
**Compared with:** [`docs/15-containerization-investigation.md`](15-containerization-investigation.md)

## Verdict

The containerization issues are **not fully fixed**.

Some application-level progress is confirmed: the LLM-router Pydantic private-field error is fixed, worker tests now collect successfully, Python compilation passes, and Compose configuration still resolves. The primary container build blocker remains unchanged: Compose gives the LLM-router repository-root context while its Dockerfile expects service-local paths. Docker image builds could not be verified because Docker Desktop's Linux engine is unavailable.

## Verification Matrix

| Check | Result | Status |
|---|---|---|
| `docker compose ... config` | Passed | Compose syntax resolves |
| API/worker build context | Structurally valid | Unbuilt |
| Web build context | Structurally valid | Unbuilt; web production build still fails locally on SWC |
| LLM-router build context | Still invalid | Dockerfile still uses root-relative `COPY requirements.txt` and `COPY app/` |
| Docker image build | Blocked | Docker Desktop Linux engine unavailable |
| Python compileall | Passed | Source compiles |
| Worker pytest collection | Passed | 18 tests collected |
| API pytest collection | Failed | Missing `email-validator` in active environment |
| LLM-router pytest collection | Did not complete in 30 seconds | Runtime/dependency test isolation remains unproven |
| Migration/test Compose profile | Missing | No migration or test service/profile exists |
| Dev override/source mounts | Missing | No dedicated development Compose override exists |

## Finding Status

| Prior finding | Status now |
|---|---|
| LLM-router Pydantic `_lock` error | Resolved in source: `PrivateAttr` is used |
| Worker test collection | Improved: collection passes |
| LLM-router Docker context mismatch | **Still unresolved** |
| Docker image build verification | Still blocked by unavailable Docker engine |
| Migration service/profile | Still missing |
| Readiness ordering | Still incomplete: API/worker use `service_started` for critical dependencies |
| Development override/hot reload | Still missing |
| Containerized test isolation | Still missing |

## Open Issues

### C-01: LLM-router image build context remains broken

**Severity:** Critical

Compose still declares:

```yaml
context: ../..
dockerfile: services/llm-router/Dockerfile
```

while the Dockerfile still contains:

```dockerfile
COPY requirements.txt .
COPY app/ ./app/
```

With repository-root context, those files are not at the required paths. Either change the Compose context to `../../services/llm-router` or qualify both Dockerfile copy paths with `services/llm-router/`.

### C-02: Actual container builds remain unverified

**Severity:** High

`docker compose build --no-cache api worker llm-router web` cannot reach the Docker Desktop Linux engine on this machine. No image has therefore been proven to install dependencies, import the application, or pass its healthcheck.

### C-03: API test environment still lacks a declared effective dependency

**Severity:** High

API test collection now fails when Pydantic constructs an `EmailStr` model because `email-validator` is not installed. The service requirements declare `pydantic`, but the active dependency set does not provide the optional email extra. Add `email-validator` explicitly or use `pydantic[email]`, then verify a clean install.

### C-04: Compose has no reproducible migration/test workflow

**Severity:** High

There is still no migration job, disposable test database, test profile, coverage output, or test runner service. Local verification depends on host-installed packages and manually managed services rather than a single reproducible Compose workflow.

### C-05: Critical dependencies are only partially readiness-gated

**Severity:** High

API waits for healthy PostgreSQL and Redis but only `service_started` for MinIO. Worker waits only for API and LLM-router startup. This can race database migrations, API readiness, router readiness, and MinIO bucket initialization.

### C-06: Local development ergonomics remain incomplete

**Severity:** Medium

The stack uses immutable image copies with production-style commands. There is no development override with bind mounts, reload settings, or a documented workflow for changing code without rebuilding images.

### C-07: Internal and browser-facing URLs are not cleanly separated

**Severity:** Medium

API/worker correctly use container DNS for internal services, while browser-facing frontend URLs and router defaults use localhost-oriented values. The environment contract should distinguish container-to-container URLs from URLs embedded into browser bundles.

## Readiness

| Area | Status |
|---|---|
| Compose syntax | Ready |
| Service inventory | Structurally present |
| API/worker Dockerfiles | Unverified |
| LLM-router Dockerfile | Blocked |
| Web Dockerfile | Unverified; app build blocked |
| Dependency readiness | Incomplete |
| Local development | Incomplete |
| Containerized testing | Missing |
| Fresh database bootstrap | Unverified |
| Overall | **Not build-ready for local development/testing** |

## Required Exit Gates

1. Fix the LLM-router context mismatch.
2. Install `email-validator` through the API dependency definition and rerun clean API collection.
3. Start Docker Desktop and build all images from a clean checkout.
4. Add migration and test Compose profiles with disposable data services.
5. Replace `service_started` dependencies with health/readiness gates where required.
6. Add a development override with source mounts and reload commands.
7. Verify service health, migrations, API-to-router calls, worker queue execution, and the complete test suite inside containers.

# CYMATIC Comprehensive Readiness Audit

**Investigation date:** 2026-08-22
**Compared with:** [`docs/17-containerization-follow-up.md`](17-containerization-follow-up.md)

## Executive Verdict

CYMATIC is **not yet execution-ready, test-ready, or production-ready**.

The repository has made substantial progress. Python compilation passes; worker test collection passes; Compose production and development configurations resolve; the LLM-router build-context defect is fixed; health-based dependencies, migration setup, test services, and development mounts have been added; and the API dependency file now includes `email-validator` and `python-multipart`.

The remaining blockers are material: the frontend production build still fails on the local Windows SWC binary; the host API test environment is not installed from the declared requirements; the Compose test services do not copy test files into their images; the migration service runs through an API entrypoint that already performs the same migration; full image builds and fresh-stack startup have not completed successfully; and important API streaming, WebSocket authorization, mobile, Unity, and integration paths remain unverified.

## Verification Matrix

| Gate | Result | Status |
|---|---|---|
| Python compileall | Passed | Source syntax is valid |
| Worker pytest collection | Passed: 18 tests | Collection fixed; full suite still unverified |
| API pytest collection | Failed in active host environment | `python-multipart` is unavailable despite being declared |
| LLM-router test collection/import | Not completed within the run window | Full router verification remains open |
| Web type-check | Passed | TypeScript checks |
| Web production build | Failed | Invalid `@next/swc-win32-x64-msvc` binary |
| Production Compose config | Passed | YAML and interpolated service graph resolve |
| Development Compose config | Passed | Bind mounts and reload commands resolve |
| Docker build start | Passed | Builds reached base-image and dependency-install steps |
| Complete Docker builds | Not proven | No recorded successful completion for all application images |
| LLM-router build context | Fixed | Dockerfile uses root-context-qualified paths |
| Migration profile | Added | Execution against fresh PostgreSQL is unverified |
| Container test services | Structurally incomplete | Test commands exist, but images omit `tests/` |
| Git staging hygiene | Previously passed | Worktree remains uncommitted |

## Resolution Status

| Earlier issue | Current status |
|---|---|
| Worker imports deleted local models | Resolved structurally |
| Worker import-time MinIO failure | Resolved for import smoke test |
| LLM-router Pydantic private field | Resolved with `PrivateAttr` |
| LLM-router Docker context mismatch | Resolved structurally |
| API/worker Compose service URLs | Improved; API and worker use `llm-router:8001` |
| Compose readiness ordering | Improved; health conditions now cover core dependencies |
| Migration setup | Added but not executed |
| Development API/router mounts | Added |
| Container test profiles | Added structurally but broken by missing test files |
| Frontend type-check | Resolved |
| Frontend production build | Still blocked |
| API/router clean dependency installation | Still unverified |
| Android Gradle wrapper/build | Still unverified/incomplete |
| Unity/WebRTC runtime | Still unverified |
| Streaming failure semantics | Still open |
| WebSocket authorization ownership | Still unverified |
| Persistent token revocation | Still open |

## Critical and High-Severity Findings

### C-01: Frontend production build remains blocked

**Severity:** Critical

`npm run build` fails in `apps/web` because the installed `@next/swc-win32-x64-msvc` native module is not a valid Win32 application. Type-checking passes, but the production artifact cannot be produced. The best solution is to reproduce the build in a clean Node 20 environment from `package-lock.json`, ensure the correct platform/architecture optional SWC package is installed, and make CI's production build the required gate.

### C-02: Compose test services do not contain the tests they run

**Severity:** Critical

`test-api` runs `pytest tests/` from the API image, but `services/api/Dockerfile` copies only `services/api/app/`, migrations, and entrypoint files. `test-worker` runs `pytest tests/`, but `services/worker/Dockerfile` copies only `services/worker/app/`. Neither image copies its test directory. The test containers will fail with a missing path or execute no tests.

**Best solution:** use dedicated test Dockerfiles/stages that copy `tests/`, or mount the service test directory in the test profile. Prefer a dedicated test stage so CI tests exactly the image dependency set without relying on host files.

### C-03: API test environment is not reproducible in the active interpreter

**Severity:** High

API collection fails because `python-multipart` is unavailable, even though it is declared in `services/api/requirements.txt`. Earlier collection also exposed missing optional/runtime packages. This proves only that the current host environment is incomplete; it does not prove a clean install works.

**Best solution:** create isolated per-service environments or run collection only inside the built API test image, then add a CI step that installs requirements from scratch and runs `python -m pytest --collect-only` before tests.

### C-04: Complete image builds and fresh-stack startup are unproven

**Severity:** High

Docker builds now pass the former LLM-router path boundary and reach real dependency installation, but no complete successful build for API, worker, router, and web was recorded. No fresh-volume `up`, healthcheck, migration, API request, queue job, or teardown cycle was completed.

**Best solution:** run each image build independently with a sufficiently long timeout, then run a clean-stack smoke script that waits for health, migrates once, checks all health endpoints, submits a test job, and tears down.

### C-05: Migration is duplicated between API startup and the migration service

**Severity:** High

The API image entrypoint runs `alembic upgrade head` on every API container start. The `migrate` Compose service uses the same API image and invokes `alembic upgrade head` as its command, so the entrypoint performs the migration and then the command requests it again. This is redundant and makes migration ownership unclear.

**Best solution:** choose one strategy. For local Compose, make `migrate` the authoritative one-shot service and use an API runtime image/entrypoint that only starts Uvicorn. For production, run migrations as a deployment job before API rollout, never concurrently from every API replica.

### C-06: Streaming endpoints still use broad failure handling

**Severity:** High

`services/api/app/api/v1/endpoints/streaming.py` still has broad `except Exception` handlers in render, chat, voice, and signaling paths. These can convert operational failures into fallback payloads that clients may interpret as successful operations.

**Best solution:** catch transport, timeout, HTTP status, validation, and database errors separately; return explicit 502/504/4xx responses; attach correlation IDs; and add tests for unavailable render/router services.

### C-07: WebSocket authorization remains unproven

**Severity:** High

JWT decoding exists for signaling, but the audit still lacks proof that the authenticated subject owns the requested stream session, belongs to the correct organization, and is authorized for the declared client type before messages are relayed.

**Best solution:** validate token type/expiry, load the stream session before accepting, compare user and organization ownership, enforce participant roles, and add negative tests for cross-tenant and unauthorized session access.

### C-08: Android, Unity, and WebRTC delivery gates remain unverified

**Severity:** High

The Android project still showed only wrapper properties/settings/build files in prior scans, not a complete executable wrapper/JAR. Android defaults use emulator-specific `10.0.2.2`, while Unity and render-server connectivity require environment-specific host addresses. No APK build, Unity build, headset connection, stereo output, or WebRTC session was executed.

**Best solution:** check in a complete Gradle wrapper, parameterize API/signaling URLs through build variants or settings, build the APK, and run a LAN smoke test against the Unity render server.

## Medium-Severity Findings

### C-09: Containerized tests still lack complete isolation and coverage output

Test profiles now exist, but they do not define a dedicated shared test image, coverage artifact volume, test database lifecycle, or a single orchestration command. Add a `test` profile that starts only disposable dependencies, runs migration, runs each suite, exports JUnit/coverage results, and exits with the aggregate status.

### C-10: Development override is incomplete

API/shared/router mounts are present, but worker and web source mounts/reload behavior are absent. Add worker source mounts with a development worker command and a web development service using the repository's package manager. Keep the production image path separate.

### C-11: Internal and browser-facing URLs are mixed

Compose uses container DNS correctly for server-side API/worker connections, but browser-bundled `NEXT_PUBLIC_*` values are set to `http://api:8000` and `ws://api:8000`, which are not resolvable from a browser running on the host. Use host-facing URLs for browser bundles and container DNS only for server-to-server calls, with separate environment variables.

### C-12: Refresh-token revocation is process-local

The refresh flow exists, but revocations are held in an in-memory set. Restarts and multiple API replicas lose revocation state. Move revocation/session state to Redis or a database table before production or horizontal scaling.

### C-13: Database tests bypass migrations

API fixtures call `Base.metadata.create_all`, which does not validate Alembic migrations. Replace this with a clean test database migrated to head, then truncate/reset between tests as appropriate.

### C-14: Broad exception use remains in worker/router internals

Several worker, router, and shared modules catch generic exceptions. Some are appropriate at worker boundaries, but provider, cache, asset, and pipeline paths need explicit classification, retry policy, and failure metrics so programming errors are not silently treated as ordinary provider failures.

### C-15: Uncommitted release surface remains large

The worktree contains application modifications, deletions, new Compose files, Dockerfiles, scripts, tests, and multiple audit reports. Git ignore/staging hygiene is good, but no final commit or push was performed. Review the full diff and run clean-checkout gates before publishing.

## Best Implementation Sequence

1. Fix the test image contents: add service tests to dedicated test stages or mount them in the test profile.
2. Remove duplicate migration ownership and run migrations against a fresh PostgreSQL volume.
3. Build all images independently, then run the full Compose smoke stack.
4. Create a clean dependency environment and run API, worker, router, shared, and frontend gates.
5. Fix the Next SWC build issue and make the production web build mandatory in CI.
6. Separate browser-facing and internal URLs and validate host/container access paths.
7. Harden streaming and WebSocket authorization with explicit error and tenant tests.
8. Complete Android wrapper/build and Unity/WebRTC LAN validation.
9. Add persistent token revocation and migration-backed integration tests.
10. Review, commit, and publish only the verified repository state.

## Final Readiness

| Area | Status |
|---|---|
| Source compilation | Ready |
| Compose syntax | Ready |
| Compose dependency graph | Improved, not runtime-proven |
| LLM-router build context | Fixed |
| Application image builds | Not fully verified |
| Containerized test execution | Broken until tests are included in images |
| Frontend production build | Blocked |
| Database migration lifecycle | Ambiguous/unverified |
| API/worker/router test suites | Not fully passing/proven |
| Android/Unity/WebRTC | Unverified |
| Security/session hardening | Not production-ready |
| Overall | **Not execution-ready or production-ready** |

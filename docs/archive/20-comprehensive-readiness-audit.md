# CYMATIC Comprehensive Readiness Audit

**Investigation date:** 2026-08-22  
**Compared with:** [`docs/19-comprehensive-readiness-audit.md`](19-comprehensive-readiness-audit.md)

## Executive Verdict

CYMATIC is **substantially improved but not yet execution-ready or production-ready**.

The critical Docker stage regression is fixed: Compose now targets `runtime` for normal API, worker, and migration services and `test` for test services. The API import failure is fixed because `require_admin` is now imported. API, worker, and LLM-router test collection all pass. Python compilation and Compose production/development configuration checks pass. The previous invalid Windows SWC binary warning is gone; the Next build now compiles and reaches static page generation.

The remaining release blocker is the web production build's standalone tracing step, which fails with an `ENOENT` for a generated client-reference manifest. The local audit invoked overlapping build/type-check processes, so the generated `.next` tree is not a clean-build result; this must be rerun sequentially from a clean generated directory. Full test execution, full image builds, fresh-stack startup, migrations, and runtime/device paths remain unproven.

## Verification Matrix

| Gate | Result | Status |
|---|---|---|
| Git status | Clean; branch aligned with remote | Repository changes are committed locally |
| Python compileall | Passed | Resolved |
| API pytest collection | Passed: 13 tests | Previous `require_admin` blocker fixed |
| Worker pytest collection | Passed: 18 tests | Collection fixed; full suite not run |
| LLM-router pytest collection | Passed: 13 tests | Previous Pydantic/collection blockers fixed |
| Web type-check | Failed during this run | `.next/types` was incomplete after overlapping build activity |
| Web production build | Partially passed | SWC/native compilation fixed; standalone traced-file copy failed |
| Production Compose config | Passed | Service graph and runtime targets resolve |
| Development Compose config | Passed | Dev mounts and commands resolve |
| Compose test/setup profiles | Structurally present | Full profile execution unverified |
| Docker runtime/test target selection | Fixed | Runtime services target `runtime`; test services target `test` |
| Full image build | Unverified | No complete all-image success recorded |
| Fresh stack/migrations/health | Unverified | No clean-volume integration run recorded |
| Android/Unity/WebRTC | Unverified | No device/runtime validation |

## Prior Finding Status

| Earlier issue | Current status |
|---|---|
| API/worker selecting test image stage | Resolved: explicit Compose targets exist |
| API `require_admin` import error | Resolved: import exists and API collection passes |
| LLM-router context mismatch | Resolved structurally |
| LLM-router Pydantic private field | Resolved structurally |
| Missing test files in test images | Resolved structurally: test stages copy tests |
| Frontend invalid SWC binary | Resolved in current run: build compiles without SWC failure |
| Frontend standalone production build | Still open: traced manifest copy fails |
| API/worker/router collection | Resolved for collection |
| Migration/profile execution | Still unverified |
| Streaming broad exception handling | Still open |
| WebSocket authorization | Still unverified |
| Android/Unity/WebRTC | Still unverified |
| Persistent token revocation | Still open |

## Critical and High-Severity Findings

### C-01: Clean frontend production build is not yet proven

**Severity:** Critical

The Next build now successfully compiles, lints/types, collects page data, and generates static pages. It then fails during standalone trace copying because a generated `page_client-reference-manifest.js` is missing under `.next/server`. The type-check command also saw missing `.next/types` files during overlapping build activity.

**Best solution:** remove the generated `.next` directory using the repository's normal clean-build procedure, run exactly one `npm run build` process, and rerun `npm run type-check` after the build completes. Ensure CI never runs build and type-check concurrently against the same `.next` directory. If the clean sequential build still fails, isolate the affected route/group and update Next configuration or dependency versions.

### C-02: Full service image builds and runtime startup remain unverified

**Severity:** High

Dockerfile targets are now correct, but no complete build of API, worker, LLM router, and web has been recorded, and no fresh-volume Compose startup has proven migrations, healthchecks, service DNS, queue processing, or API-to-router calls.

**Best solution:** build each target independently, inspect effective commands, start PostgreSQL/Redis/MinIO and migration setup on fresh volumes, start runtime services, wait on healthchecks, execute one API request and one worker job, then run the test profile.

### C-03: Test suites have only been collected, not executed end to end

**Severity:** High

API, worker, and router collection now passes, but collection does not validate database fixtures, Redis, MinIO, provider mocking, queue processing, migration compatibility, or assertion correctness. The worker suite previously showed infrastructure-dependent behavior and the API fixtures use a database setup path that needs migration verification.

**Best solution:** run the test profiles inside their target images with disposable dependencies, use deterministic provider mocks, migrate a fresh test database, and export JUnit/coverage artifacts.

### C-04: Migration ownership and startup behavior still need one authoritative path

**Severity:** High

Compose includes a `migrate` service and the API runtime image still has an entrypoint that runs Alembic before starting Uvicorn. This can cause duplicate migration attempts and makes production rollout semantics ambiguous.

**Best solution:** make the setup/migration job authoritative and remove automatic migrations from API replicas. Keep the runtime entrypoint limited to starting the service; make the migration job explicitly target the runtime image and verify it once against a clean database.

### C-05: Streaming failures can still be masked

**Severity:** High

Broad `except Exception` handlers remain in `services/api/app/api/v1/endpoints/streaming.py`. Unexpected failures may become fallback responses that look successful to clients.

**Best solution:** classify network timeout, connection, HTTP status, validation, and internal errors; return explicit 4xx/5xx responses; add correlation IDs and failure-path tests for unavailable render/router services.

### C-06: WebSocket authorization remains unverified

**Severity:** High

Token decoding exists, but session ownership, organization isolation, client-type authorization, expiry handling, and rejection before relay still lack end-to-end negative tests.

**Best solution:** load the stream session before accepting, compare token subject and organization, enforce client roles, reject unauthorized connections, and test cross-tenant/session access.

### C-07: Android, Unity, and WebRTC runtime delivery remains unverified

**Severity:** High

No complete Android wrapper/APK build, Unity render-server build, LAN signaling session, stereo output, or headset test has been recorded. Emulator defaults such as `10.0.2.2` do not validate physical-device networking.

**Best solution:** check in a complete Gradle wrapper, make API/signaling endpoints build-variant or settings-driven, build the APK, and run a LAN smoke test with the Unity renderer and Android client.

## Medium-Severity Findings

### C-08: Browser-facing and internal URLs require runtime validation

Compose server-side URLs use service DNS, while browser bundles require host-reachable URLs. The configuration now passes public URL build arguments, but no browser smoke test proves that the generated client can reach API/WebSocket/MinIO from the host.

### C-09: Database tests bypass the migration contract

API fixtures still use `Base.metadata.create_all`. Replace this with Alembic migrations on a clean test database so tests validate the schema shipped to containers.

### C-10: Refresh-token revocation is process-local

Revocation remains an in-memory set and is lost on restart or across replicas. Store revocation/session state in Redis or PostgreSQL before production scaling.

### C-11: Pydantic deprecation warnings remain

Worker/shared tests emit warnings for class-based Pydantic configuration and router tests emit `datetime.utcnow()` deprecation warnings. Convert to `ConfigDict` and timezone-aware UTC timestamps before dependency upgrades.

### C-12: Runtime operational observability is incomplete

Healthchecks exist, but no verified end-to-end metrics/log correlation covers migration failures, worker retries, provider circuit state, MinIO failures, WebRTC session failures, and test/profile results. Add structured readiness diagnostics and failure counters.

### C-13: GitHub/release verification remains incomplete

The worktree is clean, but the audit did not prove the current commit is pushed or that a clean checkout reproduces all gates. Run the complete CI-equivalent sequence from a fresh clone before release.

## Best Solution Sequence

1. Clean generated frontend artifacts and run one sequential `npm run build`; then run `npm run type-check`.
2. Build every Docker target independently and inspect runtime/test commands.
3. Remove duplicate migration ownership and validate Alembic on a fresh PostgreSQL volume.
4. Run the Compose test profile with disposable PostgreSQL, Redis, and MinIO services.
5. Execute the complete API, worker, router, shared, and frontend test/build gates.
6. Fix streaming error contracts and prove WebSocket tenant/session authorization.
7. Validate browser-to-container URLs from the host and container-to-container URLs internally.
8. Complete Android/Unity/WebRTC LAN validation.
9. Move refresh-token revocation to shared persistent storage and resolve deprecation warnings.
10. Reproduce all gates from a clean checkout, then push the verified commit.

## Final Readiness

| Area | Status |
|---|---|
| Python source compilation | Ready |
| API/worker/router test collection | Ready for collection only |
| Compose syntax and profiles | Ready structurally |
| Docker runtime/test targets | Fixed structurally |
| Full container builds | Unverified |
| Frontend production build | Blocked by standalone trace failure |
| Full test execution | Unverified |
| Migration lifecycle | Ambiguous/unverified |
| API streaming/security | Not production-ready |
| Android/Unity/WebRTC | Unverified |
| Overall | **Not execution-ready or production-ready** |

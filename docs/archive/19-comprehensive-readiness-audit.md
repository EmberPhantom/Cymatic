# CYMATIC Comprehensive Readiness Audit

**Investigation date:** 2026-08-22
**Compared with:** [`docs/18-comprehensive-readiness-audit.md`](18-comprehensive-readiness-audit.md)

## Executive Verdict

CYMATIC remains **not execution-ready, test-ready, or production-ready**.

The worktree is clean and the branch is one commit ahead of its remote. Several containerization improvements are present: runtime/test stages were added to the API and worker Dockerfiles, Compose has production and development profiles, health-based dependencies remain in place, and both Compose configurations parse successfully. Python compilation, frontend type-checking, and worker test collection also pass.

However, the latest Dockerfile changes introduced a critical stage-selection regression. The `test` stage is the last stage in both API and worker Dockerfiles, while normal Compose services do not select a `runtime` target. Normal API and worker images therefore inherit the test stage's command and test tooling instead of the intended service runtime command. In addition, API test collection now fails at import time because `analytics.py` references `require_admin` without importing it, and the frontend production build remains blocked by the invalid Windows SWC binary.

## Verification Matrix

| Gate | Result | Status |
|---|---|---|
| Git status | Clean; `main` ahead by one commit | Changes are committed locally, not confirmed pushed |
| Python compileall | Passed | Source compiles |
| Worker pytest collection | Passed: 18 tests | Collection only; full suite/runtime not proven |
| API pytest collection | Failed | `NameError: require_admin is not defined` in analytics endpoint |
| LLM-router collection/runtime | Not fully verified | No successful full suite recorded |
| Web type-check | Passed | TypeScript checks |
| Web production build | Failed | Invalid `@next/swc-win32-x64-msvc` binary |
| Production Compose config | Passed | Service graph parses |
| Development Compose config | Passed | Development override parses |
| API/worker test stages | Added | Tests are copied into stage images |
| API/worker runtime target selection | Broken | Compose does not select `runtime`; Dockerfile final stage is `test` |
| Migration profile | Present | Fresh database execution remains unverified |
| Full image build/startup | Not proven | No successful clean-stack startup recorded |

## Prior Finding Status

| Earlier issue | Current status |
|---|---|
| LLM-router Docker context mismatch | Resolved structurally |
| LLM-router Pydantic private field | Resolved structurally |
| Missing tests in test images | Resolved structurally, but stage selection is now wrong |
| Compose health dependencies | Improved and still present |
| Migration/test profiles | Present but not executed end-to-end |
| Development mounts | Present for API, worker, router, and web in resolved dev config |
| Frontend production build | Still blocked |
| API test collection | Regressed to source import failure |
| Worker collection | Passing |
| Streaming broad exception handling | Still open |
| WebSocket authorization | Still unverified |
| Android/Unity/WebRTC | Still unverified |
| Persistent refresh-token revocation | Still open |

## Critical Findings

### C-01: API and worker production services select the test image stage

**Severity:** Critical

Both `services/api/Dockerfile` and `services/worker/Dockerfile` define a `runtime` stage followed by a `test` stage. Because the test stage is the final stage, a build without `target:` resolves to `test`. Compose's `api` and `worker` services do not specify `build.target`.

Consequences:

- The API image inherits the test stage's `CMD ["pytest", ...]` rather than the intended Uvicorn command.
- The worker image inherits the test stage's pytest command rather than the worker Uvicorn command.
- Production services contain test dependencies and test files unnecessarily.
- The migration service and test services have ambiguous entrypoint/command behavior.

**Best solution:** make `runtime` the final Dockerfile stage and define a named `test` stage after it only when explicitly selected, or set `target: runtime` for normal services and `target: test` for test services. The more explicit and robust approach is to set `target: runtime` for `api`, `worker`, and `migrate`, and `target: test` for `test-api` and `test-worker`, then verify the effective image command with `docker inspect`.

### C-02: API import fails because `require_admin` is not imported

**Severity:** Critical

`services/api/app/api/v1/endpoints/analytics.py` imports `get_current_user`, `require_viewer`, and `require_creator`, but defines a route dependency using `require_admin`. API pytest collection fails before any test runs with:

```text
NameError: name 'require_admin' is not defined
```

**Best solution:** import `require_admin` from `app.core.dependencies`, add a focused module-import/API collection check to CI, and run the full suite after resolving all import errors.

### C-03: Frontend production build remains blocked

**Severity:** Critical

`npm run build` still fails because the installed Next SWC Windows binary is not a valid Win32 application. Type-checking passes, but the deployable web artifact is not proven.

**Best solution:** perform a clean Node 20 install from `package-lock.json`, verify Node architecture and optional native package selection, and make `npm ci && npm run build` mandatory in CI. Do not mark the web service ready based only on `tsc`.

### C-04: Full application image and fresh-stack verification is incomplete

**Severity:** High

Compose files parse and Dockerfiles are structurally improved, but no complete successful build and startup cycle has been recorded for all services. The runtime/test target regression must be fixed before build results are meaningful.

**Best solution:** build each target independently, inspect image entrypoints, start on fresh volumes, wait for healthchecks, run migrations once, exercise an API request and worker job, then run the test profile and tear down.

## High-Severity Findings

### C-05: Migration ownership remains ambiguous

The API image entrypoint runs `alembic upgrade head`, while a Compose `migrate` service also invokes Alembic. With stage selection currently ambiguous, the migration service may also inherit test behavior. Choose one authoritative migration job, preferably an explicitly targeted migration/runtime image, and remove automatic migration from every API replica.

### C-06: Containerized test execution is not yet proven

Test stages now copy `tests/`, which resolves the previous missing-file issue structurally. But test services must explicitly select `target: test`, while runtime services select `target: runtime`. Test execution still needs a clean database, Redis, MinIO, migration ordering, and exported test/coverage results.

### C-07: API streaming error handling is too broad

`services/api/app/api/v1/endpoints/streaming.py` continues to catch generic `Exception` across render, chat, voice, and signaling paths. Unexpected failures can be returned as fallback success-like responses.

**Best solution:** classify timeout, connection, HTTP, validation, and internal errors separately; return explicit status codes; log correlation IDs; and add failure-path tests.

### C-08: WebSocket session authorization remains unverified

JWT parsing exists, but no end-to-end negative tests prove session ownership, organization ownership, client-type restrictions, and rejection before message relay.

### C-09: API tests bypass Alembic migrations

Fixtures still use `Base.metadata.create_all`, so tests do not validate the migration chain. Use a clean test database migrated to head, then isolate test data through transaction rollback or controlled truncation.

### C-10: Android, Unity, and WebRTC paths remain unverified

No complete Android Gradle wrapper/APK build, Unity render-server build, LAN streaming session, stereo output check, or headset test has been recorded. Emulator defaults such as `10.0.2.2` are not a substitute for configurable LAN runtime endpoints.

## Medium-Severity Findings

### C-11: Browser-facing and internal URLs need separate contracts

Server-side Compose URLs use service DNS, while browser-facing `NEXT_PUBLIC_*` values must use host-reachable URLs. The resolved Compose configuration has improved build args, but this needs an actual browser test from the host and should use clearly named internal versus public variables.

### C-12: Refresh-token revocation is process-local

The refresh flow exists, but revocations stored in memory disappear on restart and are not shared across replicas. Use Redis or a database table before production scaling.

### C-13: Router/worker full tests and provider isolation remain unproven

Worker collection passes, but full execution with mocked providers, databases, Redis, MinIO, and queue behavior has not been demonstrated. Router tests also lack a recorded clean completion.

### C-14: Pydantic deprecation warnings remain

Worker/shared configuration emits class-based Pydantic configuration deprecation warnings. Replace legacy `class Config` blocks with `ConfigDict` before a future Pydantic upgrade turns warnings into failures.

### C-15: Local commit is not the same as GitHub readiness

The worktree is clean and one commit ahead of `origin/main`, but push status is unknown. Before publishing, verify the commit contents, run clean-checkout gates, confirm no local `.env` or generated artifacts are included, and push intentionally.

## Best Solution Sequence

1. Set explicit Docker build targets: `runtime` for API/worker/migrate and `test` for test services.
2. Import `require_admin` and add a fast API import/collection CI gate.
3. Rebuild all images and inspect their effective commands and entrypoints.
4. Run migrations once on a fresh PostgreSQL volume and start the full Compose stack.
5. Run the targeted container test profile with isolated service dependencies and coverage output.
6. Fix the Next SWC/native dependency installation and require a successful production build.
7. Replace broad streaming exception handling and add WebSocket tenant/session authorization tests.
8. Replace `create_all` test setup with Alembic-based database setup.
9. Complete Android/Unity/WebRTC LAN validation.
10. Move token revocation to persistent shared storage, resolve deprecations, then review and push the commit.

## Final Readiness

| Area | Status |
|---|---|
| Source compilation | Ready |
| Worker test collection | Ready for collection only |
| API import/test collection | Blocked |
| Compose syntax | Ready |
| Compose runtime image targets | **Blocked by stage regression** |
| Containerized tests | Structurally present, execution blocked |
| Frontend production build | Blocked |
| Migration lifecycle | Ambiguous/unverified |
| API streaming/security | Not production-ready |
| Android/Unity/WebRTC | Unverified |
| Overall | **Not execution-ready or production-ready** |

# CYMATIC Comprehensive Readiness Audit

**Investigation date:** 2026-08-22
**Compared with:** [`docs/20-comprehensive-readiness-audit.md`](20-comprehensive-readiness-audit.md)

## Executive Verdict

CYMATIC is **not yet execution-ready or production-ready**.

The previous Docker stage regression is fixed: Compose explicitly selects `runtime` for normal services and `test` for test services. The API import issue is fixed, and API, worker, and LLM-router test collection now passes. Python compilation and both production/development Compose configurations pass.

The main remaining blockers are now narrower and better isolated. Worker pipeline execution fails because the test fixture patches `cymatic_shared.agents.llm_client.call_llm_json`, while agents imported that function directly and continue calling a live LLM router that returns HTTP 500. The frontend no longer fails at SWC loading, but its standalone build still fails while copying a generated client-reference manifest. Full container builds, fresh-stack startup, migration execution, API/router full suites, and mobile/Unity/WebRTC runtime tests remain unproven.

## Verification Matrix

| Gate | Result | Status |
|---|---|---|
| Git status | Clean except current audit report | Prior implementation changes are committed |
| Python compileall | Passed | Resolved |
| API pytest collection | Passed: 13 tests | Import blocker fixed |
| Worker pytest collection | Passed: 18 tests | Collection fixed |
| LLM-router pytest collection | Passed: 13 tests | Collection fixed |
| Worker pipeline tests | Failed: 6 failed, 9 passed | Live LLM calls are not mocked at the symbols agents use |
| Web type-check | Failed during contaminated/incomplete `.next` state | Needs clean sequential run |
| Web production build | Compiles, then fails standalone tracing | Native SWC issue resolved; artifact still blocked |
| Production Compose config | Passed | Runtime target graph resolves |
| Development Compose config | Passed | Dev override resolves |
| Docker runtime/test target selection | Passed structurally | Full image startup unverified |
| Migration execution | Unverified | No fresh-volume run recorded |
| Android/Unity/WebRTC | Unverified | No device/runtime test |

## Prior Finding Status

| Earlier issue | Current status |
|---|---|
| API/worker test-stage selection | Resolved: explicit targets exist |
| API `require_admin` import | Resolved: API collection passes |
| LLM-router context/Pydantic blockers | Resolved structurally |
| Missing tests in test images | Resolved structurally |
| API/worker/router collection | Resolved |
| Frontend SWC binary | Resolved in current run |
| Frontend standalone build | Still blocked |
| Worker test isolation | **Still broken** |
| Migration ownership | Still ambiguous/unverified |
| Streaming error handling | Still open |
| WebSocket authorization | Still unverified |
| Android/Unity/WebRTC | Still unverified |
| Persistent token revocation | Still open |

## Critical and High-Severity Findings

### C-01: Worker tests call a live LLM router instead of the mock

**Severity:** Critical

`services/worker/tests/conftest.py` patches:

```python
cymatic_shared.agents.llm_client.call_llm_json
```

But agent modules import `call_llm_json` directly into their own module namespace. The patch does not replace those already-bound references. `tests/test_pipeline.py` therefore calls `http://localhost:8001/v1/chat/completions`; the current router responds with HTTP 500. Six pipeline tests fail, while nine pass.

**Best solution:** patch the symbol where it is used, for example:

```python
patch("cymatic_shared.agents.intake_agent.call_llm_json", new_callable=AsyncMock, ...)
patch("cymatic_shared.agents.clarification_agent.call_llm_json", new_callable=AsyncMock, ...)
patch("app.agents.architect_agent.call_llm_json", new_callable=AsyncMock, ...)
```

Prefer dependency injection of an LLM client at agent boundaries so tests can pass a deterministic fake without patching import paths. Add an assertion that no test opens a network connection, then rerun the full worker suite.

### C-02: Frontend production artifact still fails standalone tracing

**Severity:** Critical

The Next build now compiles, lint/type checks, collects page data, and generates static pages. It fails while copying `.next/server/app/(dashboard)/page_client-reference-manifest.js` into `.next/standalone`. Type-checking also reports missing generated `.next/types` when run against an incomplete output directory.

**Best solution:** remove generated `.next` output using the normal project clean procedure, run exactly one build process, and run type-check independently afterward. Ensure CI never runs build and type-check concurrently against the same output directory. If the clean build still fails, isolate the dashboard route group and verify the Next 14.2 standalone configuration and dependency versions.

### C-03: Full container builds and startup remain unverified

**Severity:** High

Compose and Dockerfile targets are structurally correct, but no complete build/startup record exists for all images. No fresh-volume cycle has verified migrations, healthchecks, API-to-router requests, worker queue execution, or test-profile exit status.

**Best solution:** build `api:runtime`, `worker:runtime`, `llm-router`, `web`, `api:test`, and `worker:test` independently; inspect effective entrypoints; start dependencies on fresh volumes; migrate once; run health and functional smoke checks; then run test services.

### C-04: API/router full test suites are not executed

**Severity:** High

Collection passing proves imports only. API tests still depend on PostgreSQL/Redis/MinIO fixtures and migration behavior. Router tests depend on provider/circuit-breaker behavior. Neither full suite has a recorded passing run in the current audit.

**Best solution:** execute suites inside their targeted test images with disposable dependencies and deterministic provider mocks. Export coverage and JUnit results in CI.

### C-05: Migration ownership remains ambiguous

**Severity:** High

The API runtime entrypoint runs Alembic before starting the API, while a dedicated `migrate` service also runs Alembic. This creates duplicate/racy migration behavior and complicates production rollout.

**Best solution:** make the migration job authoritative and remove migration execution from API replicas. Keep the API runtime entrypoint limited to service startup and run the migration profile explicitly before dependent services.

### C-06: Streaming errors can still be masked

**Severity:** High

Generic exception handlers remain in the streaming endpoints. Render/router failures can be returned as fallback responses instead of explicit failure status codes.

**Best solution:** classify connection, timeout, HTTP, validation, and internal errors; return explicit 4xx/5xx responses; log correlation IDs; and test unavailable upstream services.

### C-07: WebSocket session authorization remains unverified

**Severity:** High

JWT decoding exists, but ownership, organization isolation, client-role checks, and rejection before relay still lack end-to-end negative tests.

### C-08: Android, Unity, and WebRTC runtime delivery remains unverified

**Severity:** High

No complete Android wrapper/APK build, Unity render build, LAN signaling test, stereo output verification, or physical headset session has been recorded.

## Medium-Severity Findings

### C-09: Database fixtures bypass Alembic

API tests still call `Base.metadata.create_all`. Use Alembic migrations on a clean test database to validate the actual deployment schema.

### C-10: Browser and container URLs need an actual smoke test

Compose now emits host-facing `localhost` values for browser build arguments and service DNS values for server-side connections. This is directionally correct, but no browser smoke test proves API, WebSocket, and MinIO access from the host.

### C-11: Refresh-token revocation is process-local

Revocation remains an in-memory set and is lost across restarts/replicas. Move it to Redis or PostgreSQL before production scaling.

### C-12: Time/deprecation cleanup remains open

The codebase still uses `datetime.utcnow()` extensively and emits deprecation warnings. Migrate to timezone-aware UTC timestamps and Pydantic `ConfigDict` before upgrading dependencies.

### C-13: Observability and operational smoke coverage are incomplete

Healthchecks exist, but no verified metrics/log correlation covers migration failure, provider errors, worker retry/lock behavior, MinIO failures, or WebRTC session failure. Add structured readiness diagnostics and failure counters.

### C-14: GitHub release verification is incomplete

The implementation worktree is clean, but the final audit report is untracked and a clean-clone/CI-equivalent run has not been proven. Review the final diff, commit the report intentionally, and verify push status separately.

## Best Solution Sequence

1. Fix worker mock patch targets or inject a fake LLM client; require zero network calls in unit tests.
2. Clean `.next` and run one sequential frontend build, followed by type-check.
3. Build every Docker target independently and inspect effective commands.
4. Remove automatic API startup migrations and use one authoritative migration job.
5. Run a fresh-volume Compose smoke stack and execute the complete container test profile.
6. Run API, worker, router, shared, and frontend checks with coverage in CI.
7. Harden streaming failures and prove WebSocket tenant/session authorization.
8. Replace `create_all` test setup with Alembic-based setup.
9. Validate browser URLs, Android, Unity, and WebRTC over the intended LAN path.
10. Move token revocation to persistent shared storage, resolve time deprecations, and publish from a clean checkout.

## Final Readiness

| Area | Status |
|---|---|
| Python compilation | Ready |
| API/router/worker collection | Ready for collection only |
| Worker pipeline execution | Blocked by live LLM calls |
| Compose syntax and targets | Ready structurally |
| Full container builds/startup | Unverified |
| Frontend production artifact | Blocked by standalone trace failure |
| Full test suites | Unverified/not passing |
| Migration lifecycle | Ambiguous/unverified |
| Streaming/security | Not production-ready |
| Android/Unity/WebRTC | Unverified |
| Overall | **Not execution-ready or production-ready** |

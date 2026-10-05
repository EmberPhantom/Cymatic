# Phase 11 Baseline (2026-10-01, base `18ef6a0`)

## Git
- HEAD: `18ef6a0 feat(llm-router): integrate APInex provider`
- Dirty (pre-existing, not touched by Phase 11): `.env.example`, android InputManager/Models/VRActivity/WebRTCManager, web Dockerfile + auth/builder/stream pages + EntityEditor + hooks + api.ts, compose yml/dev, shared project model, api specs/streaming/config, llm-router config, worker config, unity RenderServer/Signaling/EventBridge/SetupScene. Plus untracked `apps/viewer/`, `errors.ts`, `scene_packages.py`, `test_viewer.py`.

## Gate results
- `docker compose -f infra/docker/docker-compose.yml config --quiet`: PASS
- `py_compile` api/worker/router config: PASS
- Settings load (`JWT_SECRET_KEY` dummy, dev): PASS api
- Dockerfiles: `test` stage already copies `tests/` (api/worker/router) — C-02 already resolved.
- `migrate` service owns Alembic; api/worker `CMD` is uvicorn only — C-05 already resolved.
- Web URLs: build args default `localhost` (browser), `API_INTERNAL_URL=http://api:8000` (server) — C-11 already resolved.

## Fix applied in Phase 11 WS-1
- `services/api/app/core/config.py` + `services/worker/app/core/config.py`: `_ENV_FILE parents[3]` → `parents[4]` with container fallback (matches llm-router). Reason: `services/<svc>/app/core/config.py` is 4 levels below repo root; old value resolved to `services/.env` and never loaded root `.env` on host.

## WS-2/WS-3 static verification (2026-10-01, no docker daemon)
- API collect: 35 tests (incl. `test_stream_ws_tenant_and_revoked`, `test_stream_offer_render_unavailable`, `test_input_forward_failure_is_not_reported_as_success`, `test_auth_refresh_and_revoke`, `test_rbac_matrix`, `test_cross_tenant`) — PASS collect.
- Worker collect: 46 items — PASS collect. Router collect: 20+ (cache key sensitivity/provider/org, breaker lock, quota Lua, sanitize/truncate, STT/TTS caps) — PASS collect.
- Full `pytest` run blocked: API suite timed out after 120s waiting on DB/Redis; `docker ps` fails (Docker Desktop daemon not running: `npipe/.../dockerDesktopLinuxEngine` missing). Live integration requires: start Docker Desktop, then `docker compose -f infra/docker/docker-compose.yml up -d --build`, then `--profile test run --rm test-api/test-worker/test-llm-router` per `docs/22-mvp-local-runbook.md`.
- Code review: `streaming.py:681-799` WS-auth already strict (access-type, revocation via Redis, session ownership `user_id`, active user, org match); `security.py:39-91` revocation already Redis-backed DB4 with jti + loop-aware client (C-07/C-12 resolved); `jobs.py:15-58` ownership fail-closed (IDOR guard); `projects.py:144-154` status transition guard.

## WS-2/WS-3 LIVE results (2026-10-01, docker running)
- Infra: `up -d --build` green — postgres/redis healthy, `migrate` exit 0 (fresh PG),
  api :8000 + worker :8002 + llm-router :8001 + web :3000 + viewer :8090 all healthy.
- `quay.io/minio` pulls 401 on this network → local-only override
  `infra/docker/docker-compose.s3mock.yml` swaps `minio` for `motoserver/moto:latest`
  (same service name; MinIO SDK verified against it). Production keeps real MinIO.
- Container suites: llm-router **62 passed**, api **35 passed**, worker **46 passed**
  (coverage 63% ≥ 50% gate).
- Test fixes (no prod weakening): test passwords `testpass123`→`testpass12345`
  (policy `min_length=12`); new `admin_auth_headers` fixture — plan approve correctly
  requires `require_admin` (was 403 for creator fixture).
- Live E2E (real LLM keys: groq/openrouter/nim/apinex): register 201 → login 200 →
  project 201 → intake 200 (grounded questions) → plan 200 → generate-spec 202 →
  **completed ~30s, spec_id 3** → validate **valid:true** (perf warnings kept) →
  scene **completed, `orgs/5/projects/4/scenes/spec_3_v1.cymatic`** → publish
  **completed, status published**.
- Streaming without render server: session 201 with presigned package URL;
  offer/input → explicit **503 Render server unavailable** (no silent success).
- Finding: `validate-spec` returns synthetic `validate_<id>_<n>` job_ids that 404 on
  `/v1/jobs/{id}/status` poll after completion window — harmless (validate itself 200),
  follow-up: return inline result or persist job record.

## E2E re-verification (2026-10-02, clean api rebuild, debug code reverted)
- Full real-estate loop **18/18 ALL PASS**: intake (6 grounded questions) → clarify
  (typed answers incl. 1100.0 sqft normalization) → asset PUT+complete+listed →
  plan draft (+403 approve gate for creator) → spec completed → spec fetch 200 with
  balcony/warm reflected → validate → scene `.cymatic` → publish → view 200 →
  stream session 201.
- Mystery 401s root-caused: **test-script bug** — token passed positionally into the
  `body` slot (`call("GET", url, tok)`), so no Authorization header was sent.
  Server-side instrumented logging proved `has_auth_header:false`; server correct,
  no backend change needed. `dependencies.py` debug code fully reverted (no diff).
- Regression on final tree: api **35**, worker **46** (cov 63%), router **62** — all pass.
- Note: `127.0.0.1:8000` on this host is held by a VS Code utility process
  (connection blackhole); always use `localhost` (::1 → wslrelay → docker) or LAN IP.

## Next (hardware-gated, user-side)
- WS-4/5: Unity `BuildScript` + APK + same-LAN 1-stream perf (≥30fps, <150ms e2e, <45°C).
- WS-6 deferred: Tailwind4/TS7/ESLint10, Redis PubSub multi-replica, PID thermal.
- WS-7: `docs/06-roadmap-tasks.md` Remaining list refresh + demo rehearsal.

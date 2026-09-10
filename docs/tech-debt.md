# CYMATIC — Tech Debt & Audit Register — 2026-09-07

**Baseline:** `main` @ `b3cb79b` (P0+HIGH+UX+Optimization via #67 #68 #69 #70). **Open PRs:** 0.

**Scope:** 6-agent audit (2026-09-07) — `apps/web`, `services/api`, `services/worker`, `services/llm-router`, `infra/docker`, `unity`, `android` — **~170 findings (18 P0, 45 HIGH, 107 M/P/L)**. P0+HIGH+UX core merged; this register tracks remaining **MEDIUM/LOW** for follow-up.

**Legend:** `P0` block, `H` high, `M` medium, `L` low. `File:Line` verified.

---

## 1. UX Frontend — `apps/web` — Remaining

**Done in #70:** queryKeys canonical, builder reducer, dashboard AlertDialog, SpecViewer a11y, streaming 20Hz, vitest 5, next 16.3.4 build green.

**Remaining:**
- `apps/web/src/app/(dashboard)/layout.tsx:55` `M` — Hamburger `aria-expanded` + focus-trap `Tab` loop + `Esc` + `body overflow` — *fixed in 70* (keep).
- `apps/web/src/app/(dashboard)/projects/[id]/builder/page.tsx:60` `M` — 9 `useState` → `useReducer` done; persist `sessionStorage` + `?run_id=` done.
- `apps/web/src/types/index.ts:23` `M` — `payload_json: Record<string,any>` → `unknown` + Zod.
- `apps/web/next.config.js:15` `M` — duplicate `Permissions-Policy` vs `middleware.ts:41` ( `camera=()` vs `camera=(self)` ) — reconcile to `camera=(self)` for voice.
- `apps/web/tailwind.config.js:4` `M` — content includes `lib/hooks/stores` (120ms) — trim to `app/components`.
- `apps/web/src/app/page.tsx:24` `M` — `<Link><Button>` invalid — use `Button asChild`.
- `apps/web/src/components/ui/button.tsx:9` `L` — `cva` already, keep.
- **Follow-up (deferred):** Tailwind `3.4.0` → `4.3.3` (`@tailwindcss/postcss` + `@import "tailwindcss"` + `border-border` safelist), `typescript 5.9.3` → `7.0.2` (needs `typescript-eslint` + `eslint-config-next` flat), `eslint 8.57.1` → `10.9.1` flat (`eslint.config.mjs`).

---

## 2. Backend `services/api` — Remaining

**Done in #69:** `Exception` handler `HTTPException` re-raise, `health` timeout, `metrics` 503, `ProjectStatus` enum, `send_to_client` membership, `editing` `deepcopy` + `limit(1)`, `assets` `sanitize` + `flag_modified`, `analytics` SQL `SUM/COUNT`, `dependencies` `type access`, `security` `jti`, `rate_limit` sliding `ZSET` per `org/user`.

**Remaining (MEDIUM/LOW):**
- `services/api/app/main.py:21` `M` — `structlog` only `JSONRenderer` when `LOG_FORMAT==json`; add `TimeStamper`, `MergeContextVars`, `add_log_level`.
- `services/api/app/main.py:29` `M` — `REQUEST_COUNT/LATENCY` never incremented → add `PrometheusMiddleware`.
- `services/api/app/main.py:62` `M` — middleware order `CORS` outermost (currently last added = outermost, OK but comment confusion).
- `services/api/app/core/config.py:6` `M` — `.env` `parents[3]` → `parents[4]` (worker/llm-router also).
- `services/api/app/core/config.py:25` `M` — insecure defaults `localhost/minioadmin` not rejected in prod → validator.
- `services/api/app/services/minio_client.py:159` `M` — `get_presigned_url` `method` param now branches (`PUT`→`presigned_put_object`) — done.
- `services/api/app/api/v1/endpoints/streaming.py:575` `M` — `SignalingManager` in-memory `dict` not Redis PubSub → breaks >1 replica (MVP single-stream OK, k8s later).
- `services/api/app/api/v1/endpoints/projects.py:143` `L` — client `status` `published` bypass → restrict to `require_admin`.
- `services/api/app/api/v1/endpoints/jobs.py:9` `M` — `job_id` guessable, no tenant check → add `organization_id` in payload check.
- `services/api/requirements.txt:5` `M` — `bcrypt 5.0` + `passlib 1.7.4` mismatch → pin `bcrypt==4.0.1` or `argon2`.

---

## 3. Worker & Generator — `services/worker` — Remaining

**Done in #69:** `architect` `8000` tokens + `ValidationError` catch, `composer` `deepcopy`, `domain_expert` units, `asset` LOD/budget dedup, `checkpoint` atomic `/data`, `real_estate`/`heritage` parity, `tasks` advisory lock.

**Remaining (MEDIUM):**
- `services/worker/app/core/config.py:7` `M` — `_ENV_FILE parents[3]` → `4`; `LLM_TIMEOUT 5.0` dead; `WORKER_CONCURRENCY` now used? still single loop (future `Semaphore(4)`).
- `services/worker/app/pipelines/real_estate.py:288` `M` — `stage_outputs` key vs `architect` `spec.model_dump` still stores full spec 50KB×8 → 400KB checkpoint; TTL missing.
- `services/worker/app/pipelines/checkpoint.py:27` `/data` vs `/tmp` now via `CHECKPOINT_DIR`, atomic `mkstemp` done.
- `services/worker/app/services/minio_client.py:15` `M` — sync `Minio` still blocking `asyncio.to_thread` added but `PoolManager` not shared.
- `cymatic_shared/schemas/simulation_spec.py` `M` — triple duplication (`packages/shared`, `worker/app/schemas`, `schemas/`) — shim added but root `schemas/` still drifting.

---

## 4. LLM Router — `services/llm-router` — Remaining

**Done in #69:** `/v1/*` `Depends(verify_api_key)+rate_limit`, cache `sensitivity:provider:org` + `SCAN`, breaker `asyncio.Lock` + herd semaphore, quotas Redis Lua + `monthly_cost`, explicit model `sensitivity` check, `STT/TTS` caps, `sanitize`.

**Remaining (MEDIUM):**
- `services/llm-router/app/providers/litellm_client.py:75` `M` — `ChatCompletionRequest.messages: list[dict]` no `max_items`/`role` enum → add `Field(max_length)`.
- `services/llm-router/app/routing/engine.py:304` `M` — fallback still `GROQ free` for unknown combos → harden to `OPENAI/gpt-4o` paid-only.
- `services/llm-router/requirements.txt:1` `L` — `>=` not `==` → pin `==` for reproducible build.

---

## 5. Infra / Redis / Docker — Remaining

**Done in #69:** `docker-compose.yml:18` `appendonly yes` + `maxmemory 512mb volatile-lru` + `7 DB split` (`REDIS_URL` per service) + `restart`/`mem_limit`/`healthcheck`, `Dockerfile` `appuser` + `libc6-compat` + cache mounts, `.hadolint`/`.gitleaks` narrowed, `Makefile` `down -v`.

**Remaining (LOW):**
- `infra/docker/docker-compose.dev.yml:1` `M` — `PYTHONPATH /app:/app/packages/cymatic-shared` done but `--reload-dir` polling still 5-10s WSL2.
- `scripts/benchmark.py:1` `M` — `aiohttp` fallback to `httpx` done.

---

## 6. Unity — Remaining

**Done in #69:** `RenderServer` `/ws` + single-stream guard, `StereoCameraRig` `DrawTexture` + `GetTemporary`, `WebRTC` `Unity.WebRTC`, `SceneLoader` whitelist, `Copilot` `AuthToken`, `Signaling` `16k` fragment, `PerformanceManager` `Awake` vs `Start`.

**Remaining (MEDIUM):**
- `unity/render-server/Assets/Scripts/PerformanceManager.cs:175` hysteresis `5s cooldown` added but `HistorySize 60→180` still short for thermal (needs PID).
- `unity/render-server/Assets/Materials/CymaticShaders.shader:20` `LOD 200→100` done but still `Standard` not `Mobile/Diffuse` for baked.
- `unity/render-server/Packages/manifest.json:14` `com.unity.webrtc 3.0.0-pre.8` deprecated + `netcode` `+20MB` unused — remove for MVP.

---

## 7. Android — Remaining

**Done in #69:** `minSdk 34`, `isMinify true`, `arm64` only, `jvmTarget 17`, `AndroidManifest` camera `false` + storage/location removed, `ControllerManager` brace, `HandTracking` `handednesses`, `WebRTC` `sdpMid`, `ApiClient` duplicate.

**Remaining (MEDIUM):**
- `android/client/app/build.gradle.kts:25` `bundle` splits `enableSplit true` + `shrinkResources` done, `feature_handtracking` dynamic `README.md` stub.
- `android/client/app/src/main/java/com/cymatic/client/sensor/SensorFusion.kt:70` `150Hz→55Hz` throttled, `VRActivity` double sensor `100Hz` removed, `WebRTC` host candidates, `Audio` jitter `Channel 50→10`, `Voice` `1.1 req/s` batch.
- **Follow-up:** `network_security_config.xml:3` `10.0.0.0/8` cleartext → limit to `10.0.2.2` debug.

---

## 8. Roadmap

**Done:** P0 (queue atomic, single-stream, compile) + HIGH (security, persistence) + UX (builder/dashboard/spec) + Optimization (bundle `turbopack.root` + `optimizePackageImports`, Docker cache, Unity hysteresis, Android thermal) — merged `1448c90` + `b3cb79b`.

**Next (optional):**
- `chore/tailwind4` — `3.4.0 → 4.3.3` + `TS 7` + `eslint 10` flat (needs `typescript-eslint` support).
- `fix/medium-ux` — `payload_json unknown` + Zod, `confirm→Dialog` remaining, `a11y` `aria-live` gaps.
- `fix/low-infra` — `scripts/generate_openapi` `PYTHONPATH`, `Makefile` `docker-nuke` docs.

**Verification on `b3cb79b`:**
`tsc 0`, `vitest 4/4 v5`, `next build 7/7`, `ruff 0 x3`, `mypy 0 (api 44/worker 31/shared 30/llm-router 14)`, `docker compose config 0`, `gradle syntax green`.


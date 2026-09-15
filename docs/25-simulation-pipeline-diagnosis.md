# 3D Simulation Generation Pipeline — Diagnosis Report

**Date:** 2026-09-14 (UTC)
**Scope:** end-to-end unknown failure, Docker-first + local fallback, cloud keys configured
**Stack observed:** `infra/docker/docker-compose.yml` (api:8000, worker internal :8002, llm-router:8001, postgres, redis, minio, web:3000)
**Verdict:** Pipeline is **broken in live Docker**, but **unit tests pass with mocks**. Root cause is LLM-router routing/fallback, not DB/queue/MinIO/schema.

---

## 1. Complete flow (verified in code)

```
POST /v1/projects/{id}/intake
  services/api/app/api/v1/endpoints/specs.py:119 process_intake()
  -> GenerationRun ready_for_spec / needs_clarification
POST /v1/projects/{id}/clarify
  specs.py:228 process_clarification_answers()
POST /v1/projects/{id}/generate-spec -> Job spec_{run_id} queue "spec"
  services/worker/app/tasks/generation.py:24 generate_spec_task()
  -> services/worker/app/pipelines/real_estate.py / heritage.py (8 stages):
     intake -> clarification -> research -> architect -> composer
     -> domain_expert -> asset_selection -> validation
  -> architect: services/worker/app/agents/architect_agent.py
     create_spec_slm (if ENABLE_LOCAL_LLM) -> create_spec_llm (cloud) -> create_spec_fallback (template)
  -> validate_simulation_spec -> SimulationSpec VALID -> run spec_ready 60%
POST /v1/projects/{id}/generate-scene -> queue "generation"
  generation.py:233 generate_scene_task(): select_assets -> generate_scene_package
  -> MinIO orgs/{org}/projects/{id}/scenes/spec_{spec}_v{ver}.cymatic + sha256 + size verify
POST /v1/projects/{id}/publish -> publish_scene_task: ready + valid spec + MinIO artifact
```

Shared contracts: `schemas/simulation_spec.py` + `packages/cymatic-shared/cymatic_shared/{schemas/simulation_spec, agents/llm_client, queue, services/minio_client}`.
Router: `services/llm-router/app/{routing/engine.py, providers/litellm_client.py, schemas/providers.py, main.py}`.

---

## 2. Evidence (Docker logs + live probes + tests)

### 2.1 Stack health (2026-09-14 ~13:20 UTC, after `up -d`)
- `postgres`, `redis`, `minio`, `api`, `llm-router`, `worker`, `web` all `healthy`.
- `migrate` exited 0. API `/health` db+redis healthy. Worker `/health` (via `exec worker curl localhost:8002/health`) shows all 6 handlers registered, `running:true`.

### 2.2 Historical logs (before restart, 2026-09-13/14)
- Worker `generate_spec_completed project_id=1 spec_id=3`, `generate_scene_completed scene_package_id=3`, `publish_scene_completed` — one full pass **via template fallback**, not LLM:
  - `architect_llm_failed_unexpected error='LLM router 502'` → `architect_fallback_completed domain=heritage entities=1`
  - Earlier: `architect_fallback_completed domain=heritage entities=4` (project 5).
  - Scene had only 1–4 entities, `asset_selection_completed assets=3`.
- Router at 13:05:42–45: `spec_generation` → `openai/gpt-4o-mini` → `Missing credentials OPENAI_API_KEY` → 502 ×3.
- Router at 13:03:59: Groq `json_validate_failed`; at 13:04:29: clarification 429 Too Many Requests (Groq rate limit 30 rpm).
- API logs: intake/clarify/generate-spec 200/202, no 5xx — API itself healthy.

### 2.3 Live reproduction (this session, project 6, run_61fe9ad7)
- `.env`: `GROQ_API_KEY=***SET***`, `OPENROUTER_API_KEY=***SET***`, `NVIDIA_NIM_API_KEY=***SET***`, `OPENAI_API_KEY=<empty>`, `ENABLE_LOCAL_LLM=true`, `OLLAMA_URL=http://ollama:11434`, but **no `ollama` container running**.
- Router `/health`: `providers.all true`, `local_enabled:true`, `cloud_keys: groq true, openrouter true, openai false, nim true` — note `openai:true` in providers despite key false.
- Direct probe `POST /v1/chat/completions` (default routing):
  - `spec_generation/internal` → 502 `Ollama sidecar unreachable`
  - `intent_extraction/internal` → 502 same
  - `clarification/internal` → 502 same
- Explicit model probe:
  - `model=openai/gpt-oss-20b` → **OK via groq** `{"a":1}`
  - `model=gpt-4o-mini` → 502 (misleading ollama hint, actually missing OpenAI key)
- E2E:
  - `intake` → 200 but `analyser_mode:fallback`, `confidence:0.125`, 6 missing fields.
  - `clarify` → 200 but `analyser_mode:fallback`, `ready_for_generation:false`, `completion:0.25`.
  - `generate-spec` → 202 queued → worker `intake_llm_failed LLM router 502` → `clarification_llm_failed LLM router 502` → job `completed` with `status:awaiting_clarification, questions:[], completion:0`; run stuck `needs_clarification progress:0`.
  - Pipeline never reaches architect/composer/scene. User sees “not working”.

### 2.4 Tests (all pass — they mock LLM)
- `test-llm-router`: **55 passed**.
- `test-api`: **31 passed** (intake/clarify/generate-spec mocked, plan, streaming, security).
- `test-worker`: **46 passed** (pipeline/agents with mocked LLM, SLM hybrid, checkpoint).
- Conclusion: mocks hide live routing failure. No test asserts “LOCAL down → GROQ fallback” or “OPENAI key missing → skip OPENAI”.

---

## 3. Root causes (ranked)

### P0-1: LOCAL preferred with no fallback when Ollama down
- **Files:** `services/llm-router/app/routing/engine.py:81-96,108-133,217-241` (INTENT/CLARIFY/SPEC policies prefer `phi-3-mini-3.8b-q4` via LOCAL), `services/llm-router/app/providers/litellm_client.py:416,516,626,708,791` (fallback only on `ValueError/OSError/HTTPException`), `services/llm-router/app/main.py:172-186` (all other exceptions → 502).
- **Mechanism:** `ENABLE_LOCAL_LLM=true` + ollama container absent → `litellm.APIConnectionError: Cannot connect to host ollama:11434` → not in caught tuple → no retry with `fallback_profile` (e.g. `openai/gpt-oss-20b`) → immediate 502. All default `intent/clarify/spec` calls fail.
- **Why flaky:** after 5 LOCAL failures circuit opens (`circuit_breaker.py:71`), `route()` skips LOCAL and Groq works (observed 13:01–13:05). After restart circuits reset to CLOSED, LOCAL selected again → total outage.
- **Proof:** default probes 502 LOCAL; explicit Groq probe OK; worker retries `ConnectError: LLM router 502` then `intake_llm_failed`.

### P0-2: Providers marked enabled without API keys; spec_generation pinned to broken OPENAI
- **Files:** `services/llm-router/app/schemas/providers.py:99-273` (`enabled=True` defaults), `engine.py:53-67` (only LOCAL flag applied), `engine.py:355-456` (`route()` never checks `settings.*_API_KEY`).
- **Mechanism:** `OPENAI_API_KEY` empty yet `providers.openai=true`. SPEC_INTERNAL preferred `phi-3-mini` miss → fallback `gpt-4o-mini` → OPENAI selected (first in allowed order with that model) → `Missing credentials` 502. `route()` fallback/last-resort loops check `allowed_providers` order `[LOCAL, OPENAI, NVIDIA, GROQ, OPENROUTER]`, so OPENAI shadows working GROQ `openai/gpt-oss-120b` and NVIDIA `nemotron-3-ultra`. Same for any empty-key provider.
- **Proof:** 13:05 logs show 3× OPENAI 502, then template fallback with 1 entity; explicit `gpt-4o-mini` probe fails.

### P1: Degraded fallback blocks UX
- Intake fallback confidence 0.125, clarify `ready:false`, `generate_spec_task` returns `awaiting_clarification` with `questions:[]`, run `needs_clarification progress:0`. Frontend has no actionable next step. Not a crash, but pipeline appears hung.
- Secondary: Groq `json_validate_failed` + 429 (30 rpm limit) need retry/backoff; already partially handled but contributes to flakiness.

### Not root causes (ruled out)
- Postgres/Redis/MinIO/queue/MinIO upload/size-verify: healthy; historical scene upload `size=3815` succeeded.
- Spec schema/validation/composer/asset logic: unit tests pass; historical `validation_completed score=0.97 valid=True`.
- API auth/project/plan/streaming: `test-api` 31 passed; live register/login/project/intake HTTP 200/202.

---

## 4. Fix suggestions (minimal, spec-first, AGENTS.md-compliant)

### Immediate (P0, no schema change)
1. **Gate providers by key + Ollama reachability** — `services/llm-router/app/routing/engine.py`
   - In `_apply_local_llm_flag()` also verify Ollama reachable (or lazily mark LOCAL unhealthy on `APIConnectionError`); add `_apply_api_key_flags()` that sets `providers[GROQ/OPENROUTER/NVIDIA/OPENAI/SARVAM].enabled = bool(settings.<KEY>)`.
   - Keep `env_file ../../.env` as single source of truth (do not re-add `${...:-false}` interpolation that shadows it).
   - Affected modules: `services/llm-router/**`. Validation: `/health` must show `openai:false` when key empty; `local:false` when ollama down.
2. **Fix fallback exception coverage** — `services/llm-router/app/providers/litellm_client.py:416`
   - Catch `Exception` from `litellm.acompletion` for fallback purposes (still log + record circuit failure), or explicitly include `litellm.exceptions.{APIConnectionError, BadRequestError, InternalServerError, RateLimitError, Timeout}`. Current `except (ValueError, OSError, HTTPException)` lets all litellm errors bypass `policy.max_retries` fallback rotation.
   - Add test: LOCAL down (mock `litellm.acompletion` raising `APIConnectionError`) → routes to GROQ fallback; OPENAI key missing → skips OPENAI to NVIDIA/GROQ.
3. **Correct SPEC_INTERNAL policy order** — `engine.py:108-133`
   - When LOCAL disabled/unhealthy and OPENAI disabled (no key), preferred should resolve to a keyed provider (e.g. GROQ `openai/gpt-oss-120b` or NVIDIA `nemotron-3-ultra`), not `gpt-4o-mini` on disabled OPENAI. Minimal: keep profiles but ensure `route()` filters disabled providers *before* preferred/fallback/last-resort loops (covered by fix 1).
4. **Ops unblock (no code):**
   - Either `docker compose -f infra/docker/docker-compose.yml --profile local up -d ollama && docker exec <ctr> ollama pull phi3:mini` **or** set `ENABLE_LOCAL_LLM=false` in `.env` to force cloud routing until Ollama is provisioned.
   - Set `OPENAI_API_KEY` **or** accept GROQ/NVIDIA path; do not leave SPEC fallback pointing to empty OpenAI.

### Short-term (P1, UX + robustness)
5. **Truthful fallback signals** — `packages/cymatic-shared/cymatic_shared/agents/{intake_agent, clarification_agent}` + `services/api/app/api/v1/endpoints/specs.py`
   - When `analyser_mode==fallback`, surface `warning: llm_unavailable, fallback_used` in intake/clarify responses and `GET generation-runs`; ensure `awaiting_clarification` returns non-empty `questions` (currently `[]` in live repro) so builder can progress.
6. **Groq resilience** — already has `response_format json_object` + repair in `cymatic_shared/agents/llm_client.py`; add bounded retry on `json_validate_failed`/429 with jitter, and consider OpenRouter/NVIDIA as clarification fallback (currently GROQ/OPENROUTER/OPENAI).
7. **Regression tests (must add):**
   - `services/llm-router/tests/test_router.py`: `test_spec_generation_skips_providers_without_keys`, `test_local_down_falls_back_to_groq` (mock litellm error types).
   - `services/worker/tests/test_pipeline.py`: live-router-down → fallback template still yields valid spec (already covered) **plus** run status transitions to `needs_clarification` with questions (currently missing).
   - Run: `docker compose --profile test run --rm test-llm-router/test-api/test-worker` (all currently green with mocks; new tests must fail before fix, pass after).

### Out of scope (do not change for this fix)
- Unity/Android/WebRTC, hand-tracking/UVC flags, multiplayer/plugins, billing — per AGENTS.md forbidden/flagged areas.
- No hardcoded keys; no removal of validation (`validate_simulation_spec` stays mandatory); no `create_all` vs Alembic change in this fix.

---

## 5. Test plan / Definition of Done
- [ ] `/health` shows `openai:false` when key empty, `local:false` when ollama down.
- [ ] Default `spec_generation/intent/clarification` succeed via GROQ/NVIDIA with LOCAL down and OPENAI empty (live probe script).
- [ ] Full E2E: register → project → intake (`analyser_mode:llm`) → clarify (`ready:true`) → generate-spec (`spec_ready`) → generate-scene (`scene_ready`) → publish (`published`).
- [ ] `docker compose --profile test run --rm test-llm-router/test-api/test-worker` green, including new fallback tests.
- [ ] Docs updated (this report + runbook note on `ENABLE_LOCAL_LLM` vs ollama profile).
- [ ] No regression in gaze/controller/voice contract; feature flags respected.

## 6. Risks / follow-ups
- Groq free-tier 30 rpm/6k tpm will still 429 under load → need quota-aware routing + backoff (observed once).
- Template fallback masks LLM outage (1-entity scenes ship as “success”) → add `generation_notes` + `analyser_mode` to frontend so degraded output is visible.
- Circuit threshold 5 means ~5× user-visible 502s before auto-fallback after each restart; fix 1–2 removes dependence on circuit to mask config errors.
- Secrets: `.env` contains live `GROQ_API_KEY`; do not commit; rotate if exposed.

---

## Appendix: commands used
```powershell
docker compose -f infra/docker/docker-compose.yml ps --all
docker compose -f infra/docker/docker-compose.yml logs --tail=2000 worker | Select-String "error|failed|architect|502"
docker compose -f infra/docker/docker-compose.yml logs --tail=500 llm-router
Invoke-RestMethod http://localhost:8001/health | ConvertTo-Json -Depth 5
docker compose -f infra/docker/docker-compose.yml --profile test run --rm test-llm-router  # 55 passed
docker compose -f infra/docker/docker-compose.yml --profile test run --rm test-api          # 31 passed
docker compose -f infra/docker/docker-compose.yml --profile test run --rm test-worker       # 46 passed
python3 probe_router.py; python3 probe_e2e.py  # live repro: fallback + stuck needs_clarification
```

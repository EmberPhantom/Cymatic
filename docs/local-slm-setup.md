# Local <3B SLM Setup (Offline Spec Generation)

**Status:** Optional, feature-flagged (`ENABLE_LOCAL_LLM`, default `false` per `AGENTS.md`). Cloud CI is unaffected when off.

**Goal:** Generate full simulations on an 8GB RAM, no-GPU LAN box using `phi-3-mini-3.8b-q4` (~2.3GB, `q4_k_m`) via an Ollama sidecar, while planning/questions keep using Qwen on Groq for best reasoning.

## Architecture

```
intake/clarify (qwen-qwq-32b @ Groq, fallback qwen-2.5-72b @ OpenRouter)
  -> research (offline dict)
  -> architect (LOCAL phi-3-mini q4, temp 0.2, 2048 tok)
      -> on failure: cloud gpt-4o-mini -> template fallback
  -> composer / domain / asset / validation (offline) -> ScenePackage
```

The LLM router treats `LOCAL` as priority-5 provider for `SPEC_GENERATION` (+`VALIDATION`) at all sensitivity levels — local inference never leaves the box, so tenant-sensitive/regulated data is safe with it. Free cloud providers stay blocked for sensitive data.

## Hardware

- 8GB RAM, no GPU (CPU-only). Budget: phi-3 q4 ~2.3GB + Redis 0.5GB + Postgres 0.5GB ≈ 3.2GB.
- Concurrency is capped at 2 parallel local inferences (`_MAX_CONCURRENT_LOCAL`) to avoid OOM.

## Quickstart (LAN box)

```bash
cp .env.example .env
# in .env:
ENABLE_LOCAL_LLM=true
OLLAMA_URL=http://ollama:11434   # host-local dev: http://localhost:11434

# Start stack + Ollama sidecar (profile-gated, no effect on default compose)
docker compose -f infra/docker/docker-compose.yml --profile local up -d --build

# Pull the model once (~2.3GB, persisted in ollama_data volume)
docker exec $(docker ps -q -f name=ollama) ollama pull phi3:mini

# Verify
docker exec $(docker ps -q -f name=ollama) ollama list
curl http://localhost:8001/v1/router/providers | python -m json.tool
```

Generate as usual via the API (`/intake` → `/clarify` → `/generate-spec`); the architect will use the SLM first when the flag is on.

## Environment

| Var | Default | Meaning |
|---|---|---|
| `ENABLE_LOCAL_LLM` | `false` | SLM-first architect + LOCAL provider enabled |
| `OLLAMA_URL` | `http://ollama:11434` (compose) / `http://localhost:11434` (host dev) | Ollama endpoint |
| `OLLAMA_MODEL` | `phi-3-mini-3.8b-q4` | Internal router model id |
| `LOCAL_LLM_CONTEXT` | `4096` | SLM context window |
| `QWEN_GROQ_MODEL` | `qwen-qwq-32b` | Planning primary (Groq) |
| `QWEN_OPENROUTER_MODEL` | `qwen/qwen-2.5-72b-instruct` | Planning fallback |

## SLM Prompt Notes

`phi-3-mini` has a 4k window, so the architect uses a compact entities-only prompt (`ARCHITECT_SLIM_ENTITIES_PROMPT` + one few-shot 2-room example) with `temperature 0.1`, `max_tokens 2048`, and 1 retry; navigation/lighting/budget are assembled deterministically (`_assemble_spec`). A full-spec single-shot prompt proved unreliable on 3B (see tuning below).

## Tuning Results (2026-09-10, 8-core i5 laptop CPU, Docker, phi3:mini q4)

Steady-state inference: **5.4 tok/s** decode, prompt eval fast, first load ~60s.

| Config | Outcome |
|---|---|
| Full-spec prompt, temp 0.2 | 0/2 valid — truncated mid-entities (~700 chars, trailing newlines, same stall point) |
| Full-spec prompt, temp 0.1 | 0/1 valid — same stall (deterministic, not sampling noise) |
| **Hybrid entities-only, temp 0.1** | **2/2 valid first attempt** — real estate 4 rooms (122s), heritage 5 POIs (177s) |
| Full pipeline e2e (offline, no cloud keys) | `completed`, validation 0.97, domain True (129s) |

Fixes applied from tuning:
- Worker→router auth: shared client now sends `X-Api-Key` (router 401'd every worker call otherwise).
- `timeout` passthrough on shared client; `LOCAL_LLM_TIMEOUT=300` (60s reader timed out mid-generation).
- Intake/clarification fallbacks now catch `httpx.HTTPError` (router 502 with no cloud keys crashed the pipeline instead of using keyword fallback).
- `OLLAMA_KEEP_ALIVE=24h` in compose (cold load dominates first request).
- Truncated SLM outputs must not be retried from cache: keep outputs short enough to complete first try. If a run caches garbage, delete `llm_cache:spec_generation:phi-3-mini*` in Redis DB 1.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No available provider for SPEC_GENERATION` with flag on | Ollama down or model not pulled: `docker compose --profile local up -d ollama && docker exec ... ollama pull phi3:mini` |
| Slow first generation (60s load + 2-3 min for a full spec at ~5 tok/s) | Cold model load into RAM; keep `OLLAMA_KEEP_ALIVE=24h` so later runs skip load |
| `generation_notes` says template fallback | SLM + cloud both failed; check `docker logs ollama` and router `/v1/router/providers` health |
| OOM on 8GB box | Keep `_MAX_CONCURRENT_LOCAL=2`; don't raise `OLLAMA_NUM_PARALLEL` |

## Deferred

Tailwind/TS/eslint holds are unrelated. Future: `gemma-2b` / `qwen2-1.5b` profiles, `llama.cpp` native (no Ollama daemon), GPU offload when VRAM exists.

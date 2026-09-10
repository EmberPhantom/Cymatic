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

`phi-3-mini` has a 4k window, so the architect uses a compact prompt (`ARCHITECT_SLIM_PROMPT`, ~600 tokens + one few-shot 2-room example) instead of the full cloud prompt: strict single-JSON-object contract, `temperature 0.2`, `max_tokens 2048`. Non-numeric `position` hallucinations fail `SimulationSpec` validation and fall through to cloud/template — by design.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No available provider for SPEC_GENERATION` with flag on | Ollama down or model not pulled: `docker compose --profile local up -d ollama && docker exec ... ollama pull phi3:mini` |
| Slow first generation (30-60s) | Cold model load into RAM; subsequent runs 5-30s |
| `generation_notes` says template fallback | SLM + cloud both failed; check `docker logs ollama` and router `/v1/router/providers` health |
| OOM on 8GB box | Keep `_MAX_CONCURRENT_LOCAL=2`; don't raise `OLLAMA_NUM_PARALLEL` |

## Deferred

Tailwind/TS/eslint holds are unrelated. Future: `gemma-2b` / `qwen2-1.5b` profiles, `llama.cpp` native (no Ollama daemon), GPU offload when VRAM exists.

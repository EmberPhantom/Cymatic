# CYMATIC LLM Router (OpenAI-compatible AI gateway, :8001)

Single internal API over all providers (Groq, OpenRouter, NVIDIA NIM,
OpenAI, Sarvam, APInex) plus offline Ollama SLM. Task-based routing,
sensitivity policies (no tenant data to free tiers), fallbacks,
circuit breakers, Redis cache, usage quotas. Health reports live
provider inventory at `/health`.

## Layout

- `app/main.py` — routes: `/v1/chat/completions`, `/v1/embeddings`,
  `/v1/audio/transcriptions`, `/v1/audio/speech`, `/v1/router/*` (admin)
- `app/routing/` — engine, usage tracker, cache, circuit breaker
- `app/providers/` — LiteLLM client wrapper
- `app/core/` — config (strict validators), rate limiting
- `tests/` — routing/quota/sanitize unit tests

## Contracts

- Callers pass `task_type` + `sensitivity`; router picks provider chain.
- Management endpoints require `ADMIN_API_KEY` (`X-Api-Key` or Bearer).

## Build / test

```bash
docker buildx bake -f ../../docker-bake.hcl llm-router
make test-llm
```

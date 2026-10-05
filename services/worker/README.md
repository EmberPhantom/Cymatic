# CYMATIC Worker (background generation jobs, :8002)

Consumes the Redis job queue and runs the simulation pipeline:
intake → clarification → plan → spec → validate → scene → publish.
Health at `/health`; handlers: `generate_spec`, `validate_spec`,
`generate_scene`, `publish_scene`, `process_asset`, `analytics_aggregation`.

## Layout

- `app/main.py` — worker service entrypoint
- `app/agents/` — intake, clarification, research, domain-expert, architect,
  composer, asset, validation, scene-package
- `app/pipelines/` — `real_estate.py`, `heritage.py`, `heritage_templates.py`
- `app/tasks/generation.py` — job handlers (advisory locks, checkpoints)
- `app/core/` — config, queue client, LLM client
- `tests/` — pipeline/agent unit tests with mocked LLM

## Contracts

- Job payloads carry `project_id`/`spec_id`/`asset_id`; ownership is
  re-verified before work (fail-closed, see api `jobs.py` mirror).
- LLM access only via `LLM_ROUTER_URL` (never direct provider keys),
  honoring sensitivity routing. `ENABLE_LOCAL_LLM` for offline SLM.

## Build / test

```bash
docker buildx bake -f ../../docker-bake.hcl worker
make test-worker
```

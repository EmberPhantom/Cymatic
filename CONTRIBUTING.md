# Contributing to CYMATIC

## Before Opening a Change

- Read `AGENTS.md` and the relevant architecture documentation under `docs/`.
- Keep simulation changes specification-first: agent proposals must be validated before trusted state changes.
- Keep experimental features behind their existing feature flags.
- Do not commit `.env` files, provider keys, credentials, build outputs, or generated local reports.

## Validation

Run the checks relevant to the changed subsystem. The primary repository commands are:

```text
make test
make lint
make typecheck
docker compose -f infra/docker/docker-compose.yml config
```

For frontend-only changes, also run `npm run type-check`, `npm run lint`, and `npm run build` from `apps/web`.

For API, worker, or router changes, include focused tests for authorization, tenant isolation, schema validation, failure handling, and queue behavior where applicable.

Coverage and browser-test details are documented in `docs/08-testing-and-ci.md`. Pull requests must include the relevant unit, integration, and Playwright validation for changed behavior.

## Change Boundaries

- `apps/web/**`: frontend
- `services/api/**`: control-plane API
- `services/worker/**`: background processing
- `services/llm-router/**`: provider routing and policy
- `packages/cymatic-shared/**`: shared Python contracts
- `schemas/**`: shared schema sources
- `unity/**`: render server
- `android/**`: Android client
- `infra/**`: local/deployment infrastructure

Avoid unrelated refactors in the same change. Document migrations, environment variables, feature flags, and operational follow-up when they are required.

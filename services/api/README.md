# CYMATIC API (FastAPI control plane, :8000)

Auth, projects, specs, plan, assets, render/stream sessions, editing,
analytics, credits, jobs. All routes under `/v1` (see `app/api/v1/router.py`);
health at `/health`, admin-gated `/metrics`.

## Layout

- `app/main.py` — app factory, middleware, exception handlers
- `app/api/v1/endpoints/` — one module per domain (`auth`, `projects`,
  `specs`, `plan`, `assets`, `render`, `streaming`, `editing`, `analytics`,
  `credits`, `jobs`, `users`, `organizations`)
- `app/core/` — config, security (JWT + Redis revocation), dependencies
  (RBAC), rate limiting, queue client, middleware
- `app/models/` — SQLAlchemy models (see `docs/03-data-model-api.md`)
- `app/services/` — MinIO client, scene-package helpers, spec validation
- `app/db/` — session, base
- `alembic/` — migrations (`migrate` compose service owns upgrades)
- `tests/` — `test_*.py` + `conftest.py` (isolated test DBs)

## Contracts

- Tenant scoping on every query (`organization_id`); roles
  Owner/Admin/Creator/Viewer/Auditor (`require_*` in dependencies).
- Agent proposals never mutate state directly (see `docs/04`).
- Native render path: `POST /v1/render/*` (see `docs/27-mobile-render-pivot.md`).

## Build / test

```bash
docker buildx bake -f ../../docker-bake.hcl api        # image
docker compose ... --profile test run --rm --build test-api
make test-api                                          # same, via Makefile
```

Env: `.env` at repo root (`DATABASE_URL`, `REDIS_*`, `S3_*`, `JWT_SECRET_KEY`,
`LLM_ROUTER_URL`, `MOBILE_MIN_APP_VERSION`, feature flags).

# CYMATIC Infrastructure

## `docker/` — local stack

- `docker-compose.yml` — full stack (`name: cymatic`, `cymatic-*`
  containers, versioned `cymatic/<svc>:${APP_VERSION:-latest}` images,
  `migrate` owns Alembic, `test` profile suites → `./reports/`)
- `docker-compose.dev.yml` — hot-reload mounts (`make dev`)
- `docker-compose.s3mock.yml` — moto S3 fallback when quay.io is blocked
  (`make up-mock`)

Infra services: postgres :5432, redis :6379, minio :9000. App services:
api :8000, worker :8002, llm-router :8001, web :3000, viewer :8090.
See `docs/02-repo-and-setup.md` for profiles, Redis DB map, and commands.

## `k8s/` — pre-production manifests (namespace `cymatic`)

`namespace-config.yml` (ConfigMap + secrets checklist),
`services.yml` (api/worker/router/web/viewer + ingress),
`migrate-job.yml` (one-shot Alembic).
All infra files use `.yml` (single extension convention).
Rules: single api replica (in-memory signaling), version-pinned images
(never `:latest`), external Postgres/Redis/S3.

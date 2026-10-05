# Testing and CI

## Local checks

Run focused checks from each service directory:

```bash
python -m pytest tests/ -v
python -m pytest tests/ --cov=app --cov-report=term-missing --cov-report=xml
```

For the shared package:

```bash
cd packages/cymatic-shared
python -m pytest tests/ -v
```

## Host test environment

Containerized suites (`.\tasks.ps1 test-api`, `make test-api`) wire
everything themselves. Running `pytest` directly on the host against the
already-up local infra needs the test endpoints — the defaults in
`tests/conftest.py` (unauthenticated Redis on `:6379`, Postgres on
`:5432`) do not match the local stack (authenticated Redis, test
Postgres on `:5433`):

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://cymatic:cymatic@localhost:5433/cymatic_test"  # worker: .../cymatic_worker_test
$env:REDIS_URL = "redis://:cymatic_redis_pass@localhost:6379/0"
$env:REDIS_QUEUE_URL = "redis://:cymatic_redis_pass@localhost:6379/0"
$env:REDIS_CACHE_URL = "redis://:cymatic_redis_pass@localhost:6379/1"
$env:REDIS_USAGE_URL = "redis://:cymatic_redis_pass@localhost:6379/2"
$env:REDIS_RATE_URL = "redis://:cymatic_redis_pass@localhost:6379/3"
$env:REDIS_REVOKED_URL = "redis://:cymatic_redis_pass@localhost:6379/4"
$env:REDIS_PUBSUB_URL = "redis://:cymatic_redis_pass@localhost:6379/5"
$env:S3_ENDPOINT = "http://localhost:9000"
python -m pytest tests/ -q --no-cov -p no:cacheprovider
```

(`REDIS_PASSWORD` defaults to `cymatic_redis_pass` in
`infra/docker/docker-compose.yml`; `POSTGRES_TEST_PORT` defaults to
`5433`. `test_benchmark.py` additionally needs `pytest-benchmark`,
which is installed in the container images but may be missing from a
host Python.) Session teardown drops all tables including
`alembic_version`, so repeat runs re-migrate from scratch — no manual
DB reset needed.

For the frontend:

```bash
cd apps/web
npm ci
npm run test
npm run type-check
npm run lint
npm run build
npm run test:e2e
```

The Playwright smoke suite expects the frontend to be available at `http://127.0.0.1:3000`; the Playwright configuration starts `next start` automatically.

## CI policy

Pull requests run the fast `CYMATIC PR Gate` for frontend unit/build checks, API/worker/router tests, shared schema tests, type checks, linting, and coverage collection. `CYMATIC Deep Integration` runs as a direct PR check for Docker Compose, migrations, service health, and Playwright browser smoke tests, so its required status always exists even when a fast job fails. `CYMATIC Security` runs independently for vulnerability and secret scanning. Python changed-line coverage is enforced at 70% on pull requests; total coverage is reported per subsystem while the repository establishes a baseline.

Backend Dockerfiles must be built with the repository root as context because they install `packages/cymatic-shared`. Compose migration and test services must complete before dependent application services are considered ready.

## Test boundaries

Tests must mock external LLM providers and avoid tenant or production resources. Database integration tests use disposable PostgreSQL instances and Alembic migrations. Unity and Android hardware behavior remains an external integration stage; CI validates their available contracts and build configuration only.

## Pull-request volume

Dependabot groups routine updates by ecosystem and limits each ecosystem to two open PRs. The scheduled repository-maintenance workflow is dry-run by default, reports superseded Dependabot PRs, and marks inactive human PRs after 14 days before closing them after the stale period. Set repository variable `MAINTENANCE_APPLY=true` and manually dispatch with `dry_run=false` only after reviewing the report. Add `keep-open` or `pinned` when a PR must remain active.

All GitHub Actions are pinned to immutable commit SHAs and annotated with their release tags; Dependabot updates those pins.

## GitHub settings

Apply the protected-branch and required-check settings described in `.github/BRANCH_PROTECTION.md`. CODEOWNERS currently assigns review to `@EmberPhantom`.

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

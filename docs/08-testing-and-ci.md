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

Pull requests run frontend unit and smoke tests, API/worker/router tests, shared schema tests, type checks, linting, coverage collection, Docker builds, Compose integration checks, and security scans. Coverage is initially reported per subsystem while the repository establishes a baseline; changed-line enforcement is intended to begin at 70% and ratchet upward.

Backend Dockerfiles must be built with the repository root as context because they install `packages/cymatic-shared`. Compose migration and test services must complete before dependent application services are considered ready.

## Test boundaries

Tests must mock external LLM providers and avoid tenant or production resources. Database integration tests use disposable PostgreSQL instances and Alembic migrations. Unity and Android hardware behavior remains an external integration stage; CI validates their available contracts and build configuration only.

## GitHub settings

Apply the protected-branch and required-check settings described in `.github/BRANCH_PROTECTION.md`. Update the placeholder teams in `.github/CODEOWNERS` before making CODEOWNERS review mandatory.

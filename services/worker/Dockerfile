# syntax=docker/dockerfile:1
# CYMATIC worker image.
# Build context: services/worker (+ `shared` named context for cymatic-shared).
# Layer-cache design: keep the builder apt block and requirements.runtime.txt
# byte-identical with services/api/Dockerfile so BuildKit shares those
# layers between both images. Runtime-only deps are installed here; test
# deps are installed in the `test` stage only.

# ── Builder ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /tmp/build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Runtime requirements first for layer cache (rarely change vs app code).
COPY requirements.runtime.txt ./requirements.runtime.txt
# hadolint ignore=DL3042 — pip cache is a BuildKit cache mount, not image bloat
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements.runtime.txt

# Shared package via `shared` named context (bake/compose) or plain copy.
COPY --from=shared . ./shared/
# hadolint ignore=DL3042 — see above
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install ./shared \
    && find /install -type d -name '__pycache__' -prune -exec rm -rf {} + \
    && find /install -name '*.pyc' -delete

# ── Runtime ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 999 appuser && useradd --system --uid 999 --gid 999 --create-home --home-dir /app appuser

COPY --from=builder /install /usr/local

WORKDIR /app

# Separate COPYs (one dest per instruction), correct ownership up front —
# no duplicate chown layer. NOTE: `COPY dir /app/` copies dir CONTENTS, so
# each source needs its explicit destination. Numeric UID:GID is required
# with --link (link layers cannot resolve usernames).
COPY --link --chown=999:999 app/ ./app/
COPY --link --chown=999:999 alembic.ini ./alembic.ini
COPY --link --chown=999:999 alembic/ ./alembic/

USER appuser

EXPOSE 8002

# curl is cheaper than spawning `python -c "import httpx..."` every 10s.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://localhost:8002/health || exit 1

# Single uvicorn worker REQUIRED: app.main.worker_loop is a serial,
# single-owner loop (WORKER_CONCURRENCY in app/core/config.py is
# reserved/unused). `--workers N` would spawn N competing loops over the same
# Redis ZPOPMAX queues — dequeue is atomic so jobs are not lost, but the
# loops fight over polls/lock renewals and multiply LLM traffic. Scale with
# more worker containers, not uvicorn fan-out. (The llm-router image likewise
# runs a single uvicorn worker: its owning process holds the provider clients
# and in-memory policy state.)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "1"]

# ── Test ───────────────────────────────────────────────────────
FROM runtime AS test

HEALTHCHECK NONE

USER root

COPY pytest.ini requirements.runtime.txt requirements.test.txt ./
COPY tests/ ./tests/
# hadolint ignore=DL3042 — see above
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.test.txt

ENV PYTHONPATH=/app:/usr/local/lib/python3.11/site-packages

USER appuser

CMD ["pytest", "tests/", "-v", "--tb=short"]

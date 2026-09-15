# syntax=docker/dockerfile:1
# CYMATIC LLM router image.
# Build context: services/llm-router (+ `shared` named context for cymatic-shared).
# No postgres client here (no direct DB access). Runtime-only deps are
# installed in the builder; test deps are installed in `test` only.

# ── Builder ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /tmp/build

# Only gcc needed for some litellm deps (no libpq-dev: no postgres).
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
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
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 999 appuser && useradd --system --uid 999 --gid 999 --create-home --home-dir /app appuser

COPY --from=builder /install /usr/local

WORKDIR /app

# Correct ownership up front (no duplicate chown layer).
# NOTE: --link layers cannot resolve usernames, so the numeric UID:GID
# (pinned to 999 above) is required here instead of `appuser:appuser`.
COPY --link --chown=999:999 app /app/app

USER appuser

EXPOSE 8001

# curl is cheaper than spawning `python -c "import httpx..."` every 10s.
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s \
    CMD curl -fsS http://localhost:8001/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

# ── Test ───────────────────────────────────────────────────────
FROM runtime AS test

HEALTHCHECK NONE

USER root

COPY requirements.runtime.txt requirements.test.txt ./
COPY tests/ ./tests/
# hadolint ignore=DL3042 — see above
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.test.txt

ENV PYTHONPATH=/app:/usr/local/lib/python3.11/site-packages

USER appuser

CMD ["pytest", "tests/", "-v", "--tb=short"]

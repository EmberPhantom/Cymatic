# ── Build stage ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /tmp/build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Requirements first for layer cache (cache-busting order: requirements before shared/code)
COPY requirements.txt ./requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --prefix=/install -r requirements.txt

# Shared package via additional_context 'shared' (compose per-service) or fallback
COPY --from=shared . ./shared/
RUN --mount=type=cache,target=/root/.cache/pip pip install --prefix=/install ./shared

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appuser && useradd --system --gid appuser --create-home --home-dir /app appuser

COPY --from=builder /install /usr/local

WORKDIR /app

COPY app/ ./app/
COPY alembic.ini ./alembic.ini
COPY alembic/ ./alembic/

RUN chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${API_WORKERS:-4}"]

# ── Test stage ──────────────────────────────────────────────
FROM runtime AS test

USER root

COPY tests/ ./tests/
COPY pytest.ini ./pytest.ini
RUN --mount=type=cache,target=/root/.cache/pip pip install pytest==8.3.5 pytest-asyncio==0.24.0 pytest-cov psycopg2-binary==2.9.9 httpx

ENV PYTHONPATH=/app:/usr/local/lib/python3.11/site-packages

USER appuser

CMD ["pytest", "tests/", "-v", "--tb=short"]

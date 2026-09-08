# syntax=docker/dockerfile:1.6
# ── Build stage ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /tmp/build

# Only gcc needed for some litellm deps; remove libpq-dev bloat (no postgres)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY --from=shared . ./shared/
RUN pip install --no-cache-dir --prefix=/install ./shared

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --create-home app --home-dir /app app

COPY --from=builder /install /usr/local

WORKDIR /app

COPY app/ ./app/

RUN chown -R app:app /app
USER app

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=15s CMD python -c "import httpx; httpx.get('http://localhost:8001/health').raise_for_status()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

# ── Test stage ──────────────────────────────────────────────
FROM runtime AS test

USER root

COPY tests/ ./tests/
RUN pip install --no-cache-dir pytest==8.3.5 pytest-asyncio==0.24.0 pytest-cov httpx

ENV PYTHONPATH=/app:/usr/local/lib/python3.11/site-packages

USER app

CMD ["pytest", "tests/", "-v", "--tb=short"]

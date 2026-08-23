# ── Build stage ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /tmp/build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY packages/cymatic-shared/ ./shared/
RUN pip install --no-cache-dir --prefix=/install ./shared

COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --from=builder /tmp/build/shared /app/packages/cymatic-shared

WORKDIR /app

COPY services/api/app/ ./app/
COPY services/api/alembic.ini ./alembic.ini
COPY services/api/alembic/ ./alembic/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Test stage ──────────────────────────────────────────────
FROM runtime AS test

COPY services/api/tests/ ./tests/
COPY services/api/pytest.ini ./pytest.ini
RUN pip install --no-cache-dir pytest==8.3.5 pytest-asyncio==0.24.0 pytest-cov psycopg2-binary

ENV PYTHONPATH=/app/packages/cymatic-shared

CMD ["pytest", "tests/", "-v", "--tb=short"]

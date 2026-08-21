# ── Build stage ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /tmp/build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY packages/cymatic-shared/ ./shared/
RUN pip install --no-cache-dir ./shared

COPY services/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --from=builder /tmp/build/shared /app/packages/cymatic-shared

WORKDIR /app

COPY services/api/app/ ./app/
COPY services/api/alembic.ini ./alembic.ini
COPY services/api/alembic/ ./alembic/
COPY services/api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Test stage ──────────────────────────────────────────────
FROM runtime AS test

COPY services/api/tests/ ./tests/
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov

ENV PYTHONPATH=/app/packages/cymatic-shared

CMD ["pytest", "tests/", "-v", "--tb=short"]

# ── Build stage ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /tmp/build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY packages/cymatic-shared/ ./shared/
RUN pip install --no-cache-dir ./shared

COPY services/worker/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --from=builder /tmp/build/shared /app/packages/cymatic-shared

WORKDIR /app

COPY services/worker/app/ ./app/

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]

# ── Test stage ──────────────────────────────────────────────
FROM runtime AS test

COPY services/worker/tests/ ./tests/
RUN pip install --no-cache-dir pytest pytest-asyncio pytest-cov

ENV PYTHONPATH=/app/packages/cymatic-shared

CMD ["pytest", "tests/", "-v", "--tb=short"]

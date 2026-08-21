# ── Build stage ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /tmp/build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY packages/cymatic-shared/ ./shared/
RUN pip install --no-cache-dir --prefix=/install ./shared

COPY services/llm-router/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────
FROM python:3.11-slim AS runtime

COPY --from=builder /install /usr/local

WORKDIR /app

COPY services/llm-router/app/ ./app/

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

# ── Test stage ──────────────────────────────────────────────
FROM runtime AS test

COPY services/llm-router/tests/ ./tests/
RUN pip install --no-cache-dir pytest==8.3.5 pytest-asyncio==0.24.0 pytest-cov

ENV PYTHONPATH=/app/packages/cymatic-shared

CMD ["pytest", "tests/", "-v", "--tb=short"]

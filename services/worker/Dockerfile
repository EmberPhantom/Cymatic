FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install shared package first (changes less often)
COPY packages/cymatic-shared/ /app/packages/cymatic-shared/
RUN pip install --no-cache-dir /app/packages/cymatic-shared

# Install service dependencies
COPY services/worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY services/worker/app/ ./app/

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]

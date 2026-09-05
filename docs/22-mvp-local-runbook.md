# CYMATIC MVP local runbook

## Start the stack

1. Copy `.env.example` to `.env` and set a non-default `JWT_SECRET_KEY`.
2. Start the production-like local stack:

```powershell
docker compose -f infra/docker/docker-compose.yml up -d --build
```

The `migrate` service owns Alembic migrations. The API, worker, and web services wait for their required health checks.

Open `http://localhost:3000`. Browser authentication uses HttpOnly cookies. Android and other non-browser clients may continue using bearer tokens.

## Validate the stack

```powershell
docker compose -f infra/docker/docker-compose.yml ps
Invoke-WebRequest http://localhost:8000/health
Invoke-WebRequest http://localhost:3000/api/health
```

The web `/api/*` path is a same-origin proxy to the internal `api:8000` Compose service. Browser login uses the explicit `/api/auth/login` handler so FastAPI auth cookies are forwarded to the browser before navigation. Direct browser calls should use `/api`, not the internal service hostname.

## Run automated tests

The test profile creates and migrates a separate `cymatic_test` database and uses deterministic agent responses for API tests; it never targets the development database.

```powershell
docker compose -f infra/docker/docker-compose.yml --profile test run --rm test-llm-router
docker compose -f infra/docker/docker-compose.yml --profile test run --rm test-api
docker compose -f infra/docker/docker-compose.yml --profile test run --rm test-worker
```

## MVP manual flow

1. Register a user and sign in.
2. Create a `real_estate` or `heritage` project.
3. Submit an intake prompt and review the detected domain/questions.
4. Submit clarification answers.
5. Generate a specification and verify the queued job/status transition.
6. Upload/select assets and validate the specification before runtime generation.
7. Treat Unity render-server and Android/WebRTC checks as hardware-gated validation; they require the Windows render host and a compatible Android device on the same LAN.

## Single-VM Single-Device Production (one gaming laptop/desktop)

For the requested **single VM locally on one device** (no k8s, no scaling), use the same `infra/docker/docker-compose.yml` on the production host:

```powershell
# 1. Generate production secrets (do NOT commit .env)
Copy-Item .env.example .env
# PowerShell: generate 64-hex JWT (32 bytes) + admin/minio passwords
-join ((48..57)+(65..90)+(97..122) | Get-Random -Count 64 | % {[char]$_}) # then manually set JWT_SECRET_KEY, ADMIN_API_KEY, MINIO_ROOT_PASSWORD
# or: openssl rand -hex 32  (WSL)
# 2. Edit .env: ENVIRONMENT=production, DEBUG=false, set JWT_SECRET_KEY (≥32 chars), ADMIN_API_KEY, MINIO_ROOT_PASSWORD, POSTGRES_PASSWORD
# 3. Bring up
docker compose -f infra/docker/docker-compose.yml up -d --build
# 4. Verify production health (admin key required for /metrics)
Invoke-WebRequest http://localhost:8000/health | ConvertFrom-Json
curl.exe -H "X-API-Key: $env:ADMIN_API_KEY" http://localhost:8000/metrics | Select-Object -First 5
```

**Backup (nightly cron on VM host):**
```powershell
docker run --rm -v cymatic_postgres_data:/volume -v $PWD/backup:/backup alpine tar czf /backup/postgres-$(Get-Date -Format yyyy-MM-dd).tar.gz /volume
# MinIO bucket already `cymatic` auto-created on first upload; versioning/lifecycle not needed for single device
```

**Notes kept per your keep:** `pr-gate` audits `continue-on-error:true` (warn), `minio` `wget --spider`, `main` lineage `50f4029` retained, `GROQ` allowed for `TENANT_SENSITIVE` (free tier) per approval.

## Known hardware-gated validation

The local web/API/worker/LLM MVP can be validated with the flow above. Actual stereo rendering, WebRTC transport, IMU/controller input, voice capture, and thermal performance still require the Unity render server and Android client; these are not emulated by Docker.

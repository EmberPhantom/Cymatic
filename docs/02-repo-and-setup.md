# CYMATIC Repository Structure and Developer Setup

## Recommended Monorepo Layout

```text
cymatic/
├── apps/
│   ├── web/                # Next.js builder frontend (:3000)
│   └── viewer/             # Vite+Three.js mobile walkthrough viewer (:8090)
├── services/
│   ├── api/                # FastAPI control plane (:8000)
│   ├── worker/             # Background job processor (:8002)
│   └── llm-router/         # LLM provider routing (:8001)
├── unity/
│   └── render-server/      # Unity render/streaming server (Windows native)
├── android/
│   └── client/             # Android VR streaming client (Kotlin)
├── infra/
│   ├── docker/             # Compose files (prod-like, dev, s3mock)
│   └── k8s/                # Kubernetes manifests (pre-prod, see below)
├── schemas/                # SimulationSpec + PlanningSheet (TS + Pydantic)
├── packages/
│   └── cymatic-shared/     # Shared Python package (agents, models)
├── docker-bake.hcl         # Parallel image builds (all 5 services)
├── Makefile                # Dev/test/docker shortcuts
├── .env.example            # Full variable template (copy to .env)
└── docs/
```

---

## Service Allocation for Team Development

### Gaming Laptop
Primary role:
- Unity Render Server
- stereo rendering
- stream encoding

### Laptop 2
Primary role:
- PostgreSQL
- Redis
- MinIO
- shared local storage

### Laptop 3
Primary role:
- FastAPI backend
- worker services
- LLM router
- frontend development

### Other Laptops
Primary role:
- app development
- Android client testing
- QA
- documentation
- AI workflow testing

---

## Development Environment

### Operating System
- Windows 10/11
- WSL2
- Ubuntu distribution inside WSL2

### Required Tools
- Docker Desktop
- Git
- Node.js 20+
- Python 3.11+
- pnpm or npm
- Unity Hub
- Android Studio

---

## Docker Compose Strategy

Use Docker Compose for daily local development. Base file:
`infra/docker/docker-compose.yml`.

### Container naming

`name: cymatic` pins the Compose project, so containers are always
`cymatic-<service>-1` regardless of the checkout directory name.
One-shot jobs (`migrate`, `test-*`) intentionally have no `container_name`
so concurrent runs never collide. Check with `make docker-ps`.

### Services, ports, containers

| Service | Container | Host port | Purpose |
|---------|-----------|-----------|---------|
| postgres | cymatic-postgres | 5432 | PostgreSQL 16 app database |
| redis | cymatic-redis | 6379 | Queue/cache/usage/rate/revoked/pubsub (DB split) |
| minio | cymatic-minio | 9000 (+9001 console) | S3-compatible object storage |
| coturn | cymatic-coturn | 3478/5349 | TURN relay (`turn` profile only) |
| api | cymatic-api | 8000 | FastAPI control plane |
| worker | cymatic-worker | 8002 | Background generation jobs |
| llm-router | cymatic-llm-router | 8001 | LLM provider routing |
| ollama | cymatic-ollama | 11434 | Local SLM (`local` profile only) |
| web | cymatic-web | 3000 | Next.js builder |
| viewer | cymatic-viewer | 8090 | Static walkthrough viewer |

### Compose files

| File | When to use |
|------|-------------|
| `docker-compose.yml` | Default: production-like local stack |
| `docker-compose.dev.yml` | Hot-reload mounts: `-f ... -f docker-compose.dev.yml` (`make dev`) |
| `docker-compose.s3mock.yml` | Moto S3 mock instead of MinIO when quay.io is blocked (`make up-mock`) |

### Profiles

| Profile | Services | Command |
|---------|----------|---------|
| (none) | all except below | `make infra-up` |
| `test` | test-postgres, test-db(-worker), test-migrate(-worker), test-api/worker/llm-router | `make test` (JUnit XML → `./reports/`) |
| `local` | ollama | add `--profile local` for offline SLM |
| `turn` | coturn | add `--profile turn` when WebRTC needs TURN |

### Migrations

The `migrate` service owns Alembic (`alembic upgrade head`) against a fresh
database; `api` waits for `migrate: completed_successfully`. Never run
migrations from every replica — one-shot job only.

### Redis DB split

0 queue · 1 cache · 2 usage · 3 rate · 4 revoked · 5 pubsub · 6 api-test ·
7 worker-test · 8 router-test. Each map entry is a separate `REDIS_*_URL`.

### Image tags

Built images tag `cymatic/<svc>:${APP_VERSION:-latest}`. Set
`APP_VERSION=0.1.0` in `.env` to pin a release; `docker-bake.hcl` tags both
the version and `latest` (all 5 services incl. viewer).

### Runtime efficiency defaults

`init: true` (reap zombies), `stop_grace_period` 30s for
api/worker/router/ollama, `cpus` + `mem_limit` bounds per service,
`json-file` logs capped at 10m×3 with `tag: {{.Name}}` for attribution.

---

## Environment Variables

Canonical template: `.env.example` (copy to `.env`). Highlights:

```env
APP_VERSION=latest
DATABASE_URL=postgresql://cymatic:cymatic@localhost:5432/cymatic
REDIS_URL=redis://localhost:6379/0
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=cymatic
```

### LLM Router

```env
LLM_ROUTER_URL=http://localhost:8001
GROQ_API_KEY=
OPENROUTER_API_KEY=
NVIDIA_NIM_API_KEY=
OPENAI_API_KEY=
SARVAM_API_KEY=
APINEX_API_KEY=
```

### Streaming

```env
RENDER_SERVER_URL=http://<gaming-laptop-ip>:8080
SIGNALING_URL=ws://<backend-ip>:8000/v1/stream
STUN_URL=stun:stun.l.google.com:19302
TURN_URL=
TURN_USERNAME=
TURN_PASSWORD=
```

### Feature Flags

```env
ENABLE_HAND_TRACKING=false
ENABLE_UVC_CAMERA=false
ENABLE_VOICE=true
ENABLE_HERITAGE_TEMPLATES=true
ENABLE_ADAPTIVE_STREAMING=true
ENABLE_MANUAL_EDITING=false
ENABLE_MULTIPLAYER=false
```

---

## Local Setup Steps

### 1. Enable WSL2
Install WSL2 and Ubuntu on Windows.

### 2. Install Docker Desktop
Enable WSL2 integration and start the daemon.

### 3. Install runtimes
- Git, Node.js 20+, Python 3.11+, npm

### 4. Clone repository
```bash
git clone <repo-url>
cd cymatic
```

### 5. Create environment file
```bash
cp .env.example .env
# set JWT_SECRET_KEY (>=32 chars), provider keys, strong passwords for prod
```

### 6. Start the stack (pick one)
```bash
make infra-up   # production-like images (needs quay.io for MinIO)
make up-mock    # moto S3 mock instead of MinIO (offline-friendly)
make dev        # hot-reload mounts for active development
```
Windows PowerShell without GNU make: `tasks.ps1` mirrors every target —
`.\tasks.ps1 infra-up`, `.\tasks.ps1 test`, `.\tasks.ps1 docker-ps`, etc.

### 7. Verify
```bash
make docker-ps
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
```

### 8. Run tests
```bash
make test       # containerized suites, JUnit XML lands in ./reports/
```

### 9. Host-venv development (optional, fast iteration)
```bash
make install-api && make dev-api   # needs local Postgres/Redis running
```

### 10. Run Unity Render Server
- open `unity/render-server` in Unity Hub
- configure backend URL and streaming settings
- run the render server scene

### 11. Run Android Client
- open `android/client` in Android Studio
- configure server URL
- build and run on device

### Host networking notes
- Always use `localhost` (resolves to `::1` → Docker) or your LAN IP.
  `127.0.0.1:8000` may be shadowed by other tools on dev machines.

---

## Kubernetes Strategy

### Phase 1: Local development
Use Docker Compose.

### Phase 2: Shared team cluster
Use k3d or k3s.

### Phase 3: Staging/production readiness
Use Helm/manifests.

### Important MVP rules
- Do not force the Unity render server into Kubernetes initially.
  Run it as a native Windows process for simplicity.
- `infra/k8s` is pre-production: single replica for `api` (in-memory
  signaling + single-stream assumption), images must be version-pinned,
  external Postgres/Redis/S3 expected (see `migrate-job.yml`).

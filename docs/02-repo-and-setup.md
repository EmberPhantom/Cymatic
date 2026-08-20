# CYMATIC Repository Structure and Developer Setup

## Recommended Monorepo Layout

```text
cymatic/
├── apps/
│   └── web/
├── services/
│   ├── api/
│   ├── worker/
│   └── llm-router/
├── unity/
│   └── render-server/
├── android/
│   └── client/
├── infra/
│   ├── docker/
│   ├── k8s/
│   └── scripts/
├── schemas/
├── docs/
├── packages/
├── README.md
├── CLAUDE.md
└── AGENTS.md
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

Use Docker Compose for daily local development.

### Core infrastructure services
- postgres
- redis
- minio

### Application services
- api
- worker
- llm-router
- web

### Optional services
- pgadmin or adminer
- minio-console
- coturn later if WebRTC requires TURN

---

## Environment Variables

### Core
```env
DATABASE_URL=postgresql://user:password@localhost:5432/cymatic
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
DEFAULT_FAST_MODEL=
DEFAULT_STRONG_MODEL=
DEFAULT_EMBEDDING_MODEL=
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
```

---

## Local Setup Steps

### 1. Enable WSL2
Install WSL2 and Ubuntu on Windows.

### 2. Install Docker Desktop
Enable WSL2 integration.

### 3. Install runtimes
Install:
- Git
- Node.js 20+
- Python 3.11+
- pnpm/npm

### 4. Clone repository
```bash
git clone <repo-url>
cd cymatic
```

### 5. Create environment file
```bash
cp .env.example .env
```

### 6. Start infrastructure
```bash
docker compose up -d postgres redis minio
```

### 7. Run backend API
```bash
cd services/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 8. Run worker
```bash
cd services/worker
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.worker
```

### 9. Run frontend
```bash
cd apps/web
pnpm install
pnpm dev
```

### 10. Run Unity Render Server
- open `unity/render-server` in Unity Hub
- configure backend URL and streaming settings
- run the render server scene

### 11. Run Android Client
- open `android/client` in Android Studio
- configure server URL
- build and run on device

---

## Kubernetes Strategy

### Phase 1: Local development
Use Docker Compose.

### Phase 2: Shared team cluster
Use k3d or k3s.

### Phase 3: Staging/production readiness
Use Helm/manifests.

### Important MVP rule
Do not force the Unity render server into Kubernetes initially.

Run it as a native Windows process for simplicity.
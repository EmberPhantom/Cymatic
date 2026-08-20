# CYMATIC Monorepo

No-code AI simulation builder platform for real estate and heritage VR walkthroughs.

## Architecture

```
cymatic/
├── apps/
│   └── web/                 # Next.js frontend (Builder UI)
├── services/
│   ├── api/                 # FastAPI backend (Core control plane)
│   ├── worker/              # Background job worker
│   └── llm-router/          # LLM Router (AI provider abstraction)
├── unity/
│   └── render-server/       # Unity render/streaming server (Windows native)
├── android/
│   └── client/              # Android VR streaming client (Kotlin)
├── infra/
│   ├── docker/              # Docker Compose for local development
│   ├── k8s/                 # Kubernetes manifests (future)
│   └── scripts/             # Infrastructure scripts
├── schemas/
│   ├── simulation_spec.ts   # TypeScript types
│   └── simulation_spec.py   # Python/Pydantic models
├── packages/                # Shared packages (future)
└── docs/                    # Documentation
```

## Quick Start

### Prerequisites

- Windows 10/11 with WSL2 (Ubuntu)
- Docker Desktop with WSL2 integration
- Node.js 20+
- Python 3.11+
- Unity Hub (for render server)
- Android Studio (for client)

### 1. Clone and Setup

```bash
git clone <repo-url>
cd cymatic
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start Infrastructure

```bash
make infra-up
# Or manually:
docker compose -f infra/docker/docker-compose.yml up -d
```

This starts:
- PostgreSQL on localhost:5432
- Redis on localhost:6379
- MinIO on localhost:9000 (Console: 9001, Web UI: 9090)

### 3. Install Dependencies

```bash
make install
```

### 4. Run Development Servers

**Terminal 1 - API:**
```bash
make dev-api
```

**Terminal 2 - Worker:**
```bash
make dev-worker
```

**Terminal 3 - LLM Router:**
```bash
make dev-llm
```

**Terminal 4 - Frontend:**
```bash
make dev-web
```

### 5. Access Services

- **API Docs**: http://localhost:8000/docs
- **Frontend**: http://localhost:3000
- **LLM Router**: http://localhost:8001
- **Worker**: http://localhost:8002
- **MinIO Console**: http://localhost:9090

## Development Commands

```bash
# Run all tests
make test

# Run linters
make lint

# Type checking
make typecheck

# Database migrations
make migrate
make migrate-create

# Docker
make docker-build
make docker-up
make docker-down

# Cleanup
make clean
make clean-all
```

## Environment Variables

Key variables in `.env`:

```bash
# Database
DATABASE_URL=postgresql://cymatic:cymatic@localhost:5432/cymatic

# Redis
REDIS_URL=redis://localhost:6379/0

# MinIO
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_NAME=cymatic

# LLM Providers (add your keys)
GROQ_API_KEY=
OPENROUTER_API_KEY=
NVIDIA_NIM_API_KEY=
OPENAI_API_KEY=
SARVAM_API_KEY=

# Feature Flags
ENABLE_HAND_TRACKING=false
ENABLE_UVC_CAMERA=false
ENABLE_VOICE=true
ENABLE_HERITAGE_TEMPLATES=true
ENABLE_ADAPTIVE_STREAMING=true
```

## Project Structure Details

### Services

| Service | Port | Description |
|---------|------|-------------|
| API | 8000 | Core backend (auth, projects, specs, streaming) |
| Worker | 8002 | Background jobs (generation, processing) |
| LLM Router | 8001 | AI provider routing, fallbacks, policies |

### Key API Endpoints

```
POST   /v1/auth/login
POST   /v1/auth/register
GET    /v1/projects
POST   /v1/projects
GET    /v1/projects/{id}
POST   /v1/projects/{id}/intake
POST   /v1/projects/{id}/generate-spec
POST   /v1/projects/{id}/validate-spec
POST   /v1/projects/{id}/generate-scene
POST   /v1/projects/{id}/publish
POST   /v1/stream/sessions
POST   /v1/stream/sessions/{id}/offer
POST   /v1/stream/sessions/{id}/input
POST   /v1/stream/sessions/{id}/voice/transcript
```

## Documentation

- [Product Scope](docs/00-product-scope.md)
- [Architecture](docs/01-architecture.md)
- [Repo & Setup](docs/02-repo-and-setup.md)
- [Data Model & API](docs/03-data-model-api.md)
- [AI Agents & LLM Router](docs/04-ai-agents-llm-router.md)
- [Unity, Android & Input](docs/05-unity-android-input.md)
- [Roadmap & Tasks](docs/06-roadmap-tasks.md)
- [Security & Testing](docs/07-security-testing.md)

## Feature Flags

All experimental features are behind flags:

- `ENABLE_HAND_TRACKING` - MediaPipe hand tracking (default: false)
- `ENABLE_UVC_CAMERA` - External wired UVC camera (default: false)
- `ENABLE_HERITAGE_TEMPLATES` - Heritage walkthrough templates (default: true)
- `ENABLE_ADAPTIVE_STREAMING` - Adaptive quality streaming (default: true)
- `ENABLE_MANUAL_EDITING` - Manual scene editing (default: false)
- `ENABLE_MULTIPLAYER` - Multiplayer support (default: false)

## Contributing

1. Follow the specification-first design principle
2. All AI agent proposals must go through validation
3. Keep experimental features flagged
4. Never route sensitive data to free LLM providers
5. Write tests for new functionality
6. Update documentation with changes

## License

Proprietary - CYMATIC Team
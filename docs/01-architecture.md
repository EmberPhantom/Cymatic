# CYMATIC System Architecture

## Architecture Goals

The architecture must support:
- no-code simulation generation
- AI-assisted scene creation
- structured validation
- true stereo streaming
- low-end Android compatibility
- enterprise-ready security foundations
- future multi-domain expansion

---

## High-Level Architecture Diagram

```mermaid
flowchart TD
    A[User / Creator] --> B[Next.js Builder Frontend]
    B --> C[FastAPI Core Backend]

    C --> D[Project Service]
    C --> E[Simulation Spec Service]
    C --> G[Generation Orchestrator]
    C --> H[Agent Runtime Service]
    C --> I[Analytics / Credits]
    C --> J[Security / Audit]
    C --> K[Stream Signaling Service]

    C --> L[(PostgreSQL)]
    C --> M[(Redis)]
    C --> N[(MinIO Object Storage)]
    C --> O[LLM Router]

    O --> P[Groq]
    O --> Q[OpenRouter]
    O --> R[NVIDIA NIM]
    O --> S[OpenAI]
    O --> T[Sarvam]

    C --> U[Unity Render Server]
    U --> V[True Stereo Stream]
    V --> W[Android VR Client]

    W --> X[Head Orientation Input]
    W --> Y[Controller Input]
    W --> Z[Voice Input]
    W --> AA[Optional UVC Hand Tracking]

    X --> U
    Y --> U
    Z --> C
    AA --> U
```

---

## Core Components

### 1. Builder Frontend
No-code web application for simulation creation and management.

**Responsibilities:**
- prompt intake
- guided questions
- spec review
- manual editing
- publish workflow
- usage dashboard

**Key Features:**
- Prompt-to-Specification workflow with AI-guided clarification
- Real-time spec preview with 3D scene preview
- Manual scene editing with drag-and-drop
- Version control and spec history
- One-click publish to Unity Render Server
- Usage analytics and credit consumption dashboard

**Tech Stack:**
- Next.js 14 (App Router)
- TypeScript
- Tailwind CSS
- React Three Fiber / Three.js for 3D preview
- React Query / TanStack Query for data fetching
- Zustand for state management

---

### 2. Core Backend
Central control plane.

**Responsibilities:**
- authentication & authorization (JWT + RBAC)
- organizations/users management
- project lifecycle management
- simulation spec CRUD and versioning
- generation job orchestration
- asset management (upload, processing, CDN)
- WebRTC stream session management
- WebRTC signaling server
- analytics and credit tracking
- audit logging and compliance

**Tech Stack:**
- FastAPI (Python 3.11+)
- PostgreSQL 16 (asyncpg)
- Redis 7 (caching, queues, pub/sub)
- MinIO (S3-compatible object storage)
- Alembic migrations

---

### 3. LLM Router
Central AI access layer with intelligent routing.

**Responsibilities:**
- provider abstraction (Groq, OpenRouter, NVIDIA NIM, OpenAI, Sarvam)
- intelligent fallback routing with circuit breaker
- task-based model selection (intent, spec generation, validation, copilot, embeddings, STT, TTS)
- sensitivity-based routing (public/internal/tenant-sensitive/regulated)
- quota management and rate limiting
- usage logging and cost tracking
- response caching with TTL
- schema-enforced structured outputs
- automatic retry with exponential backoff

**Supported Providers:**
- Groq (Llama 3.1 8B/70B) - fast, free tier
- OpenRouter (Claude 3.5 Sonnet, Gemini Pro) - strong reasoning
- NVIDIA NIM (Nemotron 3 Ultra) - tenant-sensitive workloads
- OpenAI (GPT-4o, GPT-4o-mini, text-embedding-3-small) - regulated/sensitive
- Sarvam (Saarika STT, Bulbul TTS) - Telugu + 10 Indian languages

---

### 4. Unity Render Server
Windows-native rendering/streaming runtime.

**Responsibilities:**
- load generated scene package (.cymatic format)
- render stereo cameras (left/right eye)
- H.264 hardware encoding (NVENC/QuickSync)
- WebRTC streaming (side-by-side stereo)
- WebRTC signaling (WebSocket)
- receive input (head pose, controller, voice, optional hand tracking)
- execute permitted copilot commands (highlight, navigate, highlight, etc.)
- emit runtime events (navigation, interaction, copilot)
- adaptive bitrate streaming (5-30 Mbps)
- NavMesh baking for navigation

**Tech Stack:**
- Unity 2022.3 LTS
- Unity WebRTC package 2.3+
- H.264 hardware encoding (NVENC/QuickSync)
- WebSocket signaling (port 8080)
- STUN/TURN for NAT traversal

---

### 5. Android Client
Phone-side VR streaming client.

**Responsibilities:**
- receive WebRTC stream (side-by-side stereo)
- display stereo video (Google Cardboard compatible)
- IMU sensor fusion (accelerometer + gyroscope + magnetometer)
- Bluetooth controller input (Daydream/Cardboard style)
- push-to-talk voice capture (16kHz, Opus)
- optional UVC camera hand tracking (MediaPipe)
- send compact input packets (head pose, controller, voice, optional hand)
- thermal monitoring and adaptive quality

**Tech Stack:**
- Kotlin + Android SDK 24+
- Google WebRTC (org.webrtc:google-webrtc:1.0.32006)
- CameraX for UVC camera
- MediaPipe Hands (optional)
- ExoPlayer for audio playback

---

### 6. Data Layer
- **PostgreSQL 16**: relational data (projects, specs, users, sessions, audit logs)
- **Redis 7**: queues (Celery), cache, pub/sub, session state, rate limiting
- **MinIO**: assets (.glb/.gltf), scene packages (.cymatic), uploads, thumbnails

---

## Key Architecture Principles

### Specification-first
All simulations derive from a structured Simulation Specification (JSON Schema validated).

### Trusted builders
AI agents propose changes; trusted services validate and apply them.

### Feature-flagged experimentation
Hand tracking, UVC camera, advanced modules are optional (env flags).

### Latency-aware design
Streaming quality adapts to device/network constraints.

### Domain-generic core
The core platform is reusable for future domains (medical, industrial, education).

### Security by default
- JWT with short-lived access + refresh tokens
- Tenant isolation on every query
- Audit logging for all mutations
- Sensitivity-based LLM routing (no tenant data to free providers)
- Signed scene packages (MinIO presigned URLs)

---

## Data Flow: Prompt to VR Experience

```mermaid
sequenceDiagram
    participant User
    participant Frontend
    participant Backend
    participant LLMRouter
    participant Worker
    participant Unity
    participant Android

    User->>Frontend: Enter prompt
    Frontend->>Backend: POST /projects/{id}/intake
    Backend->>LLMRouter: Intent extraction
    LLMRouter-->>Backend: Domain + missing fields
    Backend->>Frontend: Clarification questions
    User->>Frontend: Answers questions
    Frontend->>Backend: POST /clarify
    Backend->>LLMRouter: Spec generation (architect agent)
    LLMRouter-->>Backend: SimulationSpec JSON
    Backend->>Worker: Generate scene package (async job)
    Worker->>MinIO: Upload .cymatic package
    Worker->>Backend: Scene ready
    Backend->>Frontend: Spec ready + scene package URL
    User->>Frontend: Click "Publish"
    Backend->>Unity: Signal scene package URL
    Unity->>MinIO: Download .cymatic package
    Unity->>Unity: Instantiate scene, build NavMesh
    User->>Android: Launch app, enter session ID
    Android->>Backend: Create stream session
    Backend->>Unity: Signal WebRTC offer
    Unity->>Android: WebRTC offer (SDP)
    Android->>Unity: WebRTC answer + ICE candidates
    Unity->>Android: True stereo H.264 stream
    Android->>Unity: Head pose + controller + voice input
    Unity->>Android: Stereo video stream
    Android->>Backend: Voice transcript (STT)
    Backend->>LLMRouter: Copilot query
    LLMRouter->>Backend: Copilot response
    Backend->>Android: TTS audio + actions
```

---

## Deployment Architecture

### Local Development
```
┌─────────────────────────────────────────────────────────────┐
│                    Developer Machine (Windows)              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   Docker    │  │   Unity     │  │    Android Studio   │ │
│  │  Compose    │  │  Render     │  │    + Android Phone  │ │
│  │  (Postgres, │  │  Server     │  │    (OnePlus 6T)     │ │
│  │  Redis,     │  │  (Windows)  │  │                     │ │
│  │  MinIO)     │  │             │  │                     │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │   FastAPI   │  │   Worker    │  │    Next.js Frontend   │ │
│  │   Backend   │  │  (Python)   │  │    (Port 3000)       │ │
│  │  (Port 8000)│  │  (Port 8002)│  │                      │ │
│  └─────────────┘  └─────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Production (Cloud)
```
┌──────────────────────────────────────────────────────────────┐
│                      Kubernetes Cluster                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────────────┐  │
│  │  Ingress │ │  FastAPI │ │  Worker  │ │   LLM Router    │  │
│  │  (Nginx) │ │  (x3)    │ │  (x2)    │ │   (FastAPI)     │  │
│  └──────────┘ └──────────┘ └──────────┘ └─────────────────┘  │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ PostgreSQL│ │  Redis   │ │  MinIO   │ │  Unity Render  │  │
│  │  (Primary)│ │  Cluster │ │  (S3 API)│ │  (GPU Node)    │  │
│  └──────────┘ └──────────┘ └──────────┘ └────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

---

## Security Considerations

| Layer | Measures |
|-------|----------|
| **Transport** | TLS 1.3 everywhere (Let's Encrypt / cert-manager) |
| **Authentication** | JWT (RS256), short-lived access (15m) + refresh (7d) |
| **Authorization** | RBAC (Owner/Admin/Creator/Viewer/Auditor), tenant isolation |
| **API** | Rate limiting (Redis), input validation (Pydantic), CORS |
| **LLM** | Sensitivity routing, no tenant data to free providers |
| **Storage** | MinIO SSE-S3, presigned URLs (1hr TTL), bucket policies |
| **Database** | Row-level security, encrypted connections, encrypted at rest |
| **Streaming** | DTLS-SRTP (WebRTC), TURN over TLS, signed URLs |
| **Audit** | Immutable logs (append-only), correlation IDs, 90-day retention |

---

## Scaling Strategy

| Component | Horizontal Scaling | Limits |
|---------|-------------------|--------|
| FastAPI | Stateless, k8s HPA (CPU>70%) | 100 req/s per pod |
| Worker | Stateless, k8s HPA (queue depth) | 10 concurrent jobs |
| LLM Router | Stateless, k8s HPA (latency) | 50 req/s per pod |
| Unity Render | Single GPU (no multi-GPU) | 1 concurrent stream |
| Unity Build | CI/CD pipeline | 1 build at a time |

---

## Monitoring & Observability

| Layer | Tools | Key Metrics |
|-------|-------|-------------|
| **Infrastructure** | Prometheus + Grafana | CPU, RAM, disk, network, GPU |
| **Application** | Structured logs (structlog), OpenTelemetry | Latency p50/p95/p99, error rate, throughput |
| **Business** | Custom events (PostgreSQL) | Spec generation time, stream start time, session duration |
| **LLM** | Custom dashboard | Token usage, cost, latency, fallback rate |
| **Streaming** | Custom WebRTC stats | FPS, bitrate, latency, packet loss, thermal |

---

## Disaster Recovery

| Scenario | RPO | RTO | Mitigation |
|----------|-----|-----|------------|
| PostgreSQL primary failure | <1s | <30s | Streaming replica + auto-failover (Patroni) |
| Redis failure | <1s | <10s | Redis Sentinel (3 nodes) |
| MinIO failure | <1min | <5min | Erasure coding (4+2), cross-region replication |
| Unity Render GPU failure | N/A | Manual | Spare GPU node, manual DNS switch |
| Region outage | <1hr | <4hr | Cross-region backup (daily snapshots) |

---

*Last updated: 2026-08-18*
*Version: 1.0*
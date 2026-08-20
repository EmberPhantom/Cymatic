# Agent Instructions for CYMATIC

This file defines rules for AI coding agents working in the CYMATIC repository.

It is intended for tools such as:
- Claude Code
- OpenCode
- Cursor
- Copilot-style agents
- other agentic coding assistants

---

## Project Summary

CYMATIC is a no-code AI simulation builder platform.

The MVP generates:
- real estate walkthrough simulations
- heritage walkthrough simulations

and streams them to an Android phone-based VR headset.

The platform includes:
- Next.js builder frontend
- Python FastAPI backend
- AI agent orchestration layer
- LLM router
- Unity render/streaming server
- native Android streaming client
- PostgreSQL, Redis, MinIO
- Docker-based local development environment

---

## Global Agent Rules

### 1. Specification-first design
All simulations must be generated from a structured Simulation Specification.

Do not create shortcuts that directly generate arbitrary scene state without a spec.

### 2. Agent proposals must be validated
AI agents must not directly mutate:
- database state
- Unity scene state
- runtime state
- provider policies
- billing/credit state

Allowed flow:
```text
Agent Proposal -> Schema Validation -> Trusted Service -> State Change
```

### 3. Experimental features must be feature-flagged
The following must remain optional:
- hand tracking
- external UVC camera
- advanced heritage generation
- advanced manual editing
- multiplayer
- plugin system

### 4. Sensitive data protection
Free LLM providers may only be used for:
- internal development
- non-sensitive demo content
- non-tenant test workloads

Do not route sensitive tenant data to free endpoints.

### 5. MVP performance constraints
Assume:
- low-end Android devices
- local LAN streaming
- limited thermal headroom
- one concurrent stream in MVP

Prefer:
- low-poly assets
- baked lighting
- adaptive streaming quality
- simple interaction models
- latency-first tuning

---

## Technology Defaults

### Backend
- Python 3.11+
- FastAPI
- Pydantic
- SQLAlchemy or equivalent ORM
- Alembic for migrations

### Frontend
- Next.js
- TypeScript
- React

### AI
- LiteLLM-based router or equivalent
- provider abstraction
- fallback routing
- policy layer

### Runtime
- Unity render server on Windows
- WebRTC streaming
- true stereo output

### Android
- Kotlin
- WebRTC client
- IMU orientation tracking
- controller input
- voice capture
- optional UVC camera support

### Infrastructure
- Docker Desktop
- WSL2
- Docker Compose
- MinIO
- PostgreSQL
- Redis

---

## File Ownership Guidance

When making changes, prefer this mapping:

- `apps/web/**` -> frontend changes
- `services/api/**` -> backend API changes
- `services/worker/**` -> background job changes
- `services/llm-router/**` -> LLM routing changes
- `unity/render-server/**` -> Unity runtime changes
- `android/client/**` -> Android client changes
- `infra/docker/**` -> Docker/compose changes
- `infra/k8s/**` -> Kubernetes manifests
- `schemas/**` -> shared schemas
- `docs/**` -> documentation changes

---

## Required Behavior for Coding Agents

When implementing a feature:
1. identify affected modules
2. propose file changes
3. define schema/API contract if relevant
4. implement minimal working version
5. add validation
6. add tests or test plan
7. update docs
8. note risks and follow-ups

---

## Forbidden Actions

Do not:
- remove security checks
- hardcode API keys
- introduce arbitrary code execution in MVP
- make hand tracking mandatory
- make local LLM mandatory
- add multiplayer before single-user stability
- add marketplace/plugin execution before MVP stability
- bypass the Simulation Specification model

---

## Definition of Done

A task is complete only if:
- it works in local development
- it respects feature flags
- it is documented
- it is testable
- it does not break core gaze/controller/voice interaction
- it does not introduce unapproved security risk
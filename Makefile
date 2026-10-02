# CYMATIC Development Makefile
# Supports both Windows (PowerShell) and Unix shells

.PHONY: help setup dev build test lint clean docker-build docker-build-ci docker-up docker-down docker-logs docker-ps test-docker up-mock

# Default target
help:
	@echo "CYMATIC Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Initial project setup"
	@echo "  make install        - Install all dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev            - Start full stack in hot-reload dev mode"
	@echo "  make dev-api        - Start API server only (host venv)"
	@echo "  make dev-worker     - Start worker only (host venv)"
	@echo "  make dev-llm        - Start LLM router only (host venv)"
	@echo "  make dev-web        - Start frontend only (host)"
	@echo "  make infra-up       - Start full stack (production-like images)"
	@echo "  make infra-down     - Stop stack (preserves volumes)"
	@echo "  make up-mock        - Start stack with S3 mock (offline/quay blocked)"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test           - Run all containerized test suites"
	@echo "  make test-api       - Run API suite (test DB + JUnit to ./reports)"
	@echo "  make test-worker    - Run worker suite"
	@echo "  make test-llm       - Run LLM router suite"
	@echo "  make lint           - Run all linters"
	@echo "  make lint-api       - Lint API code"
	@echo "  make lint-worker    - Lint worker code"
	@echo "  make lint-llm       - Lint LLM router code"
	@echo "  make lint-web       - Lint frontend code"
	@echo "  make typecheck      - Run type checks"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        - Run database migrations"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build   - Build all Docker images (parallel bake, local inline cache)"
	@echo "  make docker-build-ci - Build all Docker images with GHA cache (CI only)"
	@echo "  make docker-up      - Start all services with Docker Compose"
	@echo "  make docker-down    - Stop all Docker services (preserves volumes)"
	@echo "  make docker-logs SERVICE=api - Follow logs (optionally one service)"
	@echo "  make docker-ps      - List cymatic-* containers"
	@echo "  make docker-shell SERVICE=api - Shell into a service"
	@echo "  make docker-clean   - Prune unused Docker resources"
	@echo "  make generate-openapi - Generate OpenAPI specs"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make clean-all      - Clean everything including node_modules, venvs (removes volumes)"

# Detect OS
ifeq ($(OS),Windows_NT)
    VENV_BIN = .venv/Scripts
    RM = rd /s /q
    MKDIR = if not exist
else
    VENV_BIN = .venv/bin
    RM = rm -rf
    MKDIR = mkdir -p
endif

# Setup
setup:
	@echo "Setting up CYMATIC development environment..."
	@if not exist .env copy .env.example .env 2>nul || cp .env.example .env 2>/dev/null || true
	@echo "Please edit .env with your configuration"
	@echo "Run 'make install' to install dependencies"

install: install-api install-worker install-llm install-web

install-api:
	cd services/api && python -m venv .venv && $(VENV_BIN)/pip install -r requirements.txt

install-worker:
	cd services/worker && python -m venv .venv && $(VENV_BIN)/pip install -r requirements.txt

install-llm:
	cd services/llm-router && python -m venv .venv && $(VENV_BIN)/pip install -r requirements.txt

install-web:
	cd apps/web && npm install

# Paths / files
COMPOSE = docker compose -f infra/docker/docker-compose.yml
DEV_COMPOSE = docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.dev.yml
MOCK_COMPOSE = docker compose -f infra/docker/docker-compose.yml -f infra/docker/docker-compose.s3mock.yml

# Development (containerized hot-reload via dev override; infra included)
dev:
	$(DEV_COMPOSE) up -d --build
	@echo "API: http://localhost:8000"
	@echo "Worker: http://localhost:8002"
	@echo "LLM Router: http://localhost:8001"
	@echo "Frontend: http://localhost:3000"
	@echo "Viewer: http://localhost:8090"
	@echo "MinIO Console: http://localhost:9001"

dev-api:
	cd services/api && $(VENV_BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	cd services/worker && $(VENV_BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

dev-llm:
	cd services/llm-router && $(VENV_BIN)/uvicorn app.main:app --reload --host 0.0.0.0 --port 8001

dev-web:
	cd apps/web && npm run dev

infra-up:
	$(COMPOSE) up -d --build

infra-down:
	$(COMPOSE) down

infra-logs:
	$(COMPOSE) logs -f

# Local-only S3-mock stack (quay.io unreachable): same services, moto for MinIO.
# Production and CI keep real MinIO via the base file.
up-mock:
	$(MOCK_COMPOSE) up -d --build

# Testing — containerized suites (isolated test DBs, JUnit XML to ./reports)
test: test-docker

test-docker: test-api test-worker test-llm
	@echo "JUnit reports in ./reports/"

test-api:
	$(COMPOSE) --profile test run --rm --build test-api

test-worker:
	$(COMPOSE) --profile test run --rm --build test-worker

test-llm:
	$(COMPOSE) --profile test run --rm --build test-llm-router

# Host-venv suites (fast iteration, needs local Postgres/Redis running)
test-host-api:
	cd services/api && $(VENV_BIN)/pytest tests/ -v

test-host-worker:
	cd services/worker && $(VENV_BIN)/pytest tests/ -v

test-host-llm:
	cd services/llm-router && $(VENV_BIN)/pytest tests/ -v

# Linting
lint: lint-api lint-worker lint-llm lint-web

lint-api:
	cd services/api && $(VENV_BIN)/ruff check app/

lint-worker:
	cd services/worker && $(VENV_BIN)/ruff check app/

lint-llm:
	cd services/llm-router && $(VENV_BIN)/ruff check app/

lint-web:
	cd apps/web && npm run lint

# Type checking
typecheck:
	cd services/api && $(VENV_BIN)/mypy app/
	cd services/worker && $(VENV_BIN)/mypy app/
	cd services/llm-router && $(VENV_BIN)/mypy app/
	cd apps/web && npm run type-check

# Database
migrate:
	cd services/api && $(VENV_BIN)/alembic upgrade head

# Docker — parallel buildx bake (per-service contexts via bake file).
# Local uses the inline cache from docker-bake.hcl (offline-friendly).
# CI-only GHA cache lives in docker-bake.ci.hcl (needs ACTIONS_CACHE_URL).
docker-build:
	docker buildx bake -f docker-bake.hcl

docker-build-ci:
	docker buildx bake -f docker-bake.hcl -f docker-bake.ci.hcl --progress plain

docker-up:
	$(COMPOSE) up -d --build

docker-down:
	$(COMPOSE) down

docker-logs:
	$(COMPOSE) logs -f $(SERVICE)

docker-ps:
	$(COMPOSE) ps

docker-shell:
	$(COMPOSE) exec $(SERVICE) sh

docker-clean:
	@echo "Pruning Docker resources (preserves volumes)..."
	docker container prune -f
	docker image prune -f
	docker network prune -f
	docker builder prune -f --filter "until=24h"
	docker system df

generate-openapi:
	python scripts/generate_openapi.py

# Cleanup — preserve volumes by default; use clean-all to remove volumes
clean:
	$(RM) services/api/__pycache__ 2>nul || true
	$(RM) services/api/.pytest_cache 2>nul || true
	$(RM) services/api/.mypy_cache 2>nul || true
	$(RM) services/worker/__pycache__ 2>nul || true
	$(RM) services/worker/.pytest_cache 2>nul || true
	$(RM) services/worker/.mypy_cache 2>nul || true
	$(RM) services/llm-router/__pycache__ 2>nul || true
	$(RM) services/llm-router/.pytest_cache 2>nul || true
	$(RM) services/llm-router/.mypy_cache 2>nul || true
	$(RM) apps/web/.next 2>nul || true

clean-all: clean
	$(RM) services/api/.venv 2>nul || true
	$(RM) services/worker/.venv 2>nul || true
	$(RM) services/llm-router/.venv 2>nul || true
	$(RM) apps/web/node_modules 2>nul || true
	$(RM) apps/viewer/node_modules 2>nul || true
	$(RM) reports 2>nul || true
	$(COMPOSE) down --remove-orphans 2>nul || true
	docker system prune -f 2>nul || true

# Full volume removal — explicit, destructive
docker-down-v:
	$(COMPOSE) down -v --remove-orphans

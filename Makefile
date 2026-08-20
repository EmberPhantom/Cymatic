# CYMATIC Development Makefile
# Supports both Windows (PowerShell) and Unix shells

.PHONY: help setup dev build test lint clean

# Default target
help:
	@echo "CYMATIC Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make setup          - Initial project setup"
	@echo "  make install        - Install all dependencies"
	@echo ""
	@echo "Development:"
	@echo "  make dev            - Start all services in development mode"
	@echo "  make dev-api        - Start API server only"
	@echo "  make dev-worker     - Start worker only"
	@echo "  make dev-llm        - Start LLM router only"
	@echo "  make dev-web        - Start frontend only"
	@echo "  make infra-up       - Start infrastructure (Postgres, Redis, MinIO)"
	@echo "  make infra-down     - Stop infrastructure"
	@echo ""
	@echo "Testing & Quality:"
	@echo "  make test           - Run all tests"
	@echo "  make test-api       - Run API tests"
	@echo "  make test-worker    - Run worker tests"
	@echo "  make test-llm       - Run LLM router tests"
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
	@echo "  make docker-build   - Build all Docker images"
	@echo "  make docker-up      - Start all services with Docker Compose"
	@echo "  make docker-down    - Stop all Docker services"
	@echo ""
	@echo "Cleanup:"
	@echo "  make clean          - Clean build artifacts"
	@echo "  make clean-all      - Clean everything including node_modules, venvs"

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

# Development
dev: infra-up
	@echo "Starting all services..."
	@echo "API: http://localhost:8000"
	@echo "Worker: http://localhost:8002"
	@echo "LLM Router: http://localhost:8001"
	@echo "Frontend: http://localhost:3000"
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
	docker compose -f infra/docker/docker-compose.yml up -d

infra-down:
	docker compose -f infra/docker/docker-compose.yml down

infra-logs:
	docker compose -f infra/docker/docker-compose.yml logs -f

# Testing
test: test-api test-worker test-llm

test-api:
	cd services/api && $(VENV_BIN)/pytest tests/ -v

test-worker:
	cd services/worker && $(VENV_BIN)/pytest tests/ -v

test-llm:
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

# Docker
docker-build:
	docker build -t cymatic/api:latest ./services/api
	docker build -t cymatic/worker:latest ./services/worker
	docker build -t cymatic/llm-router:latest ./services/llm-router
	docker build -t cymatic/web:latest ./apps/web

docker-up:
	docker compose -f infra/docker/docker-compose.yml up -d --build

docker-down:
	docker compose -f infra/docker/docker-compose.yml down -v

# Cleanup
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
	docker compose -f infra/docker/docker-compose.yml down -v --remove-orphans 2>nul || true
	docker system prune -f 2>nul || true

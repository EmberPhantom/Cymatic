"""Worker test configuration - database setup and LLM mocking.

Provides:
  - PostgreSQL test database with alembic migrations
  - Redis + MinIO environment config
  - LLM client mocking for test isolation
"""
import asyncio
import json as _json
import os
import sys
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker  # noqa: F401 - kept for fallback compat
from sqlalchemy.pool import NullPool
from alembic.config import Config
from alembic import command

from cymatic_shared.utils import to_async_db_url

# ---------------------------------------------------------------------------
# Environment defaults — must be set BEFORE importing any app module
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only-32charslong")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cymatic:cymatic@localhost:5432/cymatic_worker_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
os.environ.setdefault("S3_BUCKET_NAME", "cymatic")
os.environ.setdefault("S3_REGION", "us-east-1")
os.environ.setdefault("LLM_ROUTER_URL", "http://localhost:8001")

# ---------------------------------------------------------------------------
# Path setup + app imports
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from services.worker.app.main import app as _app_try  # noqa: F401
    from services.worker.app.db.session import get_db as _get_db_try  # noqa: F401
    from services.worker.app.core.config import get_settings as _get_settings_try  # noqa: F401
    from cymatic_shared.db import Base as _Base_try  # noqa: F401

    app = _app_try  # type: ignore[no-redef]
    get_db = _get_db_try  # type: ignore[no-redef]
    Base = _Base_try  # type: ignore[no-redef]
except ModuleNotFoundError:
    from app.main import app  # type: ignore[no-redef]
    from app.db.session import get_db  # type: ignore[no-redef]
    from cymatic_shared.db import Base  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Test engine + session factory
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = to_async_db_url(
    os.environ.get("DATABASE_URL", "postgresql://cymatic:cymatic@localhost:5432/cymatic")
)

engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


# ---------------------------------------------------------------------------
# Database Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """Apply Alembic migrations only. No create_all fallback."""
    # Wait for PostgreSQL to be ready (mirrors api conftest)
    sync_url = TEST_DATABASE_URL.replace("+asyncpg", "")
    for attempt in range(30):
        try:
            import asyncpg
            conn = await asyncpg.connect(sync_url)
            await conn.close()
            break
        except Exception:
            if attempt == 29:
                raise RuntimeError("PostgreSQL not ready after 30s")
            await asyncio.sleep(1)

    alembic_dir = os.path.join(os.path.dirname(__file__), '..')
    alembic_cfg = Config(os.path.join(alembic_dir, "alembic.ini"))
    # Use sync URL for alembic
    alembic_cfg.set_main_option("sqlalchemy.url", sync_url)
    command.upgrade(alembic_cfg, "head")
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session(setup_db) -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# LLM Mock Fixtures
# ---------------------------------------------------------------------------

def _intake_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None, **kwargs):
    """Return intake-appropriate mock data based on prompt content."""
    content = messages[1]["content"] if len(messages) > 1 else ""
    prompt = content.split("Prompt: ")[1].split("\n")[0] if "Prompt: " in content else content.lower()

    is_heritage = any(kw in prompt.lower() for kw in ("heritage", "temple", "monument", "palace", "museum", "courtyard"))

    if is_heritage:
        return {
            "detected_domain": "heritage",
            "objective": prompt,
            "missing_fields": ["site_type", "narration"],
            "suggested_questions": [
                "What type of heritage site?",
                "Do you need guided narration?",
            ],
            "extracted_entities": {},
            "confidence": 0.85,
        }

    return {
        "detected_domain": "real_estate",
        "objective": prompt,
        "missing_fields": ["style", "bedrooms"],
        "suggested_questions": [
            "What architectural style do you prefer?",
            "How many bedrooms do you need?",
        ],
        "extracted_entities": {},
        "confidence": 0.85,
    }


def _clarification_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None, **kwargs):
    """Return clarification mock data. The user message contains the merged answers."""
    content = messages[1]["content"] if len(messages) > 1 else "{}"
    try:
        data = _json.loads(content)
    except (_json.JSONDecodeError, IndexError):
        data = {}

    # current_answers already has converted values from convert_value()
    updated_fields = data.get("current_answers", {})

    return {
        "questions": [],
        "updated_fields": updated_fields,
        "ready_for_generation": False,
        "completion_percentage": 0.6,
    }


def _architect_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None, **kwargs):
    """Return architect mock data - a valid SimulationSpec dict (includes has_window for domain compliance)."""
    return {
        "domain": "real_estate",
        "metadata": {"title": "Test Apartment", "description": "Generated spec", "version": "1.0"},
        "entities": [
            {"id": "room1", "type": "room", "name": "Living Room", "position": [0, 0, 0], "properties": {"size": [15, 20, 10], "has_window": True, "has_doors": True, "style": "modern"}},
            {"id": "room2", "type": "room", "name": "Bedroom", "position": [20, 0, 0], "properties": {"size": [12, 12, 10], "has_window": True, "has_doors": True, "style": "modern"}},
        ],
        "navigation": {
            "points": [
                {"id": "nav1", "name": "Living Room", "position": [7.5, 1.6, 10], "connections": ["nav2"]},
                {"id": "nav2", "name": "Bedroom", "position": [26, 1.6, 6], "connections": ["nav1"]},
            ],
            "paths": [{"from_point": "nav1", "to": "nav2"}],
            "default_start_point": "nav1",
        },
        "lighting": {"preset": "warm", "time_of_day": "evening", "ambient_intensity": 0.8},
        "copilot_policy": {"enabled": True, "languages": ["en"], "default_language": "en", "personality": "helpful_guide"},
        "performance_budget": {"target_fps": 60, "max_triangles": 100000, "max_draw_calls": 50, "texture_budget_mb": 100},
    }


def _dispatch_llm(messages, task_type="copilot_chat", **kwargs):
    """Route to the correct mock based on task_type."""
    if task_type == "intent_extraction":
        return _intake_mock(messages, task_type=task_type, **kwargs)
    elif task_type == "clarification":
        return _clarification_mock(messages, task_type=task_type, **kwargs)
    elif task_type == "spec_generation":
        return _architect_mock(messages, task_type=task_type, **kwargs)
    return {}


async def _async_dispatch_llm(messages, task_type="copilot_chat", **kwargs):
    """Async wrapper for _dispatch_llm so AsyncMock awaits correctly."""
    return _dispatch_llm(messages, task_type=task_type, **kwargs)


@pytest.fixture(autouse=True)
def mock_llm_client():
    """Mock call_llm_json at all consumer namespaces.

    Patch targets cover:
      - cymatic_shared primary client and agent re-exports
      - worker app core and architect consumers
      - services.worker.* alternate import path (PYTHONPATH . ../../)
    """
    mock = AsyncMock(side_effect=_async_dispatch_llm)

    patch_targets = [
        "cymatic_shared.agents.llm_client.call_llm_json",
        "cymatic_shared.agents.intake_agent.call_llm_json",
        "cymatic_shared.agents.clarification_agent.call_llm_json",
        "app.core.llm_client.call_llm_json",
        "app.agents.architect_agent.call_llm_json",
        "services.worker.app.core.llm_client.call_llm_json",
        "services.worker.app.agents.architect_agent.call_llm_json",
    ]

    patches = []
    for target in patch_targets:
        try:
            p = patch(target, mock)
            p.start()
            patches.append(p)
        except ModuleNotFoundError:
            continue

    yield mock

    for p in patches:
        p.stop()
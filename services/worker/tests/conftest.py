"""Worker test configuration - database setup and LLM mocking.

Provides:
  - PostgreSQL test database with alembic migrations
  - Redis + MinIO environment config
  - LLM client mocking for test isolation
"""
import json as _json
import os
import sys
import pytest
import pytest_asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
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
    from services.worker.app.main import app
    from services.worker.app.db.session import get_db
    from services.worker.app.core.config import get_settings
    from cymatic_shared.db import Base
except ModuleNotFoundError:
    from app.main import app
    from app.db.session import get_db
    from app.core.config import get_settings
    from cymatic_shared.db import Base

# ---------------------------------------------------------------------------
# Test engine + session factory
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = to_async_db_url(
    os.environ.get("DATABASE_URL", "postgresql://cymatic:cymatic@localhost:5432/cymatic")
)

engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
    # Use API's alembic.ini since worker shares the same database schema
    alembic_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'api')
    alembic_cfg = Config(os.path.join(alembic_dir, "alembic.ini"))
    # Use sync URL for alembic
    sync_url = TEST_DATABASE_URL.replace("+asyncpg", "")
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

def _intake_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None):
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


def _clarification_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None):
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


def _architect_mock(messages, task_type="copilot_chat", sensitivity="internal", temperature=0.3, max_tokens=None):
    """Return architect mock data - a valid SimulationSpec dict."""
    return {
        "domain": "real_estate",
        "metadata": {"title": "Test Apartment", "description": "Generated spec", "version": "1.0"},
        "entities": [
            {"id": "room1", "type": "room", "name": "Living Room", "position": [0, 0, 0], "properties": {"size": [15, 20, 10]}},
            {"id": "room2", "type": "room", "name": "Bedroom", "position": [20, 0, 0], "properties": {"size": [12, 12, 10]}},
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


@pytest.fixture(autouse=True)
def mock_llm_client():
    """Mock call_llm_json at consumer namespaces.

    Patch targets:
      - cymatic_shared.agents.intake_agent.call_llm_json
      - cymatic_shared.agents.clarification_agent.call_llm_json
    """
    mock = AsyncMock(side_effect=_dispatch_llm)

    patches = [
        patch("cymatic_shared.agents.intake_agent.call_llm_json", mock),
        patch("cymatic_shared.agents.clarification_agent.call_llm_json", mock),
    ]

    for p in patches:
        p.start()

    yield mock

    for p in patches:
        p.stop()
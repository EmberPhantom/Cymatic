"""Pytest configuration for API tests.

Fixes:
  - pytest-asyncio 0.24+ with session-scoped event loop for all fixtures and tests
  - Unique emails per fixture to avoid IntegrityError collisions
  - Alembic-only schema (no create_all fallback)
  - Hard-fail on import errors instead of silent pass
"""
import pytest
import pytest_asyncio
import sys
import os
import uuid
import asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
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
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cymatic:cymatic@localhost:5432/cymatic_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
os.environ.setdefault("S3_BUCKET_NAME", "cymatic")
os.environ.setdefault("S3_REGION", "us-east-1")

# ---------------------------------------------------------------------------
# Path setup + app imports
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

try:
    from app.main import app
    from app.db.session import Base, get_db
    from app.core.config import get_settings
except ModuleNotFoundError:
    from services.api.app.main import app
    from services.api.app.db.session import Base, get_db
    from services.api.app.core.config import get_settings

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
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="session")
async def setup_db():
    """Apply Alembic migrations only. No create_all fallback."""
    # Wait for PostgreSQL to be ready
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
async def client(setup_db) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db_session(setup_db) -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus
from app.core.security import get_password_hash, create_access_token
from cymatic_shared.agents.intake_agent import IntakeResult
from cymatic_shared.agents.clarification_agent import ClarificationResult
from cymatic_shared.agents.clarification_agent import ClarificationQuestion


@pytest.fixture(autouse=True)
def deterministic_agent_results(monkeypatch):
    """Keep endpoint tests deterministic and independent of live LLM providers."""
    async def intake(prompt, context=None):
        return IntakeResult(
            detected_domain="real_estate",
            objective=prompt,
            missing_fields=["bedrooms"],
            suggested_questions=["How many bedrooms are required?"],
            extracted_entities={},
            confidence=0.95,
        )

    async def clarify(domain, current_answers, new_answers):
        return ClarificationResult(
            questions=[],
            updated_fields=dict(new_answers),
            ready_for_generation=True,
            completion_percentage=1.0,
        )

    monkeypatch.setattr("app.api.v1.endpoints.specs.process_intake", intake)
    monkeypatch.setattr("app.api.v1.endpoints.specs.process_clarification_answers", clarify)


@pytest_asyncio.fixture
async def test_user(db_session):
    organization = Organization(name="Fixture Organization", plan="free")
    db_session.add(organization)
    await db_session.flush()
    """Fixture user — uses a unique email to avoid collision with test_register_user."""
    user = User(
        email=f"fixture-{uuid.uuid4().hex[:10]}@example.com",
        name="Fixture User",
        hashed_password=get_password_hash("testpass123"),
        role=UserRole.CREATOR,
        organization_id=organization.id,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_headers(test_user):
    access_token = create_access_token(
        data={"sub": str(test_user.id), "email": test_user.email, "org_id": test_user.organization_id}
    )
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def test_project(db_session, test_user):
    project = Project(
        name="Test Project",
        domain="real_estate",
        category="apartment",
        organization_id=test_user.organization_id,
        created_by=test_user.id,
        status=ProjectStatus.DRAFT,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project
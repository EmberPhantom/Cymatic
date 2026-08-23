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
import subprocess
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

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
    from services.api.app.main import app
    from services.api.app.db.session import Base, get_db
    from services.api.app.core.config import get_settings
except ModuleNotFoundError:
    from app.main import app
    from app.db.session import Base, get_db
    from app.core.config import get_settings

# ---------------------------------------------------------------------------
# Test engine + session factory
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = to_async_db_url(
    os.environ.get("DATABASE_URL", "postgresql://cymatic:cymatic@localhost:5432/cymatic")
)

engine = create_async_engine(TEST_DATABASE_URL, echo=False, pool_pre_ping=True)
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
    alembic_dir = os.path.join(os.path.dirname(__file__), '..')
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from alembic.config import CommandLine; CommandLine(prog='alembic').main()",
            "-c",
            "alembic.ini",
            "upgrade",
            "head",
        ],
        cwd=alembic_dir,
        capture_output=True,
        text=True,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL.replace("+asyncpg", "")},
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Alembic migration failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
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


from app.models.user import User, UserRole
from app.models.project import Project, ProjectStatus
from app.core.security import get_password_hash, create_access_token


@pytest_asyncio.fixture
async def test_user(db_session):
    """Fixture user — uses a unique email to avoid collision with test_register_user."""
    user = User(
        email="fixture@example.com",
        name="Fixture User",
        hashed_password=get_password_hash("testpass123"),
        role=UserRole.CREATOR,
        organization_id=1,
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

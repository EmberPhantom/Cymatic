"""Pytest configuration"""
import pytest
import asyncio
import sys
import os
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Set required environment variables BEFORE importing settings
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only-32charslong")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://cymatic:cymatic@localhost:5432/cymatic_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("S3_ENDPOINT", "http://localhost:9000")
os.environ.setdefault("S3_ACCESS_KEY", "minioadmin")
os.environ.setdefault("S3_SECRET_KEY", "minioadmin")
os.environ.setdefault("S3_BUCKET_NAME", "cymatic")
os.environ.setdefault("S3_REGION", "us-east-1")

# Add the services directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from services.api.app.main import app
from services.api.app.db.session import Base, get_db
from services.api.app.core.config import get_settings

# Override settings for testing
settings = get_settings()

# Test database
TEST_DATABASE_URL = "postgresql+asyncpg://cymatic:cymatic@localhost:5432/cymatic_test"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(setup_db) -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session(setup_db) -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session
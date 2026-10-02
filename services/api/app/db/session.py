"""API database session management."""

from collections.abc import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from cymatic_shared.db import (
    create_cymatic_engine,
)  # re-export for Alembic and tests  # noqa: F401
from cymatic_shared.utils import to_async_db_url
from app.core.config import get_settings

settings = get_settings()

# Use shared helper with safe pool sizes (keep total < Postgres max_connections 100)
# api: 5 + 10 = 15, worker: 5 + 10 = 15, total 30 + overhead < 50
engine = create_cymatic_engine(
    to_async_db_url(settings.DATABASE_URL),
    echo=settings.DEBUG,
    pool_size=getattr(settings, "DB_POOL_SIZE", 5),
    max_overflow=getattr(settings, "DB_MAX_OVERFLOW", 10),
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    """Verify database connectivity. Schema managed by Alembic migrations."""
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    await engine.dispose()

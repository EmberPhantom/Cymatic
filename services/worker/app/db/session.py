"""Worker database session management."""
from collections.abc import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from cymatic_shared.db import create_cymatic_engine
from cymatic_shared.utils import to_async_db_url
from app.core.config import get_settings

settings = get_settings()

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

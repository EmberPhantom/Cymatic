"""Worker database session management."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from cymatic_shared.db import Base
from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
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

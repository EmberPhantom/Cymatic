"""Shared SQLAlchemy Base and database utilities."""
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

# Keep total pooled connections well below Postgres max_connections (100)
# Services: api (5+10) + worker (5+10) = 30, plus migrate/test overhead <50 safe
DEFAULT_POOL_SIZE = 5
DEFAULT_MAX_OVERFLOW = 10
DEFAULT_POOL_PRE_PING = True
DEFAULT_POOL_RECYCLE = 3600


def create_cymatic_engine(
    url: str,
    *,
    pool_size: int = DEFAULT_POOL_SIZE,
    max_overflow: int = DEFAULT_MAX_OVERFLOW,
    echo: bool = False,
    pool_pre_ping: bool = DEFAULT_POOL_PRE_PING,
    pool_recycle: int = DEFAULT_POOL_RECYCLE,
) -> AsyncEngine:
    """Create async engine with safe pool defaults.

    Total `pool_size + max_overflow` per service should keep sum across all
    services < Postgres max_connections (default 100 in docker-compose).
    """
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=pool_pre_ping,
        pool_recycle=pool_recycle,
        pool_size=pool_size,
        max_overflow=max_overflow,
    )


def create_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

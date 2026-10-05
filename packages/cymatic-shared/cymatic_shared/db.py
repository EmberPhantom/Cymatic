"""Shared SQLAlchemy Base and database utilities."""

import hashlib

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
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


_ADVISORY_KEY_MASK = (1 << 63) - 1


def advisory_lock_key(namespace: str, *parts: object) -> int:
    """Derive a collision-free bigint key for pg_advisory_xact_lock.

    Postgres advisory locks accept only a bigint (or an int pair) — NOT
    strings — so a namespaced string key is impossible at the SQL layer.
    Hashing ``"<namespace>:<part>:..."`` into 63 bits instead gives:
    distinct namespaces (e.g. "scene" vs "spec") can never collide with
    each other, and same-namespace collisions need a ~2^31-key birthday
    hit on SHA-256's top 63 bits (vs. the old scheme where
    ``spec_id * 100000 + project_id % 100000`` collided across pairs and
    with bare ``int(project_id)`` keys). Fits in a signed bigint.
    """
    text = namespace + ":" + ":".join(str(p) for p in parts)
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") & _ADVISORY_KEY_MASK

"""Shared SQLAlchemy Base and database utilities."""
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text


class Base(DeclarativeBase):
    pass

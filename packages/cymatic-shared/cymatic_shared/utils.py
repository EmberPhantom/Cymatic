"""General-purpose shared utilities."""


def to_async_db_url(url: str) -> str:
    """Convert sync PostgreSQL URL to async (asyncpg) URL."""
    return url.replace("postgresql://", "postgresql+asyncpg://").replace(
        "postgres://", "postgresql+asyncpg://"
    )

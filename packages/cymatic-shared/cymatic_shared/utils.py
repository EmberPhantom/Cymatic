"""General-purpose shared utilities."""
from urllib.parse import urlsplit, urlunsplit

try:
    from sqlalchemy.engine.url import make_url  # type: ignore

    def to_async_db_url(url: str) -> str:
        """Convert sync PostgreSQL URL to async (asyncpg) URL via SQLAlchemy URL parsing.

        Handles `postgresql://`, `postgres://`, and `postgresql+psycopg2://` safely,
        preserving user, password (even if it contains ://), host, port, query.
        """
        try:
            sa_url = make_url(url)
            # Normalize drivername to asyncpg
            if sa_url.drivername in ("postgresql", "postgres", "postgresql+psycopg2", "postgresql+psycopg"):
                sa_url = sa_url.set(drivername="postgresql+asyncpg")
            elif sa_url.drivername == "postgresql+asyncpg":
                pass
            else:
                # Fallback for non-postgres URLs: return as-is
                return url
            return sa_url.render_as_string(hide_password=False)
        except Exception:
            # Fallback to urlsplit parsing if make_url fails
            pass

        # Fallback manual parsing
        parts = urlsplit(url)
        scheme = parts.scheme
        if scheme in ("postgresql", "postgres"):
            scheme = "postgresql+asyncpg"
        elif scheme == "postgresql+psycopg2":
            scheme = "postgresql+asyncpg"
        return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))

except ImportError:

    def to_async_db_url(url: str) -> str:
        """Fallback without SQLAlchemy."""
        parts = urlsplit(url)
        scheme = parts.scheme
        if scheme in ("postgresql", "postgres", "postgresql+psycopg2"):
            scheme = "postgresql+asyncpg"
        return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))

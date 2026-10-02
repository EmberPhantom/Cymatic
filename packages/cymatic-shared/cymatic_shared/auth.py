"""Shared admin-key auth + logging bootstrap. Single source.

Admin-key semantics (standard): dual header (X-Api-Key or Bearer),
constant-time compare, 503 when unset (fail-closed), 401 on mismatch.
"""
import hmac
import logging
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Header, HTTPException


def verify_admin_key_dependency(
    admin_key: str | Callable[[], str],
) -> Callable[[str | None, str | None], Awaitable[None]]:
    """Build a FastAPI dependency enforcing one admin key (standard semantics).

    The key is resolved lazily per request (callable supported) so tests and
    key rotation that mutate settings after import keep working.
    """

    def _resolve() -> str:
        return admin_key() if callable(admin_key) else admin_key

    async def _dep(
        x_api_key: str | None = Header(None, alias="X-Api-Key"),
        authorization: str | None = Header(None, alias="Authorization"),
    ) -> None:
        key = _resolve()
        if not key:
            raise HTTPException(status_code=503, detail="Admin API key not configured")
        token: str | None = None
        if x_api_key:
            token = x_api_key.strip()
        elif authorization:
            auth = authorization.strip()
            token = auth[7:].strip() if auth.lower().startswith("bearer ") else auth
        if token is None or not hmac.compare_digest(token, key):
            raise HTTPException(status_code=401, detail="Invalid or missing admin API key")

    return _dep


def configure_logging(service: str, log_format: str = "json") -> None:
    """One logging bootstrap for all services (JSON in prod-shaped output)."""
    renderer = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,  # type: ignore[list-item]
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(),
    )
    structlog.get_logger().info("logging_configured", service=service, format=log_format)

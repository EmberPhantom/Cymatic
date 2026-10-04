"""Redis sliding-window rate limiter with org/user scoping.

Sliding-window mechanics live in shared rate_limit_core (add-first order
preserved here); this module keeps router-specific identifier resolution
and per-provider limits.
"""

from collections.abc import Awaitable, Callable

import redis.asyncio as redis
import structlog
from fastapi import HTTPException, Request

from app.core.config import get_settings
from cymatic_shared.rate_limit_core import parse_limit, sliding_check  # noqa: F401

settings = get_settings()
logger = structlog.get_logger()
_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    global _redis
    if _redis is None:
        try:
            # DB 3 = rate limiting (isolated)
            redis_url = getattr(settings, "REDIS_RATE_URL", None) or settings.REDIS_URL
            _redis = redis.from_url(redis_url, decode_responses=True)
        except Exception:
            _redis = None
    return _redis


def _get_forwarded_ip(request: Request) -> str | None:
    xff = request.headers.get("x-forwarded-for") or request.headers.get(
        "X-Forwarded-For"
    )
    if xff:
        # Take first IP in list (client origin)
        return xff.split(",")[0].strip()
    forwarded = request.headers.get("forwarded")
    if forwarded:
        # Forwarded: for=1.2.3.4;proto=http
        for part in forwarded.split(";"):
            part = part.strip()
            if part.lower().startswith("for="):
                ip = part[4:].strip().strip('"').strip("[]")
                return ip.split(":")[0]
    return None


def _resolve_identifier(request: Request) -> str:
    # Prioritize org/user scoping over IP
    # Check state (set by auth middleware if available)
    state = getattr(request, "state", None)
    if state is not None:
        org = getattr(state, "organization_id", None) or getattr(state, "org_id", None)
        if org:
            return f"org:{org}"
        user = getattr(state, "user_id", None)
        if user:
            return f"user:{user}"
        if getattr(state, "authenticated", False):
            # Server-verified caller with no per-principal identity (e.g. a
            # shared data-plane API key). Client-controlled headers and
            # X-Forwarded-For are spoofable, so they must not mint a fresh
            # bucket here — fall back to the TCP peer address instead.
            host = request.client.host if request.client else "unknown"
            return f"ip:{host}"
    # Check headers
    for header in ("x-organization-id", "x-org-id", "x-provider-org", "x-tenant-id"):
        val = request.headers.get(header) or request.headers.get(header.title())
        if val:
            return f"org:{val.strip()}"
    for header in ("x-user-id", "x-api-user"):
        val = request.headers.get(header) or request.headers.get(header.title())
        if val:
            return f"user:{val.strip()}"
    # Fallback to X-Forwarded-For / client IP
    f_ip = _get_forwarded_ip(request)
    if f_ip:
        return f"ip:{f_ip}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"


async def is_rate_limited(key: str, limit: str) -> tuple[bool, int]:
    """Sliding window check via shared core (add-first order preserved).

    Returns (is_limited, retry_after_seconds). Fail-closed on Redis error.
    """
    r = _get_redis()
    if r is None:
        # Fail-closed: if Redis unavailable, deny to avoid abuse
        return True, 60
    try:
        count, window = parse_limit(limit)
    except Exception:
        return True, 60
    return await sliding_check(r, f"rl:sliding:{key}", count, window, add_first=True)


async def is_rate_limited_for_provider(
    provider: str, org_or_user: str, limit: str
) -> tuple[bool, int]:
    """Per-provider sliding window."""
    key = f"provider:{provider}:{org_or_user}"
    return await is_rate_limited(key, limit)


async def rate_limit_dependency(request: Request, limit: str | None = None) -> None:
    # Resolve limit: explicit or default from settings
    effective_limit = limit or settings.RATE_LIMIT_LLM
    identifier = _resolve_identifier(request)
    # Include path to scope, but per-provider check is handled separately
    key = f"{identifier}:{request.url.path}"
    limited, retry_after = await is_rate_limited(key, effective_limit)
    if limited:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )
    # Per-provider limits: if request hints at provider via header or query, enforce
    provider_hint = request.headers.get("x-provider") or request.query_params.get(
        "provider"
    )
    if provider_hint:
        # Map provider to its configured rpm limit if known
        try:
            from app.schemas.providers import (
                ProviderName,
            )  # local import to avoid cycle

            # Try to resolve provider config for limit
            # Fallback to generic limit if not found
            prov = provider_hint.strip().lower()
            # Try to find provider config via routing_engine
            from app.routing.engine import routing_engine

            cfg = (
                routing_engine.providers.get(ProviderName(prov))
                if prov in [p.value for p in ProviderName]
                else None
            )
            if cfg is not None:
                prov_limit = f"{cfg.rate_limit_rpm}/minute"
            else:
                prov_limit = effective_limit
            p_limited, p_retry = await is_rate_limited_for_provider(
                prov, identifier, prov_limit
            )
            if p_limited:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for provider {prov}",
                    headers={"Retry-After": str(p_retry)},
                )
        except HTTPException:
            raise
        except Exception:
            # Fail-closed already handled in is_rate_limited
            pass


def rate_limit(limit: str) -> Callable[[Request], Awaitable[None]]:
    async def _dep(request: Request) -> None:
        await rate_limit_dependency(request, limit)

    return _dep

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


# Per-path default limits. Chat uses the shared RATE_LIMIT_LLM default;
# embeddings/audio use stricter buckets. An explicit `limit` argument always
# wins (backward compatible); otherwise the path map wins; otherwise
# settings.RATE_LIMIT_LLM.
_PATH_DEFAULT_LIMITS: dict[str, str] = {
    "/v1/embeddings": "30/minute",
    "/v1/audio/transcriptions": "20/minute",
    "/v1/audio/speech": "20/minute",
}


def _default_limit_for_path(path: str, fallback: str) -> str:
    for prefix, path_limit in _PATH_DEFAULT_LIMITS.items():
        if path == prefix or path.startswith(prefix + "/"):
            return path_limit
    return fallback


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
    # Resolve limit: explicit arg wins (backward compatible), else per-path
    # default, else shared settings.RATE_LIMIT_LLM.
    path = request.url.path or ""
    if limit is not None:
        effective_limit = limit
    else:
        effective_limit = _default_limit_for_path(path, settings.RATE_LIMIT_LLM)
    identifier = _resolve_identifier(request)
    # Include path to scope, but per-provider check is handled separately
    key = f"{identifier}:{path}"
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
        prov = provider_hint.strip().lower()
        # Known-provider check first (enum + live routing table).
        from app.schemas.providers import ProviderName  # local import to avoid cycle
        from app.routing.engine import routing_engine

        known_values = [p.value for p in ProviderName]
        is_known = prov in known_values
        if not is_known:
            logger.debug("rate_limit_unknown_provider_hint", hint=provider_hint)
            return
        # Known provider hint: fail closed (deny) when the limit cannot be
        # evaluated; never silently skip the provider check.
        try:
            cfg = None
            try:
                cfg = routing_engine.providers.get(ProviderName(prov))
            except Exception as e:
                logger.warning(
                    "rate_limit_provider_resolve_failed", provider=prov, error=str(e)
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit unavailable for provider {prov}",
                    headers={"Retry-After": "60"},
                ) from e
            if cfg is not None:
                prov_limit = f"{cfg.rate_limit_rpm}/minute"
            else:
                prov_limit = effective_limit
            try:
                p_limited, p_retry = await is_rate_limited_for_provider(
                    prov, identifier, prov_limit
                )
            except Exception as e:
                logger.warning(
                    "rate_limit_provider_check_failed", provider=prov, error=str(e)
                )
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit unavailable for provider {prov}",
                    headers={"Retry-After": "60"},
                ) from e
            if p_limited:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for provider {prov}",
                    headers={"Retry-After": str(p_retry)},
                )
        except HTTPException:
            raise


def rate_limit(limit: str | None = None) -> Callable[[Request], Awaitable[None]]:
    async def _dep(request: Request) -> None:
        await rate_limit_dependency(request, limit)

    return _dep

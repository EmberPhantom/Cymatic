"""Redis sliding-window rate limiter (fail-closed). Single source.

Services configure the Redis URL once at import via
``configure_rate_limit(settings.REDIS_RATE_URL or settings.REDIS_URL)``
and re-export this module's names. The llm-router keeps its own variant
(per-provider limits) — see tech-debt.
"""
import asyncio
from typing import Optional
import redis.asyncio as redis
import structlog
from fastapi import Request, HTTPException

from cymatic_shared.rate_limit_core import parse_limit, sliding_check

logger = structlog.get_logger()

__all__ = [
    "configure_rate_limit", "is_rate_limited", "parse_limit",
    "rate_limit", "rate_limit_dependency", "_get_redis", "_reset_redis",
]

_redis_url: Optional[str] = None
_redis: Optional[redis.Redis] = None
_redis_loop: Optional[asyncio.AbstractEventLoop] = None


def configure_rate_limit(redis_url: Optional[str]) -> None:
    """Set the Redis URL for rate-limit state (call once per process)."""
    global _redis_url
    _redis_url = redis_url


def _reset_redis() -> None:
    global _redis, _redis_loop
    _redis = None
    _redis_loop = None


def _get_redis() -> Optional[redis.Redis]:
    """Loop-aware lazy client."""
    global _redis, _redis_loop
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if _redis is not None and running is not None and _redis_loop is not running:
        _reset_redis()
    if _redis is None:
        if not _redis_url:
            logger.warning("rate_limit_no_url_configured")
            return None
        try:
            _redis = redis.from_url(_redis_url, decode_responses=True)
            _redis_loop = running
        except Exception as e:
            logger.warning("rate_limit_redis_init_failed", error=str(e))
            _reset_redis()
    return _redis


def _is_stale_loop_error(e: Exception) -> bool:
    msg = str(e)
    return "Event loop is closed" in msg or "different loop" in msg or "attached to a different loop" in msg


async def is_rate_limited(key: str, limit: str, _retried: bool = False) -> tuple[bool, int]:
    """Return (is_limited, retry_after_seconds) using sliding window.

    Fail-closed: if Redis is unavailable or errors, deny request.
    """
    r = _get_redis()
    if r is None:
        logger.warning("rate_limit_redis_unavailable", key=key)
        return True, 60
    try:
        count, window = parse_limit(limit)
    except Exception as e:
        logger.error("rate_limit_bad_limit", key=key, error=str(e))
        return True, 60
    try:
        return await sliding_check(r, f"rl:{key}", count, window)
    except Exception as e:
        if not _retried and _is_stale_loop_error(e):
            _reset_redis()
            return await is_rate_limited(key, limit, _retried=True)
        logger.error("rate_limit_error", key=key, error=str(e))
        return True, 60


async def rate_limit_dependency(request: Request, limit: str):
    user_id = getattr(request.state, "user_id", None)
    org_id = getattr(request.state, "organization_id", None)
    if user_id is not None and org_id is not None:
        key = f"{org_id}:{user_id}:{request.url.path}"
    elif user_id is not None:
        key = f"user:{user_id}:{request.url.path}"
    else:
        client_host = request.client.host if request.client and request.client.host else "unknown"
        key = f"ip:{client_host}:{request.url.path}"
    limited, retry_after = await is_rate_limited(key, limit)
    if limited:
        raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(retry_after)})


def rate_limit(limit: str):
    async def _dep(request: Request):
        await rate_limit_dependency(request, limit)
    return _dep

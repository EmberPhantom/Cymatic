"""Redis sliding-window rate limiter."""
import time
from collections.abc import Awaitable, Callable

import redis.asyncio as redis
from fastapi import HTTPException, Request

from app.core.config import get_settings

settings = get_settings()
_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    global _redis
    if _redis is None:
        try:
            _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            _redis = None
    return _redis


def parse_limit(limit: str) -> tuple[int, int]:
    count, period = limit.split("/")
    period_seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[period.strip()]
    return int(count), period_seconds


async def is_rate_limited(key: str, limit: str) -> tuple[bool, int]:
    """Return (is_limited, retry_after_seconds)."""
    r = _get_redis()
    if r is None:
        return False, 0
    count, window = parse_limit(limit)
    now = int(time.time())
    window_key = f"rl:{key}:{now // window}"
    try:
        current: int = int(await r.incr(window_key))
        if current == 1:
            await r.expire(window_key, window)
        if current > count:
            ttl = await r.ttl(window_key)
            ttl_int = int(ttl) if isinstance(ttl, int) else 1
            return True, max(ttl_int, 1)
    except Exception:
        return False, 0
    return False, 0


async def rate_limit_dependency(request: Request, limit: str) -> None:
    host = request.client.host if request.client else "unknown"
    key = f"{host}:{request.url.path}"
    limited, retry_after = await is_rate_limited(key, limit)
    if limited:
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(retry_after)}
        )


def rate_limit(limit: str) -> Callable[[Request], Awaitable[None]]:
    async def _dep(request: Request) -> None:
        await rate_limit_dependency(request, limit)

    return _dep

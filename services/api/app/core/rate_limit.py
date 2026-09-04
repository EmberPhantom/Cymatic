"""Redis sliding-window rate limiter."""

import time
from typing import Optional
import redis.asyncio as redis
from fastapi import Request, HTTPException
from app.core.config import get_settings

settings = get_settings()
_redis: Optional[redis.Redis] = None


def _get_redis() -> Optional[redis.Redis]:
    global _redis
    if _redis is None:
        try:
            _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
        except Exception:
            _redis = None
    return _redis


def parse_limit(limit: str) -> tuple[int, int]:
    count, period = limit.split("/")
    period_seconds = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}[
        period.strip()
    ]
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
        current = await r.incr(window_key)
        if current == 1:
            await r.expire(window_key, window)
        if current > count:
            ttl = await r.ttl(window_key)
            return True, max(ttl, 1)
    except Exception:
        return False, 0
    return False, 0


async def rate_limit_dependency(request: Request, limit: str):
    key = (
        f"{request.client.host}:{request.url.path}"
        if request.client
        else request.url.path
    )
    limited, retry_after = await is_rate_limited(key, limit)
    if limited:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )


def rate_limit(limit: str):
    async def _dep(request: Request):
        await rate_limit_dependency(request, limit)

    return _dep

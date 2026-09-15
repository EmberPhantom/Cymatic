"""Redis sliding-window rate limiter (fail-closed, parity with API)."""
import asyncio
import time
import uuid
from typing import Optional
import redis.asyncio as redis
import structlog
from fastapi import Request, HTTPException
from app.core.config import get_settings

settings = get_settings()
logger = structlog.get_logger()
_redis: Optional[redis.Redis] = None
_redis_loop: Optional[asyncio.AbstractEventLoop] = None


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
        try:
            redis_url = getattr(settings, "REDIS_RATE_URL", None) or settings.REDIS_URL
            _redis = redis.from_url(redis_url, decode_responses=True)
            _redis_loop = running
        except Exception as e:
            logger.warning("rate_limit_redis_init_failed", error=str(e))
            _reset_redis()
    return _redis


def parse_limit(limit: str) -> tuple[int, int]:
    count, period = limit.split("/")
    p = period.strip().rstrip("s")
    mapping = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
    # Accept both singular and plural ("minute"/"minutes").
    if p + "s" in ("seconds", "minutes", "hours", "days"):
        p = {"seconds": "second", "minutes": "minute", "hours": "hour", "days": "day"}[p + "s"]
    period_seconds = mapping[p]
    return int(count), period_seconds


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
    count, window = parse_limit(limit)
    now = time.time()
    redis_key = f"rl:{key}"
    try:
        async with r.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, now - window)
            pipe.zcard(redis_key)
            pipe.zrange(redis_key, 0, 0, withscores=True)
            pipe.expire(redis_key, window)
            results = await pipe.execute()
        current = int(results[1]) if len(results) > 1 and results[1] is not None else 0
        oldest = results[2] if len(results) > 2 else None
        if current >= count:
            if oldest and len(oldest) > 0:
                try:
                    oldest_score = float(oldest[0][1])
                    retry_after = int(oldest_score + window - now) + 1
                except Exception:
                    retry_after = window
            else:
                retry_after = window
            return True, max(retry_after, 1)
        await r.zadd(redis_key, {str(uuid.uuid4()): now})
        await r.expire(redis_key, window)
        return False, 0
    except Exception as e:
        if not _retried and _is_stale_loop_error(e):
            _reset_redis()
            return await is_rate_limited(key, limit, _retried=True)
        logger.error("rate_limit_error", key=key, error=str(e))
        return True, window


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

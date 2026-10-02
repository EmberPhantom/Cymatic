"""Sliding-window rate-limit primitive. Single source.

Two admission orders exist historically and are BOTH preserved verbatim:
- check-then-add (api/worker): count first, admit when below limit.
- add-then-check (llm-router): admit tentatively, revoke when over limit.
Enforcement outcomes are equivalent (exactly `count` admits per window);
only bookkeeping order differs. Callers keep their own key schemes.
"""

import time
import uuid


async def sliding_check(
    client, redis_key: str, count: int, window: int, *, add_first: bool = False
) -> tuple[bool, int]:
    """Return (is_limited, retry_after_seconds). Fail-closed on Redis error."""
    now = time.time()
    try:
        if add_first:
            member = f"{now}:{uuid.uuid4()}"
            pipe = client.pipeline(transaction=False)
            pipe.zadd(redis_key, {member: now})
            pipe.zremrangebyscore(redis_key, 0, now - window)
            pipe.zcard(redis_key)
            pipe.expire(redis_key, window + 2)
            results = await pipe.execute()
            current = int(results[2]) if len(results) >= 3 else 0
            if current > count:
                return True, await _retry_after(client, redis_key, now, window)
            return False, 0
        async with client.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(redis_key, 0, now - window)
            pipe.zcard(redis_key)
            pipe.zrange(redis_key, 0, 0, withscores=True)
            pipe.expire(redis_key, window)
            results = await pipe.execute()
        current = int(results[1]) if len(results) > 1 and results[1] is not None else 0
        oldest = results[2] if len(results) > 2 else None
        if current >= count:
            return True, _retry_after_from_oldest(oldest, now, window)
        await client.zadd(redis_key, {str(uuid.uuid4()): now})
        await client.expire(redis_key, window)
        return False, 0
    except Exception:
        return True, window


async def _retry_after(client, redis_key: str, now: float, window: int) -> int:
    try:
        oldest = await client.zrange(redis_key, 0, 0, withscores=True)
        if oldest:
            first = oldest[0]
            score = (
                first[1]
                if isinstance(first, (list, tuple)) and len(first) == 2
                else first
            )
            return max(int(float(score) + window - now) + 1, 1)
    except Exception:
        pass
    return max(int(window - (now % window)), 1)


def _retry_after_from_oldest(oldest, now: float, window: int) -> int:
    if oldest and len(oldest) > 0:
        try:
            return max(int(float(oldest[0][1]) + window - now) + 1, 1)
        except Exception:
            return window
    return window


def parse_limit(limit: str) -> tuple[int, int]:
    """Tolerant 'count/period' parser (singular + plural periods)."""
    count, period = limit.split("/", 1)
    period = period.strip().lower()
    mapping = {
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
    }
    if period not in mapping:
        raise ValueError(f"Unknown period: {period}")
    return int(count), mapping[period]

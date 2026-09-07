"""Cache Layer for LLM Router Responses"""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as redis
import structlog
from pydantic import BaseModel

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class CacheEntry(BaseModel):
    key: str
    value: Any
    task_type: str
    model: str
    created_at: str
    hit_count: int = 0


class LLMCache:
    """Redis-based cache for LLM responses with TTL and invalidation."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: redis.Redis | None = None
        self.default_ttl = timedelta(hours=1)
        self._local_cache: dict[str, CacheEntry] = {}  # Hot cache
        self._max_local_size = 1000

    async def connect(self) -> None:
        if not self._client:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )

    async def disconnect(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

    def _make_key(
        self, task_type: str, model: str, prompt: str, params: dict[str, Any] | None = None
    ) -> str:
        """Generate cache key from request."""
        content = f"{task_type}:{model}:{prompt}"
        if params:
            content += f":{json.dumps(params, sort_keys=True)}"
        return f"llm_cache:{hashlib.sha256(content.encode()).hexdigest()[:32]}"

    async def get(
        self, task_type: str, model: str, prompt: str, params: dict[str, Any] | None = None
    ) -> Any | None:
        """Get cached response."""
        key = self._make_key(task_type, model, prompt, params)

        # Check local hot cache first
        if key in self._local_cache:
            entry = self._local_cache[key]
            entry.hit_count += 1
            logger.debug("cache_hit_local", key=key, hits=entry.hit_count)
            return entry.value

        # Check Redis
        await self.connect()
        if self._client is None:
            return None
        try:
            data = await self._client.get(key)
            if data:
                entry = CacheEntry.model_validate_json(data)
                # Promote to local cache
                self._promote_to_local(key, entry)
                logger.debug("cache_hit_redis", key=key)
                return entry.value
        except (redis.RedisError, OSError) as e:
            logger.warning("cache_get_failed", key=key, error=str(e))

        return None

    async def set(
        self,
        task_type: str,
        model: str,
        prompt: str,
        response: Any,
        params: dict[str, Any] | None = None,
        ttl: timedelta | None = None,
    ) -> None:
        """Cache response."""
        key = self._make_key(task_type, model, prompt, params)
        ttl_val = ttl or self.default_ttl

        entry = CacheEntry(
            key=key,
            value=response,
            task_type=task_type,
            model=model,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # Store in Redis
        await self.connect()
        if self._client is None:
            self._promote_to_local(key, entry)
            return
        try:
            await self._client.setex(
                key,
                int(ttl_val.total_seconds()),
                entry.model_dump_json(),
            )
        except (redis.RedisError, OSError) as e:
            logger.warning("cache_set_failed", key=key, error=str(e))

        # Promote to local cache
        self._promote_to_local(key, entry)

    def _promote_to_local(self, key: str, entry: CacheEntry) -> None:
        """Add entry to local hot cache."""
        if len(self._local_cache) >= self._max_local_size:
            # Remove least recently used (simplified: remove oldest)
            oldest_key = min(self._local_cache.keys(), key=lambda k: self._local_cache[k].created_at)
            del self._local_cache[oldest_key]

        self._local_cache[key] = entry

    async def invalidate(self, task_type: str | None = None, model: str | None = None) -> int:
        """Invalidate cache entries by pattern."""
        await self.connect()
        if self._client is None:
            return 0
        pattern = "llm_cache:*"
        if task_type:
            pattern = f"llm_cache:{task_type}:*"
        if model:
            pattern = f"llm_cache:*:{model}:*"

        try:
            keys = await self._client.keys(pattern)
            if keys:
                deleted = await self._client.delete(*keys)
                # Clear from local cache too
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else str(key)
                    self._local_cache.pop(key_str, None)
                logger.info("cache_invalidated", pattern=pattern, count=deleted)
                return int(deleted)
        except (redis.RedisError, OSError) as e:
            logger.warning("cache_invalidate_failed", pattern=pattern, error=str(e))

        return 0

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        await self.connect()

        local_size = len(self._local_cache)
        local_hits = sum(e.hit_count for e in self._local_cache.values())

        try:
            if self._client is None:
                redis_keys: int = 0
            else:
                redis_keys = int(await self._client.dbsize())
        except (redis.RedisError, OSError):
            redis_keys = 0

        return {
            "local_entries": local_size,
            "local_total_hits": local_hits,
            "redis_keys": redis_keys,
        }

    async def warm_cache(self, entries: list[dict[str, Any]]) -> None:
        """Pre-warm cache with common responses."""
        for entry in entries:
            params_val = entry.get("params")
            # mypy: params should be dict[str, Any] | None
            params: dict[str, Any] | None = params_val if isinstance(params_val, dict) else None
            ttl_hours = entry.get("ttl_hours", 1)
            ttl_val: timedelta = timedelta(hours=int(ttl_hours) if isinstance(ttl_hours, (int, float)) else 1)
            await self.set(
                task_type=str(entry["task_type"]),
                model=str(entry["model"]),
                prompt=str(entry["prompt"]),
                response=entry["response"],
                params=params,
                ttl=ttl_val,
            )


# Global cache instance
llm_cache = LLMCache()


async def get_cached_response(
    task_type: str, model: str, prompt: str, params: dict[str, Any] | None = None
) -> Any | None:
    return await llm_cache.get(task_type, model, prompt, params)


async def set_cached_response(
    task_type: str,
    model: str,
    prompt: str,
    response: Any,
    params: dict[str, Any] | None = None,
    ttl: timedelta | None = None,
) -> None:
    await llm_cache.set(task_type, model, prompt, response, params, ttl)


async def invalidate_cache(task_type: str | None = None, model: str | None = None) -> int:
    return await llm_cache.invalidate(task_type, model)

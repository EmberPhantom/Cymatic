"""Cache Layer for LLM Router Responses"""
import json
import hashlib
import asyncio
from datetime import timedelta
from typing import Optional, Any, Dict
from pydantic import BaseModel
import redis.asyncio as redis
import structlog
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
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: Optional[redis.Redis] = None
        self.default_ttl = timedelta(hours=1)
        self._local_cache: Dict[str, CacheEntry] = {}  # Hot cache
        self._max_local_size = 1000
    
    async def connect(self):
        if not self._client:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
    
    async def disconnect(self):
        if self._client:
            await self._client.close()
            self._client = None
    
    def _make_key(self, task_type: str, model: str, prompt: str, params: Dict = None) -> str:
        """Generate cache key from request."""
        content = f"{task_type}:{model}:{prompt}"
        if params:
            content += f":{json.dumps(params, sort_keys=True)}"
        return f"llm_cache:{hashlib.sha256(content.encode()).hexdigest()[:32]}"
    
    async def get(self, task_type: str, model: str, prompt: str, params: Dict = None) -> Optional[Any]:
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
        params: Dict = None,
        ttl: timedelta = None
    ):
        """Cache response."""
        key = self._make_key(task_type, model, prompt, params)
        ttl = ttl or self.default_ttl
        
        entry = CacheEntry(
            key=key,
            value=response,
            task_type=task_type,
            model=model,
            created_at=datetime.utcnow().isoformat(),
        )
        
        # Store in Redis
        await self.connect()
        try:
            await self._client.setex(
                key,
                int(ttl.total_seconds()),
                entry.model_dump_json()
            )
        except (redis.RedisError, OSError) as e:
            logger.warning("cache_set_failed", key=key, error=str(e))
        
        # Promote to local cache
        self._promote_to_local(key, entry)
    
    def _promote_to_local(self, key: str, entry: CacheEntry):
        """Add entry to local hot cache."""
        if len(self._local_cache) >= self._max_local_size:
            # Remove least recently used (simplified: remove oldest)
            oldest_key = min(self._local_cache.keys(), key=lambda k: self._local_cache[k].created_at)
            del self._local_cache[oldest_key]
        
        self._local_cache[key] = entry
    
    async def invalidate(self, task_type: str = None, model: str = None) -> int:
        """Invalidate cache entries by pattern."""
        await self.connect()
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
                    self._local_cache.pop(key, None)
                logger.info("cache_invalidated", pattern=pattern, count=deleted)
                return deleted
        except (redis.RedisError, OSError) as e:
            logger.warning("cache_invalidate_failed", pattern=pattern, error=str(e))
        
        return 0
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        await self.connect()
        
        local_size = len(self._local_cache)
        local_hits = sum(e.hit_count for e in self._local_cache.values())
        
        try:
            # Sample Redis keys
            redis_keys = await self._client.dbsize()
        except (redis.RedisError, OSError):
            redis_keys = 0
        
        return {
            "local_entries": local_size,
            "local_total_hits": local_hits,
            "redis_keys": redis_keys,
        }
    
    async def warm_cache(self, entries: list[Dict[str, Any]]):
        """Pre-warm cache with common responses."""
        for entry in entries:
            await self.set(
                task_type=entry["task_type"],
                model=entry["model"],
                prompt=entry["prompt"],
                response=entry["response"],
                params=entry.get("params"),
                ttl=timedelta(hours=entry.get("ttl_hours", 1))
            )


from datetime import datetime

# Global cache instance
llm_cache = LLMCache()


async def get_cached_response(task_type: str, model: str, prompt: str, params: Dict = None) -> Optional[Any]:
    return await llm_cache.get(task_type, model, prompt, params)


async def set_cached_response(
    task_type: str,
    model: str,
    prompt: str,
    response: Any,
    params: Dict = None,
    ttl: timedelta = None
):
    await llm_cache.set(task_type, model, prompt, response, params, ttl)


async def invalidate_cache(task_type: str = None, model: str = None) -> int:
    return await llm_cache.invalidate(task_type, model)
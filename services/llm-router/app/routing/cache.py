"""Cache Layer for LLM Router Responses"""

import asyncio
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
    expires_at: str | None = None
    hit_count: int = 0


class LLMCache:
    """Redis-based cache for LLM responses with TTL and invalidation."""

    def __init__(self, redis_url: str | None = None) -> None:
        # DB 1 = cache (isolated from rate/quota DBs)
        self.redis_url = (
            redis_url
            or getattr(settings, "REDIS_CACHE_URL", None)
            or settings.REDIS_URL
        )
        self._client: redis.Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self.default_ttl = timedelta(hours=1)
        self._local_cache: dict[str, CacheEntry] = {}  # Hot cache
        self._max_local_size = 1000

    async def connect(self) -> None:
        # redis.asyncio clients bind to the creating loop; recreate when the
        # running loop changed (pytest per-test loops, reloads).
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if (
            self._client is not None
            and running is not None
            and self._loop is not running
        ):
            self._client = None
            self._loop = None
        if not self._client:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            self._loop = running

    async def disconnect(self) -> None:
        if self._client:
            try:
                await self._client.close()
            except Exception:
                pass
            finally:
                self._client = None
                self._loop = None

    def _make_key(
        self,
        task_type: str,
        model: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        sensitivity: str | None = None,
        provider: str | None = None,
        organization_id: str | None = None,
    ) -> str:
        """Generate cache key from request including sensitivity/provider/org for isolation."""
        # Include sensitivity/provider/org to prevent cross-tenant / cross-sensitivity leaks
        content = f"{task_type}:{model}:{prompt}:{sensitivity or ''}:{provider or ''}:{organization_id or ''}"
        if params:
            content += f":{json.dumps(params, sort_keys=True)}"
        digest = hashlib.sha256(content.encode()).hexdigest()[:32]
        # Prefix with task_type and sanitized model for invalidation patterns
        # Sanitize model to avoid colon/slash issues in pattern
        safe_model = model.replace(":", "_").replace("/", "_").replace("*", "_")
        safe_task = task_type.replace(":", "_").replace("/", "_")
        return f"llm_cache:{safe_task}:{safe_model}:{digest}"

    def _is_local_expired(self, entry: CacheEntry) -> bool:
        if not entry.expires_at:
            return False
        try:
            exp = datetime.fromisoformat(entry.expires_at)
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= exp
        except Exception:
            return True

    @staticmethod
    def _has_tenant_scope(organization_id: str | None) -> bool:
        return bool(organization_id and str(organization_id).strip())

    async def get(
        self,
        task_type: str,
        model: str,
        prompt: str,
        params: dict[str, Any] | None = None,
        sensitivity: str | None = None,
        provider: str | None = None,
        organization_id: str | None = None,
    ) -> Any | None:
        """Get cached response."""
        # Without a non-empty organization_id the key cannot isolate tenants,
        # so skip the cache read entirely (fail-closed against cross-tenant
        # collisions) rather than sharing one global entry.
        if not self._has_tenant_scope(organization_id):
            return None
        key = self._make_key(
            task_type, model, prompt, params, sensitivity, provider, organization_id
        )

        # Check local hot cache first
        if key in self._local_cache:
            entry = self._local_cache[key]
            if self._is_local_expired(entry):
                self._local_cache.pop(key, None)
            else:
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
                if self._is_local_expired(entry):
                    # Expired in Redis but still returned? Clean up
                    await self._client.delete(key)
                    return None
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
        sensitivity: str | None = None,
        provider: str | None = None,
        organization_id: str | None = None,
    ) -> None:
        """Cache response."""
        # Do not cache sensitive tenant data with overly broad TTL? Still isolate via key.
        # Skip writes without tenant scope (mirrors get()): unscoped entries
        # would be readable across tenants.
        if not self._has_tenant_scope(organization_id):
            return
        key = self._make_key(
            task_type, model, prompt, params, sensitivity, provider, organization_id
        )
        ttl_val = ttl or self.default_ttl
        now = datetime.now(timezone.utc)
        expires_at = (now + ttl_val).isoformat()

        entry = CacheEntry(
            key=key,
            value=response,
            task_type=task_type,
            model=model,
            created_at=now.isoformat(),
            expires_at=expires_at,
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
        """Add entry to local hot cache with O(1)-ish eviction + TTL-lazy expiry.

        Avoids the old O(n) full scan on every write: expired entries are
        evicted lazily on read (see get()) plus a bounded random-sample
        probe here; capacity is enforced by popping the oldest inserted key
        (dict insertion order), which is O(1).
        """
        import random

        # Refresh insertion order on re-set
        if key in self._local_cache:
            self._local_cache.pop(key, None)
        # Bounded opportunistic expiry probe (max 5 keys, no full scan)
        if len(self._local_cache) >= self._max_local_size:
            try:
                sample_size = min(5, len(self._local_cache))
                for k in random.sample(
                    list(self._local_cache.keys()), sample_size
                ):
                    v = self._local_cache.get(k)
                    if v is not None and self._is_local_expired(v):
                        self._local_cache.pop(k, None)
            except Exception:
                pass
        # Bound writes by popping oldest inserted (insertion order)
        while len(self._local_cache) >= self._max_local_size:
            try:
                oldest = next(iter(self._local_cache))
            except StopIteration:
                break
            self._local_cache.pop(oldest, None)

        self._local_cache[key] = entry

    async def invalidate(
        self, task_type: str | None = None, model: str | None = None
    ) -> int:
        """Invalidate cache entries by pattern using SCAN."""
        await self.connect()
        if self._client is None:
            return 0
        # Build scan pattern based on new key structure llm_cache:task:model:hash
        # Use SCAN not KEYS to avoid blocking Redis
        if task_type and model:
            safe_model = model.replace(":", "_").replace("/", "_").replace("*", "_")
            safe_task = task_type.replace(":", "_").replace("/", "_")
            pattern = f"llm_cache:{safe_task}:{safe_model}:*"
        elif task_type:
            safe_task = task_type.replace(":", "_").replace("/", "_")
            pattern = f"llm_cache:{safe_task}:*:*"
        elif model:
            safe_model = model.replace(":", "_").replace("/", "_").replace("*", "_")
            pattern = f"llm_cache:*:{safe_model}:*"
        else:
            pattern = "llm_cache:*"

        deleted = 0
        try:
            # SCAN iteration
            cursor: int | str = 0
            keys_to_delete: list[str] = []
            while True:
                cursor, keys = await self._client.scan(
                    cursor=cursor, match=pattern, count=200
                )
                if keys:
                    keys_to_delete.extend(
                        [k.decode() if isinstance(k, bytes) else str(k) for k in keys]
                    )
                if cursor == 0 or cursor == "0":
                    break
            if keys_to_delete:
                # Delete in batches to avoid huge delete
                batch_size = 500
                for i in range(0, len(keys_to_delete), batch_size):
                    batch = keys_to_delete[i : i + batch_size]
                    deleted_batch = await self._client.delete(*batch)
                    deleted += int(deleted_batch)
                # Clear from local cache too – need to match pattern locally
                for key in list(self._local_cache.keys()):
                    # Simple prefix match: check if key matches pattern
                    # Convert glob pattern to check
                    if self._matches_pattern(key, pattern):
                        self._local_cache.pop(key, None)
                logger.info("cache_invalidated", pattern=pattern, count=deleted)
                return deleted
            # Also need to handle old hash-only keys (llm_cache:<hash>) for backward compat
            # Scan for those and filter by entry metadata if task/model specified
            if task_type or model:
                # Scan all llm_cache:* and decode to filter
                cursor = 0
                extra_delete: list[str] = []
                while True:
                    cursor, keys = await self._client.scan(
                        cursor=cursor, match="llm_cache:*", count=200
                    )
                    for k in keys:
                        k_str = k.decode() if isinstance(k, bytes) else str(k)
                        if k_str in keys_to_delete:
                            continue
                        # Try to fetch entry metadata to decide
                        try:
                            data = await self._client.get(k_str)
                            if data:
                                ent = CacheEntry.model_validate_json(data)
                                match_task = (
                                    not task_type
                                ) or ent.task_type == task_type
                                match_model = (not model) or ent.model == model
                                if match_task and match_model:
                                    extra_delete.append(k_str)
                        except Exception:
                            continue
                    if cursor == 0 or cursor == "0":
                        break
                if extra_delete:
                    for i in range(0, len(extra_delete), batch_size):
                        batch = extra_delete[i : i + batch_size]
                        deleted_batch = await self._client.delete(*batch)
                        deleted += int(deleted_batch)
                    for k in extra_delete:
                        self._local_cache.pop(k, None)
                    logger.info(
                        "cache_invalidated_extra",
                        pattern=pattern,
                        count=len(extra_delete),
                    )
        except (redis.RedisError, OSError) as e:
            logger.warning("cache_invalidate_failed", pattern=pattern, error=str(e))

        return deleted

    def _matches_pattern(self, key: str, pattern: str) -> bool:
        # Simple glob match for llm_cache patterns with * wildcard
        import re

        regex = "^" + re.escape(pattern).replace("\\*", ".*") + "$"
        return re.match(regex, key) is not None

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics using SCAN instead of DBSIZE."""
        await self.connect()

        local_size = len(self._local_cache)
        # Evict expired from count
        local_hits = sum(
            e.hit_count
            for e in self._local_cache.values()
            if not self._is_local_expired(e)
        )
        # Count non-expired local entries
        local_size = sum(
            1 for e in self._local_cache.values() if not self._is_local_expired(e)
        )

        redis_keys = 0
        try:
            if self._client is not None:
                cursor: int | str = 0
                while True:
                    cursor, keys = await self._client.scan(
                        cursor=cursor, match="llm_cache:*", count=500
                    )
                    redis_keys += len(keys)
                    if cursor == 0 or cursor == "0":
                        break
        except (redis.RedisError, OSError):
            redis_keys = 0

        return {
            "local_entries": local_size,
            "local_total_hits": local_hits,
            "redis_keys": redis_keys,
        }


# Global cache instance
llm_cache = LLMCache()


async def get_cached_response(
    task_type: str,
    model: str,
    prompt: str,
    params: dict[str, Any] | None = None,
    sensitivity: str | None = None,
    provider: str | None = None,
    organization_id: str | None = None,
) -> Any | None:
    return await llm_cache.get(
        task_type, model, prompt, params, sensitivity, provider, organization_id
    )


async def set_cached_response(
    task_type: str,
    model: str,
    prompt: str,
    response: Any,
    params: dict[str, Any] | None = None,
    ttl: timedelta | None = None,
    sensitivity: str | None = None,
    provider: str | None = None,
    organization_id: str | None = None,
) -> None:
    await llm_cache.set(
        task_type,
        model,
        prompt,
        response,
        params,
        ttl,
        sensitivity,
        provider,
        organization_id,
    )


async def invalidate_cache(
    task_type: str | None = None, model: str | None = None
) -> int:
    return await llm_cache.invalidate(task_type, model)

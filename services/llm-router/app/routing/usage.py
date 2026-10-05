"""Usage Tracking and Quota Management with Redis atomic quotas"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import redis.asyncio as redis
import structlog
from pydantic import BaseModel, Field
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


class UsageEventType(str, Enum):
    CHAT_COMPLETION = "chat_completion"
    EMBEDDING = "embedding"
    STT = "stt"
    TTS = "tts"


class UsageLog(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    task_type: str
    provider: str
    model: str
    sensitivity: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: int
    status: str  # success, error, fallback
    error_message: str | None = None
    user_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class QuotaLimit(BaseModel):
    provider: str
    limit_type: str  # rpm, tpm, daily_tokens, monthly_cost
    limit: int
    current: int = 0
    window_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    window_end: datetime | None = None


class ProviderQuota(BaseModel):
    provider: str
    rpm_limit: int = 60
    tpm_limit: int = 100000
    daily_token_limit: int = 1000000
    monthly_cost_limit_usd: float = 100.0
    current_rpm: int = 0
    current_tpm: int = 0
    current_daily_tokens: int = 0
    current_monthly_cost_usd: float = 0.0
    rpm_window_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    tpm_window_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    daily_window_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    monthly_window_start: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class UsageTracker:
    """Tracks LLM usage, enforces quotas via Redis Lua INCR+EXPIRE.

    Falls back to local quotas if Redis unavailable (but check_quota remains fail-closed).
    """

    def __init__(self, redis_url: str | None = None) -> None:
        # DB 2 = usage (isolated from cache/rate)
        self.redis_url = (
            redis_url
            or getattr(settings, "REDIS_USAGE_URL", None)
            or settings.REDIS_URL
        )
        self._client: redis.Redis | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._local_quotas: dict[str, ProviderQuota] = {}
        self._initialize_default_quotas()

    def _initialize_default_quotas(self) -> None:
        """Initialize default quotas per provider from actual ProviderConfig."""
        from app.schemas.providers import ProviderName

        # Use actual ProviderConfig limits rather than hardcoded 60/100k
        try:
            from app.routing.engine import routing_engine

            for provider in ProviderName:
                cfg = routing_engine.providers.get(provider)
                if cfg:
                    self._local_quotas[provider.value] = ProviderQuota(
                        provider=provider.value,
                        rpm_limit=cfg.rate_limit_rpm,
                        tpm_limit=cfg.rate_limit_tpm,
                    )
                else:
                    self._local_quotas[provider.value] = ProviderQuota(
                        provider=provider.value,
                        rpm_limit=60,
                        tpm_limit=100000,
                    )
        except Exception:
            from app.schemas.providers import ProviderName as _PN

            for provider in _PN:
                self._local_quotas[provider.value] = ProviderQuota(
                    provider=provider.value,
                    rpm_limit=60,
                    tpm_limit=100000,
                )

    def _get_provider_limits(self, provider: str) -> ProviderQuota:
        # Return live limits from ProviderConfig if available
        try:
            from app.schemas.providers import ProviderName
            from app.routing.engine import routing_engine

            # Try ProviderName conversion
            try:
                pn = ProviderName(provider)
                cfg = routing_engine.providers.get(pn)
                if cfg:
                    # Keep existing quota object but update limits to live config
                    q = self._local_quotas.get(provider)
                    if q:
                        q.rpm_limit = cfg.rate_limit_rpm
                        q.tpm_limit = cfg.rate_limit_tpm
                        return q
                    return ProviderQuota(
                        provider=provider,
                        rpm_limit=cfg.rate_limit_rpm,
                        tpm_limit=cfg.rate_limit_tpm,
                    )
            except ValueError:
                pass
        except Exception:
            pass
        return self._local_quotas.get(provider, ProviderQuota(provider=provider))

    async def connect(self) -> None:
        # Loop-aware like LLMCache.connect: recreate when running loop changed.
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

    # Lua script for atomic INCR + EXPIRE (SET if new)
    _INCR_EXPIRE_LUA = """
local current = redis.call('INCRBY', KEYS[1], ARGV[1])
if current == tonumber(ARGV[1]) then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return current
"""

    _INCRBYFLOAT_EXPIRE_LUA = """
local current = redis.call('INCRBYFLOAT', KEYS[1], ARGV[1])
if current == tonumber(ARGV[1]) then
  redis.call('EXPIRE', KEYS[1], ARGV[2])
end
return current
"""

    async def _redis_incr(self, key: str, increment: int, ttl: int) -> int:
        if self._client is None:
            await self.connect()
        if self._client is None:
            return 0
        try:
            # Use Lua for atomic INCR+EXPIRE
            result = await self._client.eval(
                self._INCR_EXPIRE_LUA, 1, key, str(increment), str(ttl)
            )
            return int(float(result)) if result is not None else 0
        except (RedisError, OSError, asyncio.TimeoutError):
            # Crash-safe fallback: INCR first, then EXPIRE only when TTL==-1.
            # A crash between the two RTTs leaves a TTL-less key, but the
            # next increment repairs it (TTL==-1 -> EXPIRE), so the key can
            # never stay permanent.
            try:
                val = await self._client.incrby(key, increment)  # type: ignore
                try:
                    ttl_left = await self._client.ttl(key)  # type: ignore
                except (RedisError, OSError, asyncio.TimeoutError):
                    ttl_left = -1
                if ttl_left == -1:
                    try:
                        await self._client.expire(key, ttl)  # type: ignore
                    except (RedisError, OSError, asyncio.TimeoutError) as e:
                        logger.warning(
                            "quota_expire_failed", key=key, error=str(e)
                        )
                return int(val) if val is not None else 0
            except (RedisError, OSError, asyncio.TimeoutError) as e:
                logger.warning("quota_incr_failed", key=key, error=str(e))
                return 0

    async def _redis_incr_float(self, key: str, increment: float, ttl: int) -> float:
        if self._client is None:
            await self.connect()
        if self._client is None:
            return 0.0
        try:
            result = await self._client.eval(
                self._INCRBYFLOAT_EXPIRE_LUA, 1, key, str(increment), str(ttl)
            )
            return float(result) if result is not None else 0.0
        except (RedisError, OSError, asyncio.TimeoutError):
            # Crash-safe fallback (see _redis_incr): repair TTL-less keys.
            try:
                val = await self._client.incrbyfloat(key, increment)  # type: ignore
                try:
                    ttl_left = await self._client.ttl(key)  # type: ignore
                except (RedisError, OSError, asyncio.TimeoutError):
                    ttl_left = -1
                if ttl_left == -1:
                    try:
                        await self._client.expire(key, ttl)  # type: ignore
                    except (RedisError, OSError, asyncio.TimeoutError) as e:
                        logger.warning(
                            "quota_expire_failed", key=key, error=str(e)
                        )
                return float(val) if val is not None else 0.0
            except (RedisError, OSError, asyncio.TimeoutError) as e:
                logger.warning("quota_incr_float_failed", key=key, error=str(e))
                return 0.0

    async def log_usage(self, usage: UsageLog) -> None:
        """Log usage event."""
        await self.connect()
        if self._client is None:
            logger.warning("usage_log_no_redis", usage=usage.model_dump())
            # Still update local quotas as fallback
            await self._update_quota_local(usage)
            return

        # Store in Redis with TTL (30 days)
        key = f"usage:{usage.timestamp.strftime('%Y-%m-%d')}:{usage.request_id}"
        try:
            await self._client.setex(
                key,
                2592000,  # 30 days
                usage.model_dump_json(),
            )
        except Exception as e:
            logger.warning("usage_log_failed", error=str(e))

        # Update daily aggregates
        day_key = f"usage:daily:{usage.timestamp.strftime('%Y-%m-%d')}"
        try:
            pipe = self._client.pipeline(transaction=False)
            pipe.hincrby(day_key, f"{usage.provider}:{usage.task_type}:count", 1)  # type: ignore
            # Fix tpm never trip for STT/TTS: ensure tokens >0 even when zero reported
            tokens_for_quota = usage.total_tokens
            if tokens_for_quota == 0 and usage.task_type in ("stt", "tts"):
                # Estimate: STT 1min audio ~150 tokens, TTS text len/4 tokens
                if usage.task_type == "stt":
                    tokens_for_quota = 150
                else:
                    # Rough: chars/4 tokens
                    tokens_for_quota = (
                        max(10, len(usage.model) * 2) if usage.model else 100
                    )
                    # Prefer metadata text_len if present
                    text_len = usage.metadata.get("text_len") or usage.metadata.get(
                        "chars"
                    )
                    if isinstance(text_len, int):
                        tokens_for_quota = max(10, text_len // 4)
            else:
                tokens_for_quota = (
                    max(tokens_for_quota, 1)
                    if usage.task_type not in ("stt", "tts")
                    else tokens_for_quota
                )
            pipe.hincrby(
                day_key, f"{usage.provider}:{usage.task_type}:tokens", tokens_for_quota
            )  # type: ignore
            pipe.hincrby(day_key, f"{usage.provider}:latency_sum", usage.latency_ms)  # type: ignore
            pipe.expire(day_key, 2592000)  # type: ignore
            await pipe.execute()
        except Exception as e:
            logger.warning("usage_aggregate_failed", error=str(e))

        # Update provider quotas via Redis atomic ops
        await self._update_quota_redis(usage)
        # Also update local for get_quota_status fallback
        await self._update_quota_local(usage)

        # Log to structured logger
        logger.info("llm_usage", **usage.model_dump())

    async def _update_quota_redis(self, usage: UsageLog) -> None:
        """Update provider quota counters in Redis."""
        now = datetime.now(timezone.utc)
        # Keys with window TTLs
        minute_bucket = now.strftime("%Y-%m-%d-%H-%M")
        day_bucket = now.strftime("%Y-%m-%d")
        month_bucket = now.strftime("%Y-%m")
        rpm_key = f"quota:{usage.provider}:rpm:{minute_bucket}"
        tpm_key = f"quota:{usage.provider}:tpm:{minute_bucket}"
        daily_key = f"quota:{usage.provider}:daily:{day_bucket}"
        monthly_cost_key = f"quota:{usage.provider}:monthly_cost:{month_bucket}"

        # Estimate tokens for STT/TTS if zero
        tokens = usage.total_tokens
        if tokens == 0 and usage.task_type in ("stt", "tts"):
            if usage.task_type == "stt":
                tokens = 150
            else:
                text_len = (
                    usage.metadata.get("text_len")
                    if isinstance(usage.metadata.get("text_len"), int)
                    else 100
                )
                tokens = (
                    max(10, int(text_len) // 4) if isinstance(text_len, int) else 100
                )

        cost_per_1k = self._estimate_cost(usage.provider, usage.model)
        cost = (tokens / 1000) * cost_per_1k

        # RPM: increment 1
        await self._redis_incr(rpm_key, 1, 70)
        # TPM: increment tokens
        if tokens > 0:
            await self._redis_incr(tpm_key, tokens, 70)
        # Daily
        if tokens > 0:
            await self._redis_incr(daily_key, tokens, 86400 * 2)
        # Monthly cost
        if cost > 0:
            await self._redis_incr_float(monthly_cost_key, cost, 86400 * 32)

    async def _update_quota_local(self, usage: UsageLog) -> None:
        """Update local quota counters (fallback)."""
        quota = self._local_quotas.get(usage.provider)
        if not quota:
            # Create from live config
            quota = self._get_provider_limits(usage.provider)
            self._local_quotas[usage.provider] = quota

        now = datetime.now(timezone.utc)

        # Reset windows if needed
        if (now - quota.rpm_window_start).total_seconds() >= 60:
            quota.current_rpm = 0
            quota.rpm_window_start = now
        if (now - quota.tpm_window_start).total_seconds() >= 60:
            quota.current_tpm = 0
            quota.tpm_window_start = now
        if (now - quota.daily_window_start).days >= 1:
            quota.current_daily_tokens = 0
            quota.daily_window_start = now
        if (now - quota.monthly_window_start).days >= 30:
            quota.current_monthly_cost_usd = 0.0
            quota.monthly_window_start = now

        # Increment - use estimated tokens for STT/TTS
        tokens = usage.total_tokens
        if tokens == 0 and usage.task_type in ("stt", "tts"):
            tokens = (
                150
                if usage.task_type == "stt"
                else max(10, int(usage.metadata.get("text_len", 100)) // 4)
            )  # type: ignore
        quota.current_rpm += 1
        quota.current_tpm += tokens
        quota.current_daily_tokens += tokens
        cost_per_1k = self._estimate_cost(usage.provider, usage.model)
        quota.current_monthly_cost_usd += (tokens / 1000) * cost_per_1k

    def _estimate_cost(self, provider: str, model: str) -> float:
        """Estimate cost per 1k tokens."""
        costs: dict[str, float] = {
            "groq": 0.0,  # Free tier
            "openrouter": 0.001,
            "nvidia_nim": 0.0,
            "openai": 0.002 if "gpt-4o-mini" in model else 0.01,
            "sarvam": 0.001,
            "apinex": 0.0,  # Free-tier gateway models
            "local": 0.0,  # On-box Ollama inference
        }
        return costs.get(provider, 0.001)

    async def check_quota(self, provider: str, estimated_tokens: int = 1000) -> bool:
        """Check if request would exceed quota (Redis first, fallback local). Returns True if allowed."""
        # Fail-closed for unknown providers: no quota row means no budget was
        # ever approved, so deny rather than allowing unbounded usage.
        try:
            from app.schemas.providers import ProviderName as _ProviderName

            _ProviderName(provider)
        except ValueError:
            logger.warning("quota_unknown_provider", provider=provider)
            return False
        quota_limits = self._get_provider_limits(provider)
        now = datetime.now(timezone.utc)
        minute_bucket = now.strftime("%Y-%m-%d-%H-%M")
        day_bucket = now.strftime("%Y-%m-%d")
        month_bucket = now.strftime("%Y-%m")

        # Fix tpm never trip for STT/TTS: ensure estimated_tokens at least 1 for those tasks
        # Caller should pass proper estimated_tokens; if 0, default to 100
        if estimated_tokens <= 0:
            estimated_tokens = 100

        # Try Redis
        await self.connect()
        if self._client is not None:
            try:
                rpm_key = f"quota:{provider}:rpm:{minute_bucket}"
                tpm_key = f"quota:{provider}:tpm:{minute_bucket}"
                daily_key = f"quota:{provider}:daily:{day_bucket}"
                monthly_cost_key = f"quota:{provider}:monthly_cost:{month_bucket}"

                pipe = self._client.pipeline(transaction=False)
                pipe.get(rpm_key)  # type: ignore
                pipe.get(tpm_key)  # type: ignore
                pipe.get(daily_key)  # type: ignore
                pipe.get(monthly_cost_key)  # type: ignore
                vals = await pipe.execute()
                cur_rpm = int(vals[0]) if vals[0] else 0
                cur_tpm = int(vals[1]) if vals[1] else 0
                cur_daily = int(vals[2]) if vals[2] else 0
                cur_monthly_cost = float(vals[3]) if vals[3] else 0.0

                # Check RPM
                if cur_rpm >= quota_limits.rpm_limit:
                    return False
                # Check TPM
                if cur_tpm + estimated_tokens > quota_limits.tpm_limit:
                    return False
                # Check daily
                if cur_daily + estimated_tokens > quota_limits.daily_token_limit:
                    return False
                # Check monthly cost – this was missing before
                est_cost = (estimated_tokens / 1000) * self._estimate_cost(provider, "")
                if cur_monthly_cost + est_cost > quota_limits.monthly_cost_limit_usd:
                    return False

                return True
            except Exception as e:
                logger.warning(
                    "quota_check_redis_failed", provider=provider, error=str(e)
                )
                # fall through to local

        # Fallback local (also covers no Redis)
        quota = self._local_quotas.get(provider)
        if not quota:
            # Unknown provider with no quota row: deny (fail-closed).
            return False
        # Update limits from live config
        quota = self._get_provider_limits(provider)

        # Check windows similar to original but with monthly_cost
        # RPM
        if (now - quota.rpm_window_start).total_seconds() < 60:
            if quota.current_rpm >= quota.rpm_limit:
                return False
        # TPM
        if (now - quota.tpm_window_start).total_seconds() < 60:
            if quota.current_tpm + estimated_tokens > quota.tpm_limit:
                return False
        # Daily
        if (now - quota.daily_window_start).days < 1:
            if quota.current_daily_tokens + estimated_tokens > quota.daily_token_limit:
                return False
        # Monthly cost
        if (now - quota.monthly_window_start).days < 30:
            est_cost = (estimated_tokens / 1000) * self._estimate_cost(provider, "")
            if quota.current_monthly_cost_usd + est_cost > quota.monthly_cost_limit_usd:
                return False
        return True

    async def get_quota_status(self, provider: str) -> dict[str, Any]:
        """Get current quota status from Redis (preferred) else local."""
        await self.connect()
        quota_limits = self._get_provider_limits(provider)
        now = datetime.now(timezone.utc)
        minute_bucket = now.strftime("%Y-%m-%d-%H-%M")
        day_bucket = now.strftime("%Y-%m-%d")
        month_bucket = now.strftime("%Y-%m")
        if self._client is not None:
            try:
                rpm_key = f"quota:{provider}:rpm:{minute_bucket}"
                tpm_key = f"quota:{provider}:tpm:{minute_bucket}"
                daily_key = f"quota:{provider}:daily:{day_bucket}"
                monthly_cost_key = f"quota:{provider}:monthly_cost:{month_bucket}"
                pipe = self._client.pipeline(transaction=False)
                pipe.get(rpm_key)  # type: ignore
                pipe.get(tpm_key)  # type: ignore
                pipe.get(daily_key)  # type: ignore
                pipe.get(monthly_cost_key)  # type: ignore
                vals = await pipe.execute()
                cur_rpm = int(vals[0]) if vals[0] else 0
                cur_tpm = int(vals[1]) if vals[1] else 0
                cur_daily = int(vals[2]) if vals[2] else 0
                cur_monthly = float(vals[3]) if vals[3] else 0.0
                return {
                    "provider": provider,
                    "rpm": {
                        "used": cur_rpm,
                        "limit": quota_limits.rpm_limit,
                        "remaining": max(0, quota_limits.rpm_limit - cur_rpm),
                    },
                    "tpm": {
                        "used": cur_tpm,
                        "limit": quota_limits.tpm_limit,
                        "remaining": max(0, quota_limits.tpm_limit - cur_tpm),
                    },
                    "daily_tokens": {
                        "used": cur_daily,
                        "limit": quota_limits.daily_token_limit,
                        "remaining": max(0, quota_limits.daily_token_limit - cur_daily),
                    },
                    "monthly_cost_usd": {
                        "used": round(cur_monthly, 4),
                        "limit": quota_limits.monthly_cost_limit_usd,
                        "remaining": round(
                            quota_limits.monthly_cost_limit_usd - cur_monthly, 4
                        ),
                    },
                }
            except Exception:
                pass

        # Fallback to local logic
        quota = self._local_quotas.get(provider)
        if not quota:
            return {}

        # Reset windows if needed
        if (now - quota.rpm_window_start).total_seconds() >= 60:
            quota.current_rpm = 0
        if (now - quota.tpm_window_start).total_seconds() >= 60:
            quota.current_tpm = 0
        if (now - quota.daily_window_start).days >= 1:
            quota.current_daily_tokens = 0
        if (now - quota.monthly_window_start).days >= 30:
            quota.current_monthly_cost_usd = 0.0

        return {
            "provider": quota.provider,
            "rpm": {
                "used": quota.current_rpm,
                "limit": quota.rpm_limit,
                "remaining": max(0, quota.rpm_limit - quota.current_rpm),
            },
            "tpm": {
                "used": quota.current_tpm,
                "limit": quota.tpm_limit,
                "remaining": max(0, quota.tpm_limit - quota.current_tpm),
            },
            "daily_tokens": {
                "used": quota.current_daily_tokens,
                "limit": quota.daily_token_limit,
                "remaining": max(
                    0, quota.daily_token_limit - quota.current_daily_tokens
                ),
            },
            "monthly_cost_usd": {
                "used": round(quota.current_monthly_cost_usd, 4),
                "limit": quota.monthly_cost_limit_usd,
                "remaining": round(
                    quota.monthly_cost_limit_usd - quota.current_monthly_cost_usd, 4
                ),
            },
        }

    async def get_usage_stats(self, days: int = 7) -> dict[str, Any]:
        """Get aggregated usage statistics with days cap (max 30)."""
        # Fix days cap to prevent unbounded Redis load
        MAX_DAYS = 30
        if days > MAX_DAYS:
            days = MAX_DAYS
        if days < 1:
            days = 1
        await self.connect()
        if self._client is None:
            return {
                "by_provider": {},
                "by_task": {},
                "by_model": {},
                "total_requests": 0,
                "total_tokens": 0,
                "avg_latency_ms": 0,
                "error_rate": 0,
            }

        stats: dict[str, Any] = {
            "by_provider": {},
            "by_task": {},
            "by_model": {},
            "total_requests": 0,
            "total_tokens": 0,
            "avg_latency_ms": 0,
            "error_rate": 0,
        }

        latency_sum = 0

        for i in range(days):
            day = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            day_key = f"usage:daily:{day}"
            try:
                data: dict[Any, Any] = await self._client.hgetall(day_key)
            except Exception:
                continue

            for key, value in data.items():
                key_str = key.decode() if isinstance(key, bytes) else str(key)
                val_str = value.decode() if isinstance(value, bytes) else str(value)
                parts = key_str.split(":")
                if len(parts) >= 3:
                    provider = parts[0]
                    task = parts[1]
                    metric = parts[2]

                    by_provider: dict[str, Any] = stats["by_provider"]
                    by_task: dict[str, Any] = stats["by_task"]
                    if metric == "count":
                        by_provider[provider] = by_provider.get(provider, 0) + int(
                            val_str
                        )
                        by_task[task] = by_task.get(task, 0) + int(val_str)
                        stats["total_requests"] = int(stats["total_requests"]) + int(
                            val_str
                        )
                    elif metric == "tokens":
                        by_provider[f"{provider}_tokens"] = by_provider.get(
                            f"{provider}_tokens", 0
                        ) + int(val_str)
                        stats["total_tokens"] = int(stats["total_tokens"]) + int(
                            val_str
                        )
                    elif metric == "latency_sum":
                        latency_sum += int(val_str)

        if int(stats["total_requests"]) > 0:
            stats["avg_latency_ms"] = latency_sum / int(stats["total_requests"])

        # Populate by_model from existing per-call records (bounded scan so
        # the stats endpoint cannot trigger unbounded Redis load).
        try:
            await self._populate_by_model(days, stats)
        except Exception as e:
            logger.debug("usage_by_model_failed", error=str(e))

        return stats

    async def _populate_by_model(self, days: int, stats: dict[str, Any]) -> None:
        """Aggregate per-model counts/tokens from `usage:{date}:{id}` records.

        Reads only existing per-call data (no new writes). Bounded: at most
        200 records per day, 50 keys per SCAN round.
        """
        import json as _json

        if self._client is None:
            return
        by_model: dict[str, Any] = stats.setdefault("by_model", {})
        for i in range(days):
            day = (datetime.now(timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
            pattern = f"usage:{day}:*"
            scanned = 0
            cursor: Any = 0
            try:
                while scanned < 200:
                    cursor, keys = await self._client.scan(
                        cursor=cursor, match=pattern, count=50
                    )
                    if keys:
                        for k in keys:
                            if scanned >= 200:
                                break
                            scanned += 1
                            k_str = (
                                k.decode() if isinstance(k, bytes) else str(k)
                            )
                            try:
                                raw = await self._client.get(k_str)
                            except Exception:
                                continue
                            if not raw:
                                continue
                            raw_str = (
                                raw.decode()
                                if isinstance(raw, bytes)
                                else str(raw)
                            )
                            try:
                                rec = _json.loads(raw_str)
                            except Exception:
                                continue
                            model = str(rec.get("model", "unknown"))
                            tokens = int(rec.get("total_tokens", 0) or 0)
                            entry = by_model.get(model)
                            if not isinstance(entry, dict):
                                entry = {"count": 0, "tokens": 0}
                                by_model[model] = entry
                            entry["count"] = int(entry.get("count", 0)) + 1
                            entry["tokens"] = int(entry.get("tokens", 0)) + tokens
                    if cursor == 0 or cursor == "0":
                        break
            except Exception:
                continue


# Global usage tracker
usage_tracker = UsageTracker()


async def log_llm_usage(
    task_type: str,
    provider: str,
    model: str,
    sensitivity: str,
    prompt_tokens: int,
    completion_tokens: int,
    latency_ms: int,
    status: str,
    error_message: str | None = None,
    user_id: str | None = None,
    organization_id: str | None = None,
    project_id: str | None = None,
) -> None:
    """Convenience function to log LLM usage."""
    usage = UsageLog(
        task_type=task_type,
        provider=provider,
        model=model,
        sensitivity=sensitivity,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
        user_id=user_id,
        organization_id=organization_id,
        project_id=project_id,
    )
    await usage_tracker.log_usage(usage)

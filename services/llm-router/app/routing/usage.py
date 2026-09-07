"""Usage Tracking and Quota Management"""
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

import redis.asyncio as redis
import structlog
from pydantic import BaseModel, Field

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
    rpm_window_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tpm_window_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    daily_window_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    monthly_window_start: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UsageTracker:
    """Tracks LLM usage, enforces quotas, and logs for billing."""

    def __init__(self, redis_url: str | None = None) -> None:
        self.redis_url = redis_url or settings.REDIS_URL
        self._client: redis.Redis | None = None
        self._local_quotas: dict[str, ProviderQuota] = {}
        self._initialize_default_quotas()

    def _initialize_default_quotas(self) -> None:
        """Initialize default quotas per provider."""
        from app.schemas.providers import ProviderName

        for provider in ProviderName:
            self._local_quotas[provider.value] = ProviderQuota(
                provider=provider.value,
                rpm_limit=60,
                tpm_limit=100000,
            )

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

    async def log_usage(self, usage: UsageLog) -> None:
        """Log usage event."""
        await self.connect()
        if self._client is None:
            logger.warning("usage_log_no_redis", usage=usage.model_dump())
            return

        # Store in Redis with TTL (30 days)
        key = f"usage:{usage.timestamp.strftime('%Y-%m-%d')}:{usage.request_id}"
        await self._client.setex(
            key,
            2592000,  # 30 days
            usage.model_dump_json(),
        )

        # Update daily aggregates
        day_key = f"usage:daily:{usage.timestamp.strftime('%Y-%m-%d')}"
        await self._client.hincrby(day_key, f"{usage.provider}:{usage.task_type}:count", 1)
        await self._client.hincrby(
            day_key, f"{usage.provider}:{usage.task_type}:tokens", usage.total_tokens
        )
        await self._client.hincrby(day_key, f"{usage.provider}:latency_sum", usage.latency_ms)

        # Update provider quotas
        await self._update_quota(usage)

        # Log to structured logger
        logger.info("llm_usage", **usage.model_dump())

    async def _update_quota(self, usage: UsageLog) -> None:
        """Update provider quota counters."""
        quota = self._local_quotas.get(usage.provider)
        if not quota:
            return

        now = datetime.now(timezone.utc)

        # Reset RPM window if needed (1 minute)
        if (now - quota.rpm_window_start).total_seconds() >= 60:
            quota.current_rpm = 0
            quota.rpm_window_start = now

        # Reset TPM window if needed (1 minute)
        if (now - quota.tpm_window_start).total_seconds() >= 60:
            quota.current_tpm = 0
            quota.tpm_window_start = now

        # Reset daily window if needed
        if (now - quota.daily_window_start).days >= 1:
            quota.current_daily_tokens = 0
            quota.daily_window_start = now

        # Reset monthly window if needed
        if (now - quota.monthly_window_start).days >= 30:
            quota.current_monthly_cost_usd = 0.0
            quota.monthly_window_start = now

        # Increment counters
        quota.current_rpm += 1
        quota.current_tpm += usage.total_tokens
        quota.current_daily_tokens += usage.total_tokens

        # Estimate cost (rough)
        cost_per_1k = self._estimate_cost(usage.provider, usage.model)
        quota.current_monthly_cost_usd += (usage.total_tokens / 1000) * cost_per_1k

    def _estimate_cost(self, provider: str, model: str) -> float:
        """Estimate cost per 1k tokens."""
        costs: dict[str, float] = {
            "groq": 0.0,  # Free tier
            "openrouter": 0.001,
            "nvidia_nim": 0.0,
            "openai": 0.002 if "gpt-4o-mini" in model else 0.01,
            "sarvam": 0.001,
        }
        return costs.get(provider, 0.001)

    async def check_quota(self, provider: str, estimated_tokens: int = 1000) -> bool:
        """Check if request would exceed quota."""
        quota = self._local_quotas.get(provider)
        if not quota:
            return True

        now = datetime.now(timezone.utc)

        # Check RPM
        if (now - quota.rpm_window_start).total_seconds() < 60:
            if quota.current_rpm >= quota.rpm_limit:
                return False

        # Check TPM
        if (now - quota.tpm_window_start).total_seconds() < 60:
            if quota.current_tpm + estimated_tokens > quota.tpm_limit:
                return False

        # Check daily tokens
        if (now - quota.daily_window_start).days < 1:
            if quota.current_daily_tokens + estimated_tokens > quota.daily_token_limit:
                return False

        return True

    async def get_quota_status(self, provider: str) -> dict[str, Any]:
        """Get current quota status."""
        quota = self._local_quotas.get(provider)
        if not quota:
            return {}

        now = datetime.now(timezone.utc)

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
                "remaining": max(0, quota.daily_token_limit - quota.current_daily_tokens),
            },
            "monthly_cost_usd": {
                "used": round(quota.current_monthly_cost_usd, 4),
                "limit": quota.monthly_cost_limit_usd,
                "remaining": round(quota.monthly_cost_limit_usd - quota.current_monthly_cost_usd, 4),
            },
        }

    async def get_usage_stats(self, days: int = 7) -> dict[str, Any]:
        """Get aggregated usage statistics."""
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
            data: dict[Any, Any] = await self._client.hgetall(day_key)

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
                        by_provider[provider] = by_provider.get(provider, 0) + int(val_str)
                        by_task[task] = by_task.get(task, 0) + int(val_str)
                        stats["total_requests"] = int(stats["total_requests"]) + int(val_str)
                    elif metric == "tokens":
                        by_provider[f"{provider}_tokens"] = by_provider.get(
                            f"{provider}_tokens", 0
                        ) + int(val_str)
                        stats["total_tokens"] = int(stats["total_tokens"]) + int(val_str)
                    elif metric == "latency_sum":
                        latency_sum += int(val_str)

        if int(stats["total_requests"]) > 0:
            stats["avg_latency_ms"] = latency_sum / int(stats["total_requests"])

        return stats


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

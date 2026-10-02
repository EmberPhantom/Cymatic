"""Redis sliding-window rate limiter - re-exported from shared package."""

from cymatic_shared.rate_limit import (  # noqa: F401
    configure_rate_limit,
    is_rate_limited,
    parse_limit,
    rate_limit,
    rate_limit_dependency,
    _get_redis,
    _reset_redis,
)
from app.core.config import get_settings

_settings = get_settings()
configure_rate_limit(getattr(_settings, "REDIS_RATE_URL", None) or _settings.REDIS_URL)

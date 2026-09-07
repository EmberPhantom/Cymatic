"""Circuit Breaker Implementation for LLM Provider Fault Tolerance"""
from datetime import datetime, timezone
from enum import Enum
from threading import Lock
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, PrivateAttr

from app.schemas.providers import ProviderName

logger = structlog.get_logger()


class CircuitState(str, Enum):
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker(BaseModel):
    """Circuit breaker for provider fault tolerance."""

    model_config = ConfigDict(validate_assignment=True)
    provider: ProviderName
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: datetime | None = None
    last_success_time: datetime | None = None

    # Configuration
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout: float = 30.0  # seconds before trying half-open

    # Thread safety
    _lock: Lock = PrivateAttr(default_factory=Lock)

    def record_success(self) -> None:
        """Record successful request."""
        with self._lock:
            self.failure_count = 0
            self.success_count += 1
            self.last_success_time = datetime.now(timezone.utc)

            if self.state == CircuitState.HALF_OPEN and self.success_count >= self.success_threshold:
                self.state = CircuitState.CLOSED
                self.success_count = 0
                logger.info("circuit_breaker_closed", provider=self.provider)

    def record_failure(self) -> None:
        """Record failed request."""
        with self._lock:
            self.failure_count += 1
            self.success_count = 0
            self.last_failure_time = datetime.now(timezone.utc)

            if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning("circuit_breaker_opened", provider=self.provider, failures=self.failure_count)

            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
                logger.warning("circuit_breaker_reopened", provider=self.provider)

    def can_execute(self) -> bool:
        """Check if request can be executed."""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if self.last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                    if elapsed >= self.timeout:
                        self.state = CircuitState.HALF_OPEN
                        self.success_count = 0
                        logger.info("circuit_breaker_half_open", provider=self.provider)
                        return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                return True

            return False

    def get_state(self) -> CircuitState:
        with self._lock:
            return self.state


# Global circuit breaker instances
_circuit_breakers: dict[ProviderName | str, CircuitBreaker] = {}
_lock = Lock()


def _normalize_provider(provider: ProviderName | str) -> ProviderName | str:
    if isinstance(provider, ProviderName):
        return provider
    try:
        return ProviderName(provider)
    except Exception:
        return provider


def get_circuit_breaker(provider: ProviderName | str) -> CircuitBreaker:
    """Get or create circuit breaker for provider."""
    normalized = _normalize_provider(provider)
    # CircuitBreaker provider field expects ProviderName; if normalized is str, cast
    provider_name = normalized if isinstance(normalized, ProviderName) else ProviderName.GROQ
    # Use normalized as dict key (allows str), but create with ProviderName
    with _lock:
        if normalized not in _circuit_breakers:
            _circuit_breakers[normalized] = CircuitBreaker(provider=provider_name)
        return _circuit_breakers[normalized]


def record_provider_success(provider: ProviderName | str) -> None:
    """Record successful request for provider."""
    cb = get_circuit_breaker(provider)
    cb.record_success()


def record_provider_failure(provider: ProviderName | str) -> None:
    """Record failed request for provider."""
    cb = get_circuit_breaker(provider)
    cb.record_failure()


def can_execute_provider(provider: ProviderName | str) -> bool:
    """Check if provider can execute request."""
    cb = get_circuit_breaker(provider)
    return cb.can_execute()


def get_circuit_breaker_status(provider: ProviderName | str) -> dict[str, Any]:
    """Get circuit breaker status for provider."""
    cb = get_circuit_breaker(provider)
    return {
        "state": cb.state.value,
        "failure_count": cb.failure_count,
        "success_count": cb.success_count,
        "last_failure": cb.last_failure_time.isoformat() if cb.last_failure_time else None,
    }


def get_all_circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers."""
    return {p.value: get_circuit_breaker_status(p) for p in ProviderName}

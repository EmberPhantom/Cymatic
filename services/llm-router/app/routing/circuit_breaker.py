"""Circuit Breaker Implementation for LLM Provider Fault Tolerance"""

import asyncio
from datetime import datetime, timezone
from enum import Enum
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
    """Circuit breaker for provider fault tolerance with asyncio primitives."""

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

    # Asyncio safety – single-flight half-open trial via semaphore
    _lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)
    _half_open_sem: asyncio.Semaphore = PrivateAttr(
        default_factory=lambda: asyncio.Semaphore(1)
    )
    _half_open_in_progress: bool = PrivateAttr(default=False)

    def record_success(self) -> None:
        """Sync record successful request (kept for backward compat / tests).

        For async callers use `async_record_success`.
        """
        # No lock in sync path – acceptable for tests, production uses async variant
        self.failure_count = 0
        self.success_count += 1
        self.last_success_time = datetime.now(timezone.utc)

        if (
            self.state == CircuitState.HALF_OPEN
            and self.success_count >= self.success_threshold
        ):
            self.state = CircuitState.CLOSED
            self.success_count = 0
            self._half_open_in_progress = False
            # Release semaphore if held
            if self._half_open_sem.locked():
                try:
                    self._half_open_sem.release()
                except ValueError:
                    pass
            logger.info("circuit_breaker_closed", provider=self.provider)

    def record_failure(self) -> None:
        """Sync record failed request (kept for backward compat)."""
        self.failure_count += 1
        self.success_count = 0
        self.last_failure_time = datetime.now(timezone.utc)

        if (
            self.state == CircuitState.CLOSED
            and self.failure_count >= self.failure_threshold
        ):
            self.state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                provider=self.provider,
                failures=self.failure_count,
            )

        elif self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            self.success_count = 0
            self._half_open_in_progress = False
            if self._half_open_sem.locked():
                try:
                    self._half_open_sem.release()
                except ValueError:
                    pass
            logger.warning("circuit_breaker_reopened", provider=self.provider)

    def can_execute(self) -> bool:
        """Sync check if request can be executed (backward compat)."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if self.last_failure_time:
                elapsed = (
                    datetime.now(timezone.utc) - self.last_failure_time
                ).total_seconds()
                if elapsed >= self.timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    # Single trial guard: if already in progress, deny thundering herd
                    if self._half_open_in_progress:
                        return False
                    if self._half_open_sem.locked():
                        return False
                    self._half_open_in_progress = True
                    # sync can't await acquire, so treat as acquired via flag
                    logger.info("circuit_breaker_half_open", provider=self.provider)
                    return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            if self._half_open_in_progress or self._half_open_sem.locked():
                return False
            return True

        return False

    def get_state(self) -> CircuitState:
        return self.state

    # --- Async variants with proper locking and single-trial semaphore ---

    async def async_record_success(self) -> None:
        async with self._lock:
            self.failure_count = 0
            self.success_count += 1
            self.last_success_time = datetime.now(timezone.utc)

            if (
                self.state == CircuitState.HALF_OPEN
                and self.success_count >= self.success_threshold
            ):
                self.state = CircuitState.CLOSED
                self.success_count = 0
                self._half_open_in_progress = False
                if self._half_open_sem.locked():
                    try:
                        self._half_open_sem.release()
                    except ValueError:
                        pass
                logger.info("circuit_breaker_closed", provider=self.provider)

            # Ensure semaphore released after trial
            if self.state == CircuitState.CLOSED and self._half_open_sem.locked():
                # Might have been held from half-open trial
                try:
                    # Only release if we previously acquired
                    if self._half_open_in_progress:
                        self._half_open_sem.release()
                        self._half_open_in_progress = False
                except ValueError:
                    pass

    async def async_record_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            self.success_count = 0
            self.last_failure_time = datetime.now(timezone.utc)

            if (
                self.state == CircuitState.CLOSED
                and self.failure_count >= self.failure_threshold
            ):
                self.state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_opened",
                    provider=self.provider,
                    failures=self.failure_count,
                )
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
                self._half_open_in_progress = False
                if self._half_open_sem.locked():
                    try:
                        self._half_open_sem.release()
                    except ValueError:
                        pass
                logger.warning("circuit_breaker_reopened", provider=self.provider)

    async def async_can_execute(self) -> bool:
        async with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                if self.last_failure_time:
                    elapsed = (
                        datetime.now(timezone.utc) - self.last_failure_time
                    ).total_seconds()
                    if elapsed >= self.timeout:
                        # Try to acquire single-flight semaphore for half-open trial
                        if self._half_open_sem.locked() or self._half_open_in_progress:
                            return False
                        # Acquire semaphore for this trial
                        await self._half_open_sem.acquire()
                        self._half_open_in_progress = True
                        self.state = CircuitState.HALF_OPEN
                        self.success_count = 0
                        logger.info("circuit_breaker_half_open", provider=self.provider)
                        return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                # Only one trial at a time
                if self._half_open_sem.locked() and self._half_open_in_progress:
                    # Already a trial in progress – deny herd
                    return False
                if self._half_open_sem.locked():
                    return False
                # Acquire for new trial (should not happen normally, as we acquire on transition)
                await self._half_open_sem.acquire()
                self._half_open_in_progress = True
                return True

            return False

    async def async_get_state(self) -> CircuitState:
        async with self._lock:
            return self.state


# Global circuit breaker instances
_circuit_breakers: dict[ProviderName | str, CircuitBreaker] = {}
# Use asyncio lock for async creation path; sync path uses GIL
_async_lock = asyncio.Lock()


def _normalize_provider(provider: ProviderName | str) -> ProviderName | str:
    if isinstance(provider, ProviderName):
        return provider
    try:
        return ProviderName(provider)
    except Exception:
        return provider


def get_circuit_breaker(provider: ProviderName | str) -> CircuitBreaker:
    """Get or create circuit breaker for provider (sync)."""
    normalized = _normalize_provider(provider)
    provider_name = (
        normalized if isinstance(normalized, ProviderName) else ProviderName.GROQ
    )
    # Sync creation – dict access is atomic under GIL, no threading.Lock needed
    if normalized not in _circuit_breakers:
        _circuit_breakers[normalized] = CircuitBreaker(provider=provider_name)
    return _circuit_breakers[normalized]


async def get_circuit_breaker_async(provider: ProviderName | str) -> CircuitBreaker:
    """Async version with lock."""
    normalized = _normalize_provider(provider)
    provider_name = (
        normalized if isinstance(normalized, ProviderName) else ProviderName.GROQ
    )
    async with _async_lock:
        if normalized not in _circuit_breakers:
            _circuit_breakers[normalized] = CircuitBreaker(provider=provider_name)
        return _circuit_breakers[normalized]


def record_provider_success(provider: ProviderName | str) -> None:
    """Record successful request for provider (sync wrapper)."""
    cb = get_circuit_breaker(provider)
    cb.record_success()


def record_provider_failure(provider: ProviderName | str) -> None:
    """Record failed request for provider (sync wrapper)."""
    cb = get_circuit_breaker(provider)
    cb.record_failure()


def can_execute_provider(provider: ProviderName | str) -> bool:
    """Check if provider can execute request (sync)."""
    cb = get_circuit_breaker(provider)
    return cb.can_execute()


async def async_record_provider_success(provider: ProviderName | str) -> None:
    cb = await get_circuit_breaker_async(provider)
    await cb.async_record_success()


async def async_record_provider_failure(provider: ProviderName | str) -> None:
    cb = await get_circuit_breaker_async(provider)
    await cb.async_record_failure()


async def async_can_execute_provider(provider: ProviderName | str) -> bool:
    cb = await get_circuit_breaker_async(provider)
    return await cb.async_can_execute()


def get_circuit_breaker_status(provider: ProviderName | str) -> dict[str, Any]:
    """Get circuit breaker status for provider."""
    cb = get_circuit_breaker(provider)
    return {
        "state": cb.state.value,
        "failure_count": cb.failure_count,
        "success_count": cb.success_count,
        "last_failure": cb.last_failure_time.isoformat()
        if cb.last_failure_time
        else None,
    }


def get_all_circuit_breaker_status() -> dict[str, dict[str, Any]]:
    """Get status of all circuit breakers."""
    return {p.value: get_circuit_breaker_status(p) for p in ProviderName}

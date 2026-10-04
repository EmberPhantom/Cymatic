"""Worker-side LLM-call budget: bounded retries + circuit breaker.

The router client already retries transient errors per request (tenacity, 3
attempts). This module adds the *across-call* guard: when the router (or the
network in front of it) is down, every dequeued job fails fast and would
otherwise hammer the router on each retry cycle. Callers record outcomes on
a process-global-ish :class:`CircuitBreaker`; once consecutive failures hit
the threshold, the caller pauses for a cooldown instead of firing the next
call immediately. :func:`run_with_backoff` is the bounded per-call retry
used by worker LLM wrappers.

All sleeps go through :func:`asyncio.sleep` so tests can patch them; all
durations are constructor/env parameters (no hidden globals).
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable, TypeVar

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitBreaker:
    """Consecutive-failure circuit breaker with a fixed cooldown.

    Closed (normal): calls proceed. After `max_consecutive_failures`
    failures in a row the breaker opens; :meth:`wait_if_open` then sleeps
    `cooldown_seconds` once and half-opens (next call probes). Any success
    closes it and resets the counter.
    """

    def __init__(
        self,
        max_consecutive_failures: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        if max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be >= 1")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")
        self.max_consecutive_failures = max_consecutive_failures
        self.cooldown_seconds = cooldown_seconds
        self.consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        if (time.monotonic() - self._opened_at) >= self.cooldown_seconds:
            # Cooldown elapsed: half-open (allow one probe call).
            self._opened_at = None
            self.consecutive_failures = 0
            return False
        return True

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self._opened_at = None

    def record_failure(self) -> bool:
        """Record a failure; True when the breaker just opened (caller pauses)."""
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.max_consecutive_failures:
            if self._opened_at is None:
                self._opened_at = time.monotonic()
                logger.warning(
                    "llm_breaker_opened",
                    consecutive_failures=self.consecutive_failures,
                    cooldown_s=self.cooldown_seconds,
                )
            return True
        return False

    async def wait_if_open(self) -> None:
        """Sleep out the cooldown when open; no-op when closed/half-open."""
        if self.is_open:
            logger.warning(
                "llm_breaker_cooling_down",
                cooldown_s=self.cooldown_seconds,
                consecutive_failures=self.consecutive_failures,
            )
            await asyncio.sleep(self.cooldown_seconds)
            # Half-open after the pause: the next call probes.
            self._opened_at = None
            self.consecutive_failures = 0


async def run_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Call `fn` with bounded retries and exponential backoff.

    Total attempts = 1 + max_retries. Delay before retry N (1-based) is
    `min(base_delay * 2**(N-1), max_delay)`. Non-retryable exceptions and
    :class:`asyncio.CancelledError` propagate immediately (cancellation must
    never be swallowed by a retry loop).
    """
    if max_retries < 0:
        raise ValueError("max_retries must be >= 0")
    attempt = 0
    while True:
        try:
            return await fn()
        except asyncio.CancelledError:
            raise
        except retryable as exc:
            if attempt >= max_retries:
                raise
            attempt += 1
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            logger.warning(
                "llm_backoff_retry",
                attempt=attempt,
                max_retries=max_retries,
                delay_s=delay,
                error=str(exc)[:200],
            )
            await asyncio.sleep(delay)


async def call_with_budget(
    fn: Callable[[], Awaitable[T]],
    breaker: CircuitBreaker,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    """Budget-guarded call: cooldown-pause, then bounded retries.

    Records the aggregate outcome on `breaker` exactly once (success closes,
    terminal failure counts once no matter how many inner retries fired).
    """
    await breaker.wait_if_open()
    try:
        result: Any = await run_with_backoff(
            fn,
            max_retries=max_retries,
            base_delay=base_delay,
            max_delay=max_delay,
            retryable=retryable,
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        breaker.record_failure()
        raise
    breaker.record_success()
    return result

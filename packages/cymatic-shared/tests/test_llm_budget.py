"""Phase C-Worker item 4 (shared half): LLM-call budget primitives.

CircuitBreaker: consecutive-failure counting, open/half-open/closed
transitions, cooldown pause. run_with_backoff / call_with_budget: bounded
retries with exponential backoff, no retry on cancellation.
"""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from cymatic_shared.agents.llm_budget import (
    CircuitBreaker,
    call_with_budget,
    run_with_backoff,
)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


def test_breaker_closed_initially():
    b = CircuitBreaker(max_consecutive_failures=3, cooldown_seconds=30.0)
    assert not b.is_open
    assert b.consecutive_failures == 0


def test_breaker_opens_after_threshold():
    b = CircuitBreaker(max_consecutive_failures=3, cooldown_seconds=30.0)
    assert b.record_failure() is False
    assert b.record_failure() is False
    assert b.record_failure() is True
    assert b.is_open


def test_breaker_success_resets_counter():
    b = CircuitBreaker(max_consecutive_failures=3, cooldown_seconds=30.0)
    b.record_failure()
    b.record_failure()
    b.record_success()
    assert b.consecutive_failures == 0
    assert b.record_failure() is False  # needs 3 fresh failures again
    assert not b.is_open


def test_breaker_half_opens_after_cooldown():
    b = CircuitBreaker(max_consecutive_failures=1, cooldown_seconds=30.0)
    assert b.record_failure() is True
    assert b.is_open
    # Simulate cooldown elapsed without real sleeping.
    b._opened_at = time.monotonic() - 31.0
    assert not b.is_open
    assert b.consecutive_failures == 0


async def test_breaker_wait_if_open_sleeps_cooldown():
    b = CircuitBreaker(max_consecutive_failures=1, cooldown_seconds=30.0)
    b.record_failure()
    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        await b.wait_if_open()
    asleep.assert_awaited_once_with(30.0)
    # After the pause the breaker half-opens (next call probes).
    assert not b.is_open


async def test_breaker_wait_if_open_noop_when_closed():
    b = CircuitBreaker(max_consecutive_failures=2, cooldown_seconds=30.0)
    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        await b.wait_if_open()
    asleep.assert_not_awaited()


def test_breaker_rejects_bad_config():
    with pytest.raises(ValueError):
        CircuitBreaker(max_consecutive_failures=0)
    with pytest.raises(ValueError):
        CircuitBreaker(cooldown_seconds=-1.0)


# ---------------------------------------------------------------------------
# run_with_backoff
# ---------------------------------------------------------------------------


async def test_backoff_success_first_try_no_sleep():
    calls = {"n": 0}

    async def _ok():
        calls["n"] += 1
        return {"ok": True}

    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        assert await run_with_backoff(_ok, max_retries=3) == {"ok": True}
    assert calls["n"] == 1
    asleep.assert_not_awaited()


async def test_backoff_retries_then_succeeds_with_exponential_delays():
    calls = {"n": 0}

    async def _flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("router down")
        return "recovered"

    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        result = await run_with_backoff(_flaky, max_retries=3, base_delay=1.0)
    assert result == "recovered"
    assert calls["n"] == 3
    assert [c.args[0] for c in asleep.await_args_list] == [1.0, 2.0]


async def test_backoff_delay_capped_by_max_delay():
    async def _always_fail():
        raise RuntimeError("down")

    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        with pytest.raises(RuntimeError):
            await run_with_backoff(
                _always_fail, max_retries=3, base_delay=10.0, max_delay=15.0
            )
    assert [c.args[0] for c in asleep.await_args_list] == [10.0, 15.0, 15.0]


async def test_backoff_gives_up_after_max_retries():
    calls = {"n": 0}

    async def _always_fail():
        calls["n"] += 1
        raise ConnectionError("no route")

    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(ConnectionError):
            await run_with_backoff(_always_fail, max_retries=2)
    # 1 initial attempt + 2 retries
    assert calls["n"] == 3


async def test_backoff_does_not_swallow_cancellation():
    async def _cancelled():
        raise asyncio.CancelledError()

    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        with pytest.raises(asyncio.CancelledError):
            await run_with_backoff(_cancelled, max_retries=3)
    asleep.assert_not_awaited()


async def test_backoff_non_retryable_propagates_immediately():
    calls = {"n": 0}

    async def _bad():
        calls["n"] += 1
        raise ValueError("not retryable")

    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        with pytest.raises(ValueError):
            await run_with_backoff(_bad, max_retries=3, retryable=(RuntimeError,))
    assert calls["n"] == 1
    asleep.assert_not_awaited()


async def test_backoff_rejects_negative_retries():
    async def _noop():
        return None

    with pytest.raises(ValueError):
        await run_with_backoff(_noop, max_retries=-1)


# ---------------------------------------------------------------------------
# call_with_budget
# ---------------------------------------------------------------------------


async def test_call_with_budget_success_closes_breaker():
    b = CircuitBreaker(max_consecutive_failures=2, cooldown_seconds=5.0)
    b.record_failure()

    async def _ok():
        return 42

    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        assert await call_with_budget(_ok, b, max_retries=2) == 42
    asleep.assert_not_awaited()
    assert b.consecutive_failures == 0
    assert not b.is_open


async def test_call_with_budget_terminal_failure_counts_once():
    b = CircuitBreaker(max_consecutive_failures=5, cooldown_seconds=5.0)

    async def _always_fail():
        raise RuntimeError("router 503")

    with patch("asyncio.sleep", new=AsyncMock()):
        with pytest.raises(RuntimeError):
            await call_with_budget(_always_fail, b, max_retries=3, base_delay=0.01)
    # One aggregate failure despite 4 inner attempts.
    assert b.consecutive_failures == 1


async def test_call_with_budget_pauses_when_breaker_open():
    b = CircuitBreaker(max_consecutive_failures=1, cooldown_seconds=12.0)
    b.record_failure()
    assert b.is_open

    async def _ok():
        return "probed"

    with patch("asyncio.sleep", new=AsyncMock()) as asleep:
        assert await call_with_budget(_ok, b) == "probed"
    asleep.assert_awaited_once_with(12.0)
    assert b.consecutive_failures == 0

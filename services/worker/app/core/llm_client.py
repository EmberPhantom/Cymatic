"""LLM Router Client - re-export from shared package + worker budget guard.

The plain `call_llm_json` re-export is the per-request path (tenacity retries
live in the shared client). `call_llm_json_with_budget` is the worker-side
guard: bounded retries with exponential backoff around the router call plus
a process-global consecutive-failure circuit breaker, so a downed router
(or a Redis blip upstream of it) pauses the worker instead of turning every
dequeue cycle into a router-hammering loop. Worker-owned agent paths (e.g.
the cloud architect call) should prefer the budgeted variant.
"""

from typing import Any, Dict, List, Optional

from cymatic_shared.agents.llm_budget import CircuitBreaker, call_with_budget
from cymatic_shared.agents.llm_client import (
    LLMRouterClient,
    llm_router_client,
    call_llm,
    call_llm_json,
    call_llm_structured,
)

__all__ = [
    "LLMRouterClient",
    "llm_router_client",
    "call_llm",
    "call_llm_json",
    "call_llm_structured",
    "call_llm_json_with_budget",
    "get_worker_llm_breaker",
    "reset_worker_llm_breaker",
]

_worker_llm_breaker: CircuitBreaker | None = None


def _budget_settings() -> tuple[int, float, int, float]:
    """(max_retries, backoff_base_s, max_consecutive_failures, cooldown_s)."""
    try:
        from app.core.config import get_settings

        settings = get_settings()
        return (
            int(getattr(settings, "LLM_BUDGET_MAX_RETRIES", 3)),
            float(getattr(settings, "LLM_BUDGET_BACKOFF_BASE_S", 1.0)),
            int(getattr(settings, "LLM_BUDGET_MAX_CONSECUTIVE_FAILURES", 5)),
            float(getattr(settings, "LLM_BUDGET_COOLDOWN_S", 30.0)),
        )
    except Exception:
        return (3, 1.0, 5, 30.0)


def get_worker_llm_breaker() -> CircuitBreaker:
    """Process-global breaker for worker LLM calls (lazy, settings-driven)."""
    global _worker_llm_breaker
    if _worker_llm_breaker is None:
        _, _, max_failures, cooldown = _budget_settings()
        _worker_llm_breaker = CircuitBreaker(
            max_consecutive_failures=max_failures,
            cooldown_seconds=cooldown,
        )
    return _worker_llm_breaker


def reset_worker_llm_breaker() -> None:
    """Drop the cached breaker (tests / settings change)."""
    global _worker_llm_breaker
    _worker_llm_breaker = None


async def call_llm_json_with_budget(
    messages: List[Dict[str, str]],
    task_type: str = "copilot_chat",
    sensitivity: str = "internal",
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    use_cache: bool = True,
    required_non_empty_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Budget-guarded `call_llm_json`: cooldown-pause + bounded retries.

    Same contract as the shared `call_llm_json` (returns {} when the LLM
    output is unrecoverable — callers MUST treat {} as failure and fall
    back). The shared client is imported lazily at call time so test patches
    on `cymatic_shared.agents.llm_client.call_llm_json` keep applying.
    """
    from cymatic_shared.agents import llm_client as shared_llm_client

    max_retries, backoff_base, _, _ = _budget_settings()
    breaker = get_worker_llm_breaker()

    async def _call() -> Dict[str, Any]:
        return await shared_llm_client.call_llm_json(
            messages=messages,
            task_type=task_type,
            sensitivity=sensitivity,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            timeout=timeout,
            use_cache=use_cache,
            required_non_empty_keys=required_non_empty_keys,
        )

    return await call_with_budget(
        _call,
        breaker,
        max_retries=max_retries,
        base_delay=backoff_base,
    )

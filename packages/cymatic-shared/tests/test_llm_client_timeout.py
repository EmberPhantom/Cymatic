"""Phase C-Worker item 2: LLM_TIMEOUT wiring in the shared router client.

The client default must come from settings LLM_TIMEOUT (worker config),
falling back to 60.0s when no settings object provides it. Explicit
constructor timeouts and per-request overrides keep precedence.
"""

from types import SimpleNamespace

import pytest

from cymatic_shared.agents import llm_client as lc


@pytest.fixture
def _fake_settings():
    """Inject a stub settings object; restore the cache afterwards."""
    previous = lc._settings
    lc._settings = SimpleNamespace(
        LLM_ROUTER_URL="http://test-router:8001",
        ADMIN_API_KEY="",
        LLM_TIMEOUT=7.5,
    )
    try:
        yield lc._settings
    finally:
        lc._settings = previous


async def test_default_timeout_comes_from_settings(_fake_settings):
    assert lc._default_llm_timeout() == 7.5
    client = lc.LLMRouterClient()
    try:
        assert float(client.client.timeout.connect) == 7.5
    finally:
        await client.close()


async def test_explicit_constructor_timeout_wins(_fake_settings):
    client = lc.LLMRouterClient(timeout=3.0)
    try:
        assert float(client.client.timeout.connect) == 3.0
    finally:
        await client.close()


async def test_missing_setting_falls_back_to_60():
    previous = lc._settings
    lc._settings = SimpleNamespace(
        LLM_ROUTER_URL="http://test-router:8001", ADMIN_API_KEY=""
    )
    try:
        assert lc._default_llm_timeout() == 60.0
        client = lc.LLMRouterClient()
        try:
            assert float(client.client.timeout.connect) == 60.0
        finally:
            await client.close()
    finally:
        lc._settings = previous


async def test_invalid_setting_falls_back_to_60():
    previous = lc._settings
    lc._settings = SimpleNamespace(
        LLM_ROUTER_URL="http://test-router:8001",
        ADMIN_API_KEY="",
        LLM_TIMEOUT="not-a-number",
    )
    try:
        assert lc._default_llm_timeout() == 60.0
    finally:
        lc._settings = previous


async def test_settings_env_override_roundtrip(monkeypatch):
    """LLM_TIMEOUT set on the settings object changes the client default."""
    previous = lc._settings
    lc._settings = SimpleNamespace(
        LLM_ROUTER_URL="http://test-router:8001",
        ADMIN_API_KEY="",
        LLM_TIMEOUT=120.0,
    )
    try:
        client = lc.LLMRouterClient()
        try:
            # intake-style 120s override documented as a per-agent value
            assert float(client.client.timeout.connect) == 120.0
        finally:
            await client.close()
    finally:
        lc._settings = previous


def test_reset_settings_clears_cache():
    lc._settings = SimpleNamespace(LLM_ROUTER_URL="http://x", ADMIN_API_KEY="")
    lc._reset_settings()
    assert lc._settings is None

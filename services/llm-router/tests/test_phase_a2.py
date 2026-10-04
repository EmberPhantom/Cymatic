"""Phase A2 (LLM-router security P0s) regression tests."""

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException, Request
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.main import app
from app.schemas.providers import ProviderName, SensitivityLevel, TaskType

settings = get_settings()
settings.ADMIN_API_KEY = "test-admin-key"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _tiny_wav_b64() -> str:
    return base64.b64encode(b"RIFF....fake-wav-bytes").decode()


# --- 1. STT/TTS sensitivity bypass -------------------------------------------


@pytest.mark.asyncio
async def test_stt_regulated_denied_and_not_sent():
    from app.providers.litellm_client import LiteLLMClient, STTRequest

    c = LiteLLMClient()
    req = STTRequest(audio_data=_tiny_wav_b64(), sensitivity=SensitivityLevel.REGULATED)
    with patch(
        "litellm.atranscription", new_callable=AsyncMock
    ) as mock_transcribe:
        with pytest.raises(ValueError, match="support|blocked|allowed|provider"):
            await c.stt(req)
        mock_transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_tts_regulated_denied_and_not_sent():
    from app.providers.litellm_client import LiteLLMClient, TTSRequest

    c = LiteLLMClient()
    req = TTSRequest(text="hello", sensitivity=SensitivityLevel.REGULATED)
    with patch("litellm.aspeech", new_callable=AsyncMock) as mock_speech:
        with pytest.raises(ValueError, match="support|blocked|allowed|provider"):
            await c.tts(req)
        mock_speech.assert_not_called()


@pytest.mark.asyncio
async def test_stt_explicit_model_allowlisted():
    from app.providers.litellm_client import LiteLLMClient, STTRequest

    c = LiteLLMClient()
    req = STTRequest(audio_data=_tiny_wav_b64(), model="nonexistent-model-xyz")
    with patch(
        "litellm.atranscription", new_callable=AsyncMock
    ) as mock_transcribe:
        with pytest.raises(ValueError, match="not found"):
            await c.stt(req)
        mock_transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_tts_explicit_model_allowlisted():
    from app.providers.litellm_client import LiteLLMClient, TTSRequest

    c = LiteLLMClient()
    req = TTSRequest(text="hello", model="nonexistent-model-xyz")
    with patch("litellm.aspeech", new_callable=AsyncMock) as mock_speech:
        with pytest.raises(ValueError, match="not found"):
            await c.tts(req)
        mock_speech.assert_not_called()


@pytest.mark.asyncio
async def test_stt_internal_still_routes_to_sarvam(monkeypatch):
    import os

    from app.providers.litellm_client import LiteLLMClient, STTRequest
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam-key-12345678")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        c = LiteLLMClient()
        c.usage_tracker.check_quota = AsyncMock(return_value=True)  # type: ignore
        fake_resp = MagicMock()
        fake_resp.text = "hello world"
        with (
            patch("app.providers.litellm_client.routing_engine", engine),
            patch(
                "app.providers.litellm_client.log_llm_usage",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "litellm.atranscription", new_callable=AsyncMock
            ) as mock_transcribe,
        ):
            mock_transcribe.return_value = fake_resp
            resp = await c.stt(STTRequest(audio_data=_tiny_wav_b64()))
            assert resp.provider == "sarvam"
            assert resp.model == "saarika:v2"
            mock_transcribe.assert_called_once()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        os.environ.pop("SARVAM_API_KEY", None)


# --- 2. Quota fail-open --------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_quota_check_failure_denies():
    from app.providers.litellm_client import ChatCompletionRequest, LiteLLMClient

    c = LiteLLMClient()
    c.usage_tracker.check_quota = AsyncMock(  # type: ignore
        side_effect=RuntimeError("redis down")
    )
    fake_engine = MagicMock()
    fake_engine.route.return_value = MagicMock(
        provider=ProviderName.GROQ,
        model="openai/gpt-oss-20b",
        fallback=None,
    )
    fake_engine.get_policy.return_value = MagicMock(max_retries=0)
    with patch("app.providers.litellm_client.routing_engine", fake_engine):
        with pytest.raises(HTTPException) as exc:
            await c.chat_completion(
                ChatCompletionRequest(
                    messages=[{"role": "user", "content": "hi"}],
                    use_cache=False,
                )
            )
    assert exc.value.status_code == 429


# --- 3. Cache cross-tenant collision -------------------------------------------


@pytest.mark.asyncio
async def test_cache_requires_org_scope():
    from app.routing.cache import LLMCache

    cache = LLMCache(redis_url="redis://localhost:6379/0")
    # Writes without org are skipped
    await cache.set("copilot_chat", "m", "same prompt", {"ok": 1})
    await cache.set("copilot_chat", "m", "same prompt", {"ok": 1}, organization_id="  ")
    assert len(cache._local_cache) == 0

    # Scoped write is isolated per org; other/missing orgs never hit it
    await cache.set(
        "copilot_chat", "m", "same prompt", {"ok": 1}, organization_id="org-a"
    )
    assert await cache.get("copilot_chat", "m", "same prompt", organization_id="org-a") == {
        "ok": 1
    }
    assert (
        await cache.get("copilot_chat", "m", "same prompt", organization_id="org-b")
        is None
    )
    assert await cache.get("copilot_chat", "m", "same prompt") is None
    assert (
        await cache.get("copilot_chat", "m", "same prompt", organization_id="")
        is None
    )


# --- 4. Split data-plane / admin-plane keys ------------------------------------


@pytest.mark.asyncio
async def test_data_plane_key_split(client):
    old_admin, old_data = settings.ADMIN_API_KEY, settings.LLM_API_KEY
    settings.ADMIN_API_KEY = "admin-key-123"
    settings.LLM_API_KEY = "data-key-123"
    try:
        with patch(
            "app.core.rate_limit.is_rate_limited",
            new=AsyncMock(return_value=(False, 0)),
        ):
            # Data key works on data-plane routes
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
                headers={"X-Api-Key": "data-key-123"},
            )
            assert resp.status_code != 401
            # Planes are split: admin key does NOT open data-plane routes
            # once LLM_API_KEY is set
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
                headers={"X-Api-Key": "admin-key-123"},
            )
            assert resp.status_code == 401
            # Data key must NOT open admin-plane routes
            resp = await client.get(
                "/v1/router/providers", headers={"X-Api-Key": "data-key-123"}
            )
            assert resp.status_code == 401
            # Admin key still opens admin-plane routes
            resp = await client.get(
                "/v1/router/providers", headers={"X-Api-Key": "admin-key-123"}
            )
            assert resp.status_code == 200
            # Wrong key rejected everywhere
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
                headers={"X-Api-Key": "wrong-key"},
            )
            assert resp.status_code == 401

        # Back-compat fallback: with LLM_API_KEY unset, the admin key opens
        # data-plane routes (a warning is logged).
        settings.LLM_API_KEY = ""
        with patch(
            "app.core.rate_limit.is_rate_limited",
            new=AsyncMock(return_value=(False, 0)),
        ):
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
                headers={"X-Api-Key": "admin-key-123"},
            )
            assert resp.status_code != 401
    finally:
        settings.ADMIN_API_KEY = old_admin
        settings.LLM_API_KEY = old_data


# --- 5. Unknown-provider quota + cost entries ----------------------------------


@pytest.mark.asyncio
async def test_unknown_provider_quota_denied():
    from app.routing.usage import UsageTracker

    tracker = UsageTracker(redis_url="redis://localhost:6379/0")
    assert await tracker.check_quota("definitely_unknown_provider_xyz", 100) is False
    assert await tracker.check_quota("", 100) is False


def test_cost_entries_cover_apinex_and_local():
    from app.routing.usage import UsageTracker

    tracker = UsageTracker(redis_url="redis://localhost:6379/0")
    assert tracker._estimate_cost("apinex", "free/glm-5.3-flash") == 0.0
    assert tracker._estimate_cost("local", "phi-3-mini-3.8b-q4") == 0.0


# --- 6. Spoofable rate-limit identity ------------------------------------------


def _spoofed_request(authenticated: bool) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/chat/completions",
        "headers": [
            (b"x-organization-id", b"spoofed-org"),
            (b"x-user-id", b"spoofed-user"),
            (b"x-forwarded-for", b"9.9.9.9"),
        ],
        "client": ("10.0.0.5", 1234),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    }
    req = Request(scope)  # type: ignore[arg-type]
    if authenticated:
        req.state.authenticated = True
    return req


def test_rate_limit_ignores_spoofed_headers_when_authenticated():
    from app.core.rate_limit import _resolve_identifier

    ident = _resolve_identifier(_spoofed_request(authenticated=True))
    assert ident == "ip:10.0.0.5"
    assert "spoofed" not in ident
    assert "9.9.9.9" not in ident


def test_rate_limit_prefers_state_org_over_spoofed_headers():
    from app.core.rate_limit import _resolve_identifier

    req = _spoofed_request(authenticated=True)
    req.state.organization_id = "real-org"
    assert _resolve_identifier(req) == "org:real-org"


# --- 7. /health disclosure -------------------------------------------------------


@pytest.mark.asyncio
async def test_health_public_has_no_key_detail(client):
    body = (await client.get("/health")).json()
    assert body["status"] == "healthy"
    assert "cloud_keys_configured" not in body
    assert "providers" not in body
    # A wrong key must not unlock the detail either
    body = (await client.get("/health", headers={"X-Api-Key": "wrong"})).json()
    assert "cloud_keys_configured" not in body
    assert "providers" not in body


@pytest.mark.asyncio
async def test_chat_task_types_stt_tts_route():
    """Sanity: engine exposes STT/TTS routes for non-regulated levels."""
    from app.routing.engine import RoutingEngine

    engine = RoutingEngine()
    for task in (TaskType.STT, TaskType.TTS):
        policy = engine.get_policy(task, SensitivityLevel.INTERNAL)
        assert policy.allowed_providers == [ProviderName.SARVAM]

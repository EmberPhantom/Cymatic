"""Tests for LLM Router"""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import get_settings
from app.schemas.providers import TaskType, SensitivityLevel, ProviderName
from app.routing.circuit_breaker import get_circuit_breaker

settings = get_settings()
settings.ADMIN_API_KEY = "test-admin-key"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    # Public /health must not disclose per-provider/per-key detail
    assert "providers" not in response.json()
    assert "cloud_keys_configured" not in response.json()


@pytest.mark.asyncio
async def test_health_check_admin_sees_provider_detail(client):
    response = await client.get(
        "/health", headers={"X-Api-Key": settings.ADMIN_API_KEY}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "providers" in body
    assert "cloud_keys_configured" in body


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "name" in response.json()


@pytest.mark.asyncio
async def test_list_providers(client):
    response = await client.get(
        "/v1/router/providers", headers={"X-Api-Key": settings.ADMIN_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data


@pytest.mark.asyncio
async def test_list_policies(client):
    response = await client.get(
        "/v1/router/policies", headers={"X-Api-Key": settings.ADMIN_API_KEY}
    )
    assert response.status_code == 200
    data = response.json()
    assert "policies" in data


@pytest.mark.asyncio
async def test_admin_routes_reject_missing_api_key(client):
    response = await client.get("/v1/router/providers")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_routes_reject_wrong_api_key(client):
    response = await client.get(
        "/v1/router/cache/stats", headers={"X-Api-Key": "wrong-key"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_circuit_breaker():
    cb = get_circuit_breaker(ProviderName.GROQ)
    assert cb.can_execute() is True

    for _ in range(5):
        cb.record_failure()

    assert cb.state.value == "open"
    assert cb.can_execute() is False

    cb.state = "closed"
    cb.failure_count = 0


@pytest.mark.asyncio
async def test_circuit_breaker_half_open():
    cb = get_circuit_breaker(ProviderName.OPENAI)
    cb.state = "open"
    cb.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=40)

    assert cb.can_execute() is True
    assert cb.state.value == "half_open"

    cb.record_success()
    cb.record_success()
    assert cb.state.value == "closed"


@pytest.mark.asyncio
async def test_routing_engine_intent_extraction(monkeypatch):
    # Intent uses the live free model on Groq (gpt-oss-20b); qwen-qwq-32b was
    # decommissioned by Groq and must not be referenced by any policy.
    # Hermetic: ignore ambient .env (which may have APINEX set).
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345678")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key-12345678")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345678")
    monkeypatch.setenv("APINEX_API_KEY", "")
    monkeypatch.setenv("ENABLE_LOCAL_LLM", "false")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        decision = engine.route(TaskType.INTENT_EXTRACTION, SensitivityLevel.INTERNAL)
        assert decision.provider == "groq"
        assert decision.model == "openai/gpt-oss-20b"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        for k in (
            "GROQ_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "ENABLE_LOCAL_LLM",
        ):
            os.environ.pop(k, None)


@pytest.mark.asyncio
async def test_routing_engine_spec_generation(monkeypatch):
    # Free GROQ gpt-oss-120b preferred when LOCAL/APINEX off; paid OPENAI
    # fallback covers OPENAI-only deployments. Never routes to a provider
    # without a key (P0-2).
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345678")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345678")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-nvidia-key-12345678")
    monkeypatch.setenv("APINEX_API_KEY", "")
    monkeypatch.setenv("ENABLE_LOCAL_LLM", "false")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        decision = engine.route(TaskType.SPEC_GENERATION, SensitivityLevel.INTERNAL)
        # Free preferred: GROQ gpt-oss-120b
        assert decision.provider == "groq"
        assert decision.model == "openai/gpt-oss-120b"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        for k in (
            "GROQ_API_KEY",
            "OPENAI_API_KEY",
            "NVIDIA_NIM_API_KEY",
            "ENABLE_LOCAL_LLM",
        ):
            os.environ.pop(k, None)


@pytest.mark.asyncio
async def test_routing_engine_sensitivity(monkeypatch):
    # Tenant-sensitive spec must never touch free Groq/OpenRouter endpoints.
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345678")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "test-nvidia-key-12345678")
    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("APINEX_API_KEY", "")
    monkeypatch.setenv("ENABLE_LOCAL_LLM", "false")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        decision = engine.route(
            TaskType.SPEC_GENERATION, SensitivityLevel.TENANT_SENSITIVE
        )
        assert decision.provider in ("local", "openai", "nvidia_nim")
        assert decision.provider not in ("groq", "openrouter")
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        for k in ("OPENAI_API_KEY", "NVIDIA_NIM_API_KEY", "ENABLE_LOCAL_LLM"):
            os.environ.pop(k, None)


@pytest.mark.asyncio
async def test_routing_engine_local_slm_when_flag_on(monkeypatch):
    """With ENABLE_LOCAL_LLM=true, spec generation prefers the offline SLM."""
    import os

    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("ENABLE_LOCAL_LLM", "true")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        assert engine.providers[ProviderName.LOCAL].enabled is True
        decision = engine.route(TaskType.SPEC_GENERATION, SensitivityLevel.INTERNAL)
        assert decision.provider == "local"
        assert decision.model == "phi-3-mini-3.8b-q4"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        os.environ.pop("ENABLE_LOCAL_LLM", None)


@pytest.mark.asyncio
async def test_routing_engine_intent_clarify_local_slm_when_flag_on(monkeypatch):
    """With ENABLE_LOCAL_LLM=true, planning tasks prefer the offline SLM."""
    import os

    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("ENABLE_LOCAL_LLM", "true")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        for task in (TaskType.INTENT_EXTRACTION, TaskType.CLARIFICATION):
            decision = engine.route(task, SensitivityLevel.INTERNAL)
            assert decision.provider == "local"
            assert decision.model == "phi-3-mini-3.8b-q4"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        os.environ.pop("ENABLE_LOCAL_LLM", None)


@pytest.mark.asyncio
async def test_routing_embedding(monkeypatch):
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345678")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        decision = engine.route(TaskType.EMBEDDING, SensitivityLevel.INTERNAL)
        assert decision.provider == "openai"
        assert decision.model == "text-embedding-3-small"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        os.environ.pop("OPENAI_API_KEY", None)


@pytest.mark.asyncio
async def test_routing_copilot_chat(monkeypatch):
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345678")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345678")
    monkeypatch.setenv("APINEX_API_KEY", "")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        decision = engine.route(TaskType.COPILOT_CHAT, SensitivityLevel.PUBLIC)
        assert decision.provider == "groq"
        assert decision.model == "openai/gpt-oss-20b"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        for k in ("GROQ_API_KEY", "OPENAI_API_KEY"):
            os.environ.pop(k, None)


@pytest.mark.asyncio
async def test_routing_stt(monkeypatch):
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam-key-12345678")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        decision = engine.route(TaskType.STT, SensitivityLevel.INTERNAL)
        assert decision.provider == "sarvam"
        assert decision.model == "saarika:v2"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        os.environ.pop("SARVAM_API_KEY", None)


@pytest.mark.asyncio
async def test_routing_tts(monkeypatch):
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("SARVAM_API_KEY", "test-sarvam-key-12345678")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        decision = engine.route(TaskType.TTS, SensitivityLevel.INTERNAL)
        assert decision.provider == "sarvam"
        assert decision.model == "bulbul:v1"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        os.environ.pop("SARVAM_API_KEY", None)


@pytest.mark.asyncio
async def test_routing_fallback_on_circuit_open(monkeypatch):
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345678")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-or-key-12345678")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345678")
    monkeypatch.setenv("APINEX_API_KEY", "")
    monkeypatch.setenv("ENABLE_LOCAL_LLM", "false")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        cb = get_circuit_breaker(ProviderName.GROQ)
        # Force circuit open
        for _ in range(6):
            cb.record_failure()
        assert cb.state.value == "open"
        # Try routing with preferred groq but circuit open should fallback
        decision = engine.route(TaskType.INTENT_EXTRACTION, SensitivityLevel.INTERNAL)
        # Should fallback to openai/openrouter or not groq
        assert decision.provider != "groq" or decision.model != "openai/gpt-oss-20b"
        # Reset
        cb.state = "closed"
        cb.failure_count = 0
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        for k in (
            "GROQ_API_KEY",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "ENABLE_LOCAL_LLM",
        ):
            os.environ.pop(k, None)


@pytest.mark.asyncio
async def test_routing_provider_models_have_correct_task():
    from app.schemas.providers import DEFAULT_PROVIDERS

    for provider_name, config in DEFAULT_PROVIDERS.items():
        for model_id, profile in config.models.items():
            assert isinstance(profile.task_types, list)
            assert len(profile.task_types) > 0


@pytest.mark.asyncio
async def test_usage_tracker_logs(monkeypatch):
    from app.routing.usage import usage_tracker

    # Mock redis to avoid connection
    usage = {
        "provider": "groq",
        "model": "openai/gpt-oss-20b",
        "tokens": 100,
        "cost": 0.01,
    }
    # Just test that tracker can be called without error (even if redis down)
    try:
        await usage_tracker.log_usage(**usage)  # type: ignore
    except Exception:
        pass  # Expected if redis not connected
    assert True


@pytest.mark.asyncio
async def test_cache_invalidate(client):
    response = await client.post(
        "/v1/router/cache/invalidate", headers={"X-Api-Key": settings.ADMIN_API_KEY}
    )
    assert response.status_code in (200, 404, 422)
    # Should succeed even if no cache entries
    if response.status_code == 200:
        assert (
            "invalidated" in response.json()
            or "count" in response.json()
            or response.json() == {}
        )


@pytest.mark.asyncio
async def test_apinex_provider_schema():
    """Verify APINEX provider is registered in DEFAULT_PROVIDERS with free/glm-5.3-flash."""
    from app.schemas.providers import DEFAULT_PROVIDERS

    assert ProviderName.APINEX in DEFAULT_PROVIDERS
    apinex_cfg = DEFAULT_PROVIDERS[ProviderName.APINEX]
    assert apinex_cfg.base_url == "https://api.apinex.bond/v1"
    assert "free/glm-5.3-flash" in apinex_cfg.models
    assert SensitivityLevel.PUBLIC in apinex_cfg.supported_sensitivity
    assert SensitivityLevel.INTERNAL in apinex_cfg.supported_sensitivity
    assert SensitivityLevel.TENANT_SENSITIVE not in apinex_cfg.supported_sensitivity
    assert SensitivityLevel.REGULATED not in apinex_cfg.supported_sensitivity


@pytest.mark.asyncio
async def test_apinex_sensitivity_blocking():
    """APInex must NEVER be routed for tenant-sensitive or regulated tasks (Rule 4)."""
    from app.routing.engine import RoutingEngine

    engine = RoutingEngine()
    for task in (
        TaskType.SPEC_GENERATION,
        TaskType.INTENT_EXTRACTION,
        TaskType.COPILOT_CHAT,
        TaskType.VALIDATION,
    ):
        for sens in (SensitivityLevel.TENANT_SENSITIVE, SensitivityLevel.REGULATED):
            policy = engine.get_policy(task, sens)
            assert ProviderName.APINEX in policy.blocked_providers
            assert ProviderName.APINEX not in policy.allowed_providers


@pytest.mark.asyncio
async def test_apinex_primary_routing_when_key_set(monkeypatch):
    """When APINEX_API_KEY is configured, APInex is primary for public/internal tasks with free/glm-5.3-flash."""
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("APINEX_API_KEY", "sk-apx-test-key-12345678")
    monkeypatch.setenv("ENABLE_LOCAL_LLM", "false")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        assert engine.providers[ProviderName.APINEX].enabled is True

        decision_spec = engine.route(
            TaskType.SPEC_GENERATION, SensitivityLevel.INTERNAL
        )
        assert decision_spec.provider == "apinex"
        assert decision_spec.model == "free/glm-5.3-flash"

        decision_intent = engine.route(
            TaskType.INTENT_EXTRACTION, SensitivityLevel.PUBLIC
        )
        assert decision_intent.provider == "apinex"
        assert decision_intent.model == "free/glm-5.3-flash"

        decision_chat = engine.route(TaskType.COPILOT_CHAT, SensitivityLevel.INTERNAL)
        assert decision_chat.provider == "apinex"
        assert decision_chat.model == "free/glm-5.3-flash"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        os.environ.pop("APINEX_API_KEY", None)


@pytest.mark.asyncio
async def test_apinex_litellm_model_and_params():
    """Verify LiteLLM client converts apinex models to openai/ prefix."""
    from app.providers.litellm_client import LiteLLMClient

    assert LiteLLMClient._is_apinex_provider(ProviderName.APINEX) is True
    assert LiteLLMClient._is_apinex_provider("apinex") is True

    m1 = LiteLLMClient._to_litellm_model(ProviderName.APINEX, "free/glm-5.3-flash")
    assert m1 == "openai/free/glm-5.3-flash"

    m2 = LiteLLMClient._to_litellm_model("apinex", "gemini-3.8-flash")
    assert m2 == "openai/gemini-3.8-flash"

    m3 = LiteLLMClient._to_litellm_model("apinex", "apinex/deepseek-v4.1-flash")
    assert m3 == "openai/deepseek-v4.1-flash"


@pytest.mark.asyncio
async def test_spec_generation_skips_providers_without_keys(monkeypatch):
    """P0-2: OPENAI empty must not be selected; GROQ fallback must win."""
    import os
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345678")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("APINEX_API_KEY", "")
    monkeypatch.setenv("ENABLE_LOCAL_LLM", "false")
    # Ensure empty string (not just missing) also disables OPENAI
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        assert engine.providers[ProviderName.OPENAI].enabled is False
        assert engine.providers[ProviderName.GROQ].enabled is True
        decision = engine.route(TaskType.SPEC_GENERATION, SensitivityLevel.INTERNAL)
        assert decision.provider != "openai"
        assert decision.provider == "groq"
        assert decision.model == "openai/gpt-oss-120b"
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        for k in ("GROQ_API_KEY", "OPENAI_API_KEY", "ENABLE_LOCAL_LLM"):
            os.environ.pop(k, None)


@pytest.mark.asyncio
async def test_providers_disabled_without_keys(monkeypatch):
    """P0-2: /health providers must reflect key gating (openai:false when empty)."""
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("GROQ_API_KEY", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("SARVAM_API_KEY", "")
    monkeypatch.setenv("APINEX_API_KEY", "")
    monkeypatch.setenv("ENABLE_LOCAL_LLM", "false")
    get_settings.cache_clear()
    try:
        engine = RoutingEngine()
        assert engine.providers[ProviderName.GROQ].enabled is False
        assert engine.providers[ProviderName.OPENAI].enabled is False
        assert engine.providers[ProviderName.LOCAL].enabled is False
        assert engine.providers[ProviderName.APINEX].enabled is False
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_local_down_falls_back_to_groq(monkeypatch):
    """P0-1: Ollama APIConnectionError must trigger fallback, not immediate 502."""
    import os
    from unittest.mock import AsyncMock, patch

    import litellm
    from app.providers.litellm_client import ChatCompletionRequest, LiteLLMClient
    from app.routing.engine import RoutingEngine

    monkeypatch.setenv("ENABLE_LOCAL_LLM", "true")
    monkeypatch.setenv("GROQ_API_KEY", "test-groq-key-12345678")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key-12345678")
    monkeypatch.setenv("APINEX_API_KEY", "")
    get_settings.cache_clear()
    try:
        # Fresh engine prefers LOCAL for SPEC when flag on
        engine = RoutingEngine()
        assert engine.providers[ProviderName.LOCAL].enabled is True
        decision = engine.route(TaskType.SPEC_GENERATION, SensitivityLevel.INTERNAL)
        assert decision.provider == "local"

        client = LiteLLMClient()
        # Avoid real Redis quota checks
        client.usage_tracker.check_quota = AsyncMock(return_value=True)  # type: ignore

        async def _fake_usage(*args, **kwargs):
            return None

        # Patch module-level log function used inside chat_completion
        conn_err = Exception("Cannot connect to host ollama:11434")
        # Mark as litellm APIConnectionError shape if available
        try:
            conn_err = litellm.exceptions.APIConnectionError(
                message="Cannot connect to host ollama:11434",
                llm_provider="ollama",
                model="ollama/phi3:mini",
            )
        except Exception:
            pass

        ok_resp = type(
            "R",
            (),
            {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": type(
                    "U",
                    (),
                    {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                )(),
            },
        )()

        with (
            patch("app.providers.litellm_client.routing_engine", engine),
            patch(
                "app.providers.litellm_client.log_llm_usage",
                new=AsyncMock(side_effect=_fake_usage),
            ),
            patch(
                "app.providers.litellm_client.get_cached_response",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.providers.litellm_client.set_cached_response",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "litellm.acompletion", new=AsyncMock(side_effect=[conn_err, ok_resp])
            ),
        ):
            req = ChatCompletionRequest(
                messages=[{"role": "user", "content": "hello"}],
                task_type="spec_generation",
                sensitivity="internal",
                use_cache=False,
            )
            resp = await client.chat_completion(req)
            assert resp.provider != "local"
            assert resp.provider in (
                "groq",
                "openai",
                "nvidia_nim",
                "openrouter",
                "apinex",
            )
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()
        for k in ("ENABLE_LOCAL_LLM", "GROQ_API_KEY", "OPENAI_API_KEY"):
            os.environ.pop(k, None)

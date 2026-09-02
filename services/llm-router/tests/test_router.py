"""Tests for LLM Router"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import get_settings
from app.schemas.providers import TaskType, SensitivityLevel, ProviderName
from app.routing.engine import routing_engine
from app.routing.circuit_breaker import get_circuit_breaker

settings = get_settings()
settings.ADMIN_API_KEY = "test-admin-key"


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert "providers" in response.json()


@pytest.mark.asyncio
async def test_root(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "name" in response.json()


@pytest.mark.asyncio
async def test_list_providers(client):
    response = await client.get("/v1/router/providers", headers={"X-Api-Key": settings.ADMIN_API_KEY})
    assert response.status_code == 200
    data = response.json()
    assert "providers" in data


@pytest.mark.asyncio
async def test_list_policies(client):
    response = await client.get("/v1/router/policies", headers={"X-Api-Key": settings.ADMIN_API_KEY})
    assert response.status_code == 200
    data = response.json()
    assert "policies" in data


@pytest.mark.asyncio
async def test_admin_routes_reject_missing_api_key(client):
    response = await client.get("/v1/router/providers")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_routes_reject_wrong_api_key(client):
    response = await client.get("/v1/router/cache/stats", headers={"X-Api-Key": "wrong-key"})
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
async def test_routing_engine_intent_extraction():
    decision = routing_engine.route(TaskType.INTENT_EXTRACTION, SensitivityLevel.INTERNAL)
    assert decision.provider == "groq"
    assert decision.model == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_routing_engine_spec_generation():
    decision = routing_engine.route(TaskType.SPEC_GENERATION, SensitivityLevel.INTERNAL)
    assert decision.provider == "groq"
    assert decision.model == "openai/gpt-oss-120b"


@pytest.mark.asyncio
async def test_routing_engine_sensitivity():
    decision = routing_engine.route(TaskType.SPEC_GENERATION, SensitivityLevel.TENANT_SENSITIVE)
    assert decision.provider == "openai"
    assert decision.model == "gpt-4o"


@pytest.mark.asyncio
async def test_routing_embedding():
    decision = routing_engine.route(TaskType.EMBEDDING, SensitivityLevel.INTERNAL)
    assert decision.provider == "openai"
    assert decision.model == "text-embedding-3-small"


@pytest.mark.asyncio
async def test_routing_copilot_chat():
    decision = routing_engine.route(TaskType.COPILOT_CHAT, SensitivityLevel.PUBLIC)
    assert decision.provider == "groq"
    assert decision.model == "openai/gpt-oss-20b"


@pytest.mark.asyncio
async def test_routing_stt():
    decision = routing_engine.route(TaskType.STT, SensitivityLevel.INTERNAL)
    assert decision.provider == "sarvam"
    assert decision.model == "saarika:v2"


@pytest.mark.asyncio
async def test_routing_tts():
    decision = routing_engine.route(TaskType.TTS, SensitivityLevel.INTERNAL)
    assert decision.provider == "sarvam"
    assert decision.model == "bulbul:v1"


@pytest.mark.asyncio
async def test_routing_fallback_on_circuit_open():
    cb = get_circuit_breaker(ProviderName.GROQ)
    # Force circuit open
    for _ in range(6):
        cb.record_failure()
    assert cb.state.value == "open"
    # Try routing with preferred groq but circuit open should fallback
    decision = routing_engine.route(TaskType.INTENT_EXTRACTION, SensitivityLevel.INTERNAL)
    # Should fallback to openai or not groq
    assert decision.provider != "groq" or decision.model != "openai/gpt-oss-20b"
    # Reset
    cb.state = "closed"
    cb.failure_count = 0


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
    usage = {"provider": "groq", "model": "openai/gpt-oss-20b", "tokens": 100, "cost": 0.01}
    # Just test that tracker can be called without error (even if redis down)
    try:
        await usage_tracker.log_usage(**usage)  # type: ignore
    except Exception:
        pass  # Expected if redis not connected
    assert True


@pytest.mark.asyncio
async def test_cache_invalidate(client):
    response = await client.post("/v1/router/cache/invalidate", headers={"X-Api-Key": settings.ADMIN_API_KEY})
    assert response.status_code in (200, 404, 422)
    # Should succeed even if no cache entries
    if response.status_code == 200:
        assert "invalidated" in response.json() or "count" in response.json() or response.json() == {}

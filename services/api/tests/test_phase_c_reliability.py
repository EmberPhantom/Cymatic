"""Phase C-API reliability P1s: phantom writes, auth guards, rate limits."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import func, select

from app.models.agent_action import AgentAction
from app.models.credit_ledger import CreditLedger  # noqa: F401 (model registry)
from app.models.project import ProjectStatus
from app.models.runtime_event import RuntimeEvent
from app.models.stream_session import StreamSession, StreamSessionStatus
from app.models.voice_session import VoiceSession


async def _published_stream_session(db_session, test_project, test_user):
    test_project.status = ProjectStatus.PUBLISHED
    session = StreamSession(
        project_id=test_project.id,
        user_id=test_user.id,
        status=StreamSessionStatus.CONNECTING,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


def _failing_render_client():
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.ConnectError("render unavailable")
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    return client


def _ok_llm_client(text="hello from mock"):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "choices": [{"message": {"content": text}}],
        "provider": "mock",
    }
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    return client


def _failing_llm_client():
    response = MagicMock()
    response.raise_for_status.side_effect = httpx.ConnectError("llm down")
    client = MagicMock()
    client.post = AsyncMock(return_value=response)
    return client


async def _count(db_session, model, session_id):
    return await db_session.scalar(
        select(func.count())
        .select_from(model)
        .where(model.session_id == session_id)
    )


# --- 1. Phantom input events: forward FIRST, persist only on success ---


@pytest.mark.asyncio
async def test_input_forward_failure_persists_no_event(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    sid = session.id
    await db_session.close()
    with patch(
        "app.api.v1.endpoints.streaming._get_http_client",
        return_value=_failing_render_client(),
    ):
        resp = await client.post(
            f"/v1/stream/sessions/{sid}/input",
            json={"input_type": "controller", "payload": {}, "timestamp": 1.0},
            headers=auth_headers,
        )
    assert resp.status_code == 503
    assert await _count(db_session, RuntimeEvent, sid) == 0


@pytest.mark.asyncio
async def test_input_forward_success_persists_event(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    sid = session.id
    await db_session.close()
    ok = MagicMock()
    ok.raise_for_status.return_value = None
    ok_client = MagicMock()
    ok_client.post = AsyncMock(return_value=ok)
    with patch(
        "app.api.v1.endpoints.streaming._get_http_client",
        return_value=ok_client,
    ):
        resp = await client.post(
            f"/v1/stream/sessions/{sid}/input",
            json={"input_type": "controller", "payload": {}, "timestamp": 1.0},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert await _count(db_session, RuntimeEvent, sid) == 1


# --- 2. Commit-before-LLM: rows only after downstream success ---


@pytest.mark.asyncio
async def test_copilot_message_failure_persists_no_action(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    sid = session.id
    await db_session.close()
    with patch(
        "app.api.v1.endpoints.streaming._get_http_client",
        return_value=_failing_llm_client(),
    ):
        resp = await client.post(
            f"/v1/stream/sessions/{sid}/agent/message",
            json={"message": "hello"},
            headers=auth_headers,
        )
    assert resp.status_code == 503
    assert await _count(db_session, AgentAction, sid) == 0


@pytest.mark.asyncio
async def test_copilot_message_success_persists_action(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    sid = session.id
    await db_session.close()
    with patch(
        "app.api.v1.endpoints.streaming._get_http_client",
        return_value=_ok_llm_client(),
    ):
        resp = await client.post(
            f"/v1/stream/sessions/{sid}/agent/message",
            json={"message": "hello"},
            headers=auth_headers,
        )
    assert resp.status_code == 200
    assert resp.json()["response"] == "hello from mock"
    assert await _count(db_session, AgentAction, sid) == 1


@pytest.mark.asyncio
async def test_voice_transcript_failure_persists_no_row(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    sid = session.id
    await db_session.close()
    with patch(
        "app.api.v1.endpoints.streaming._get_http_client",
        return_value=_failing_llm_client(),
    ):
        resp = await client.post(
            f"/v1/stream/sessions/{sid}/voice/transcript",
            json={"transcript": "hello"},
            headers=auth_headers,
        )
    assert resp.status_code == 503
    assert await _count(db_session, VoiceSession, sid) == 0


@pytest.mark.asyncio
async def test_render_voice_chat_failure_persists_no_row(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    sid = session.id
    await db_session.close()
    stt_ok = MagicMock()
    stt_ok.raise_for_status.return_value = None
    stt_ok.json.return_value = {"text": "hello"}
    chat_fail = MagicMock()
    chat_fail.raise_for_status.side_effect = httpx.ConnectError("llm down")
    render_client = MagicMock()
    render_client.post = AsyncMock(side_effect=[stt_ok, chat_fail])
    with patch(
        "app.api.v1.endpoints.render._get_http_client",
        return_value=render_client,
    ):
        resp = await client.post(
            f"/v1/render/sessions/{sid}/voice/audio",
            files={"audio": ("ptt.wav", b"\x00" * 320, "audio/wav")},
            headers=auth_headers,
        )
    assert resp.status_code == 503
    assert await _count(db_session, VoiceSession, sid) == 0


# --- 3. Rate-limit coverage: forced-limited dependency -> 429 ---


def _force_limited(monkeypatch):
    async def _limited(key, limit, _retried=False):
        return True, 1

    monkeypatch.setattr(
        "cymatic_shared.rate_limit.is_rate_limited", _limited
    )


@pytest.mark.asyncio
async def test_rate_limits_fire_on_llm_and_cost_endpoints(
    client, auth_headers, test_project, monkeypatch
):
    _force_limited(monkeypatch)
    pid = test_project.id
    cases = [
        ("POST", f"/v1/projects/{pid}/intake", {"json": {"prompt": "hi"}}),
        ("POST", f"/v1/projects/{pid}/clarify", {"json": {"answers": {}}}),
        (
            "POST",
            f"/v1/projects/{pid}/clarify-with-state",
            {"json": {"answers": {}}},
        ),
        ("POST", f"/v1/projects/{pid}/plan", {"json": {"run_id": "nope"}}),
        (
            "POST",
            f"/v1/projects/{pid}/plan/1/approve",
            {},
        ),
        (
            "POST",
            "/v1/assets/upload/init",
            {
                "json": {
                    "filename": "t.glb",
                    "content_type": "model/gltf-binary",
                    "type": "model_3d",
                }
            },
        ),
        ("POST", "/v1/stream/sessions", {"json": {"project_id": pid}}),
        (
            "POST",
            "/v1/render/sessions",
            {
                "json": {
                    "project_id": pid,
                    "device_id": "rate-limit-dev",
                    "app_version": "0.1.0",
                }
            },
        ),
        (
            "POST",
            "/v1/stream/sessions/99999/input",
            {"json": {"input_type": "controller", "payload": {}, "timestamp": 1.0}},
        ),
        (
            "POST",
            "/v1/stream/sessions/99999/agent/message",
            {"json": {"message": "hi"}},
        ),
        (
            "POST",
            "/v1/stream/sessions/99999/voice/transcript",
            {"json": {"transcript": "hi"}},
        ),
    ]
    for method, path, kwargs in cases:
        resp = await client.request(method, path, headers=auth_headers, **kwargs)
        assert resp.status_code == 429, f"{method} {path} -> {resp.status_code}"


@pytest.mark.asyncio
async def test_rate_limit_fires_on_render_voice(
    client, auth_headers, test_project, monkeypatch
):
    _force_limited(monkeypatch)
    resp = await client.post(
        "/v1/render/sessions/99999/voice/audio",
        files={"audio": ("ptt.wav", b"\x00" * 320, "audio/wav")},
        headers=auth_headers,
    )
    assert resp.status_code == 429


@pytest.mark.asyncio
async def test_rate_limit_fires_on_editing(
    client, auth_headers, test_project, monkeypatch
):
    _force_limited(monkeypatch)
    import app.api.v1.endpoints.editing as editing_mod

    monkeypatch.setattr(editing_mod.settings, "ENABLE_MANUAL_EDITING", True)
    resp = await client.post(
        f"/v1/projects/{test_project.id}/specs/1/edit",
        json={"operations": []},
        headers=auth_headers,
    )
    # Rate limit runs before the body: 429 even though the spec is missing.
    assert resp.status_code == 429


# --- 6. Auth inconsistencies ---


@pytest.mark.asyncio
async def test_inactive_login_is_403(client, db_session, test_user):
    test_user.is_active = False
    await db_session.commit()
    resp = await client.post(
        "/v1/auth/login",
        data={"username": test_user.email, "password": "testpass12345"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_self_deactivate(
    client, admin_auth_headers, test_user, db_session
):
    me = await client.get("/v1/auth/me", headers=admin_auth_headers)
    assert me.status_code == 200
    own_id = me.json()["id"]

    # Self-deactivation is blocked (mirrors the self-demotion guard).
    blocked = await client.patch(
        f"/v1/users/{own_id}",
        json={"is_active": False},
        headers=admin_auth_headers,
    )
    assert blocked.status_code == 400

    # Deactivating *another* user in the org is still allowed (scoped guard).
    other = await client.patch(
        f"/v1/users/{test_user.id}",
        json={"is_active": False},
        headers=admin_auth_headers,
    )
    assert other.status_code == 200
    assert other.json()["is_active"] is False

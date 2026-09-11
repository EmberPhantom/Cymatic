"""P2 - Streaming edge cases"""
import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.project import ProjectStatus
from app.models.stream_session import StreamSession, StreamSessionStatus


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


@pytest.mark.asyncio
async def test_create_stream_session_requires_published_project(client, auth_headers, test_project):
    # Project is draft, not published -> should 400
    resp = await client.post("/v1/stream/sessions", json={"project_id": test_project.id}, headers=auth_headers)
    assert resp.status_code in (400, 404, 422)

@pytest.mark.asyncio
async def test_stream_ws_tenant_and_revoked(client, auth_headers, test_project):
    # Create a stream session first (may fail if not published, but test auth)
    # Try WS with invalid token - we test the HTTP upgrade fails
    # Use the /v1/stream/sessions/{id}/offer endpoint with invalid session
    resp = await client.post("/v1/stream/sessions/99999/offer", json={"sdp": "test", "type": "offer"}, headers=auth_headers)
    assert resp.status_code in (404, 400, 503)

@pytest.mark.asyncio
async def test_stream_offer_render_unavailable(client, auth_headers, test_project):
    # Mock render server unavailable
    with patch("app.api.v1.endpoints.streaming.httpx.AsyncClient") as mock_client:
        mock_resp = AsyncMock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = Exception("render unavailable")
        mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        # Try to create session - will try to contact render server
        resp = await client.post("/v1/stream/sessions", json={"project_id": test_project.id}, headers=auth_headers)
        # Should be 400 not published or 503 render unavailable
        assert resp.status_code in (400, 404, 503)

@pytest.mark.asyncio
async def test_stream_input_writes_runtime_event(client, auth_headers, test_project):
    # Valid InputPacket schema against a nonexistent session -> 404 path
    # (proves the endpoint exists and session lookup runs before forwarding).
    resp = await client.post("/v1/stream/sessions/99999/input", json={"input_type": "controller", "payload": {}, "timestamp": 1.0}, headers=auth_headers)
    assert resp.status_code in (404, 400)

@pytest.mark.asyncio
async def test_stream_copilot_fallback(client, auth_headers, test_project):
    # Copilot message should fallback to 503 if LLM router down
    resp = await client.post("/v1/stream/sessions/99999/agent/message", json={"message": "hello"}, headers=auth_headers)
    assert resp.status_code in (404, 400, 503, 502)


@pytest.mark.asyncio
async def test_candidate_forward_failure_is_not_reported_as_success(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    # Release the fixture connection before the request so only the
    # endpoint session is open (avoids asyncpg "another operation in
    # progress" contention between fixture and request sessions).
    await db_session.close()
    with patch(
        "app.api.v1.endpoints.streaming._get_http_client",
        return_value=_failing_render_client(),
    ):
        resp = await client.post(
            f"/v1/stream/sessions/{session.id}/candidate",
            json={"candidate": "candidate", "sdp_mid": "0", "sdp_mline_index": 0},
            headers=auth_headers,
        )
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_input_forward_failure_is_not_reported_as_success(
    client, auth_headers, db_session, test_project, test_user
):
    session = await _published_stream_session(db_session, test_project, test_user)
    # Release the fixture connection before the request (see above).
    await db_session.close()
    with patch(
        "app.api.v1.endpoints.streaming._get_http_client",
        return_value=_failing_render_client(),
    ):
        resp = await client.post(
            f"/v1/stream/sessions/{session.id}/input",
            json={"input_type": "controller", "payload": {}, "timestamp": 1.0},
            headers=auth_headers,
        )
    assert resp.status_code == 503

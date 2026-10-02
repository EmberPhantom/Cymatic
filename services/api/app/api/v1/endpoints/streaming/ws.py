"""WebSocket signaling endpoint (split, no logic change)."""

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from typing import Literal
from sqlalchemy import select
import json
import structlog
from jose import JWTError
from app.core.config import get_settings
from app.core.security import decode_token, is_token_revoked
from app.core.rate_limit import is_rate_limited
from app.db.session import AsyncSessionLocal
from app.models.stream_session import StreamSession
from app.models.project import Project
from app.models.user import User

# Agent/HTTP helpers resolve via the streaming package namespace
# (app.api.v1.endpoints.streaming.*) so tests can monkeypatch them.
from app.api.v1.endpoints import streaming as _ns

settings = get_settings()
logger = structlog.get_logger()

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def websocket_signaling(
    websocket: WebSocket,
    session_id: str,
):
    """WebSocket endpoint for WebRTC signaling between render server and Android client."""
    # Validate session_id is numeric
    try:
        session_id_int = int(session_id)
    except (ValueError, TypeError):
        await websocket.close(code=4002, reason="Invalid session ID")
        return

    # Token handling: prefer Authorization header to avoid URL leak, fallback to query for compat
    auth_header = websocket.headers.get("authorization") or websocket.headers.get(
        "Authorization"
    )
    token: str | None = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    else:
        # Check Sec-WebSocket-Protocol may contain token
        proto = websocket.headers.get(
            "sec-websocket-protocol"
        ) or websocket.headers.get("Sec-WebSocket-Protocol")
        if proto and proto.lower().startswith("bearer "):
            token = proto[7:].strip()
        else:
            token = websocket.query_params.get("token")
            if token:
                logger.warning("ws_token_in_query_deprecated", session_id=session_id)

    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    # Rate limit WS handshakes (per IP before auth). is_rate_limited is
    # fail-closed internally; an unexpected raise here also closes.
    try:
        client_host = websocket.client.host if websocket.client else "unknown"
        limited, _ = await is_rate_limited(
            f"ws:handshake:{client_host}", settings.RATE_LIMIT_WS_HANDSHAKE
        )
        if limited:
            await websocket.close(code=4029, reason="Rate limited")
            return
    except Exception as e:
        logger.warning("ws_handshake_rl_failed", error=str(e))
        await websocket.close(code=4029, reason="Rate limited")
        return

    # Decode and validate token (strict access type)
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            await websocket.close(code=4001, reason="Invalid token type")
            return
        user_id = payload.get("sub")
        if user_id is None:
            await websocket.close(code=4001, reason="Invalid token")
            return
        # Validate user_id is int-like
        try:
            int(user_id)
        except (ValueError, TypeError):
            await websocket.close(code=4001, reason="Invalid token")
            return
    except (JWTError, ValueError):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Check token revocation (RedisError handled inside)
    if await is_token_revoked(token):
        await websocket.close(code=4001, reason="Token revoked")
        return

    # Rate limit per user after auth (fail-closed on unexpected errors).
    try:
        limited_user, _ = await is_rate_limited(
            f"ws:user:{user_id}", settings.RATE_LIMIT_WS_USER
        )
        if limited_user:
            await websocket.close(code=4029, reason="Rate limited")
            return
    except Exception as e:
        logger.warning("ws_user_rl_failed", error=str(e))
        await websocket.close(code=4029, reason="Rate limited")
        return

    # Determine client_type via query alias "type" (avoid shadowing builtin)
    raw_type = websocket.query_params.get("type", "unknown")
    if raw_type not in ("android", "render_server", "web", "unknown"):
        client_type: Literal["android", "render_server", "web", "unknown"] = "unknown"
    else:
        client_type = raw_type  # type: ignore[assignment]

    # Verify session exists, user owns it, and user is active
    db = AsyncSessionLocal()
    try:
        result = await db.execute(
            select(StreamSession).where(StreamSession.id == session_id_int)
        )
        session = result.scalar_one_or_none()
        if not session:
            await websocket.close(code=4004, reason="Session not found")
            return
        if str(session.user_id) != str(user_id):
            await websocket.close(code=4003, reason="Forbidden")
            return

        # Verify user is active
        try:
            uid_int = int(str(user_id))
        except (ValueError, TypeError):
            await websocket.close(code=4001, reason="Invalid token")
            return
        user_result = await db.execute(select(User).where(User.id == uid_int))
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            await websocket.close(code=4001, reason="User inactive")
            return

        # Verify user's org matches session's project's org
        project_result = await db.execute(
            select(Project).where(Project.id == session.project_id)
        )
        project = project_result.scalar_one_or_none()
        if project and project.organization_id != user.organization_id:
            await websocket.close(code=4003, reason="Forbidden")
            return
    finally:
        await db.close()

    await _ns.signaling_manager.connect(websocket, session_id, client_type)

    try:
        while True:
            try:
                data = await websocket.receive_json()
            except json.JSONDecodeError:
                await websocket.close(code=4000, reason="Invalid JSON")
                break
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == "register":
                await websocket.send_json(
                    {
                        "type": "registered",
                        "payload": {
                            "session_id": session_id,
                            "client_type": client_type,
                        },
                    }
                )

            elif msg_type == "offer":
                await _ns.signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "answer":
                await _ns.signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "candidate":
                await _ns.signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "input":
                await _ns.signaling_manager.send_to_client(
                    session_id, "render_server", data
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "id": data.get("id", "")})

    except WebSocketDisconnect:
        logger.info(
            "signaling.disconnected", session_id=session_id, client_type=client_type
        )
    except (WebSocketDisconnect, OSError) as e:
        logger.error("signaling.error", session_id=session_id, error=str(e))
    finally:
        _ns.signaling_manager.disconnect(websocket, session_id)

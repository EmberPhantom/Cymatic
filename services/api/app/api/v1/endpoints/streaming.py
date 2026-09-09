from datetime import datetime, timezone
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Set, Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import httpx
import structlog
from jose import JWTError
from app.core.config import get_settings
from app.core.dependencies import require_viewer
from app.core.security import decode_token, is_token_revoked
from app.core.rate_limit import is_rate_limited
from app.db.session import get_db, AsyncSessionLocal
from app.models.stream_session import StreamSession, StreamSessionStatus
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.models.runtime_event import RuntimeEvent

router = APIRouter()
settings = get_settings()
logger = structlog.get_logger()

# Reuse global httpx client (avoid per-request AsyncClient creation)
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
        )
    return _http_client


class StreamSessionCreate(BaseModel):
    project_id: int
    device_info: Dict[str, Any] = {}


class StreamSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    status: str
    signaling_session_id: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[datetime] = None


class WebRTCOffer(BaseModel):
    sdp: str
    type: Literal["offer"]


class WebRTCAnswer(BaseModel):
    sdp: str
    type: Literal["answer"]


class ICECandidate(BaseModel):
    candidate: str
    sdp_mid: str
    sdp_mline_index: int


class InputPacket(BaseModel):
    input_type: str
    payload: Dict[str, Any]
    timestamp: float


class CopilotMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = {}


class VoiceTranscript(BaseModel):
    transcript: str
    language: str = "en"
    confidence: Optional[float] = None


@router.post(
    "/sessions",
    response_model=StreamSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_stream_session(
    session_data: StreamSessionCreate,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == session_data.project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != ProjectStatus.PUBLISHED:
        raise HTTPException(
            status_code=400, detail="Project must be published to stream"
        )

    session = StreamSession(
        project_id=session_data.project_id,
        user_id=current_user.id,
        status=StreamSessionStatus.PENDING,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    try:
        client = _get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions",
            json={"session_id": session.id, "project_id": session.project_id},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        if resp.status_code == 200:
            session.status = StreamSessionStatus.CONNECTING
            session.signaling_session_id = resp.json().get("signaling_session_id")
            await db.commit()
            await db.refresh(session)
    except httpx.ConnectError:
        session.status = StreamSessionStatus.FAILED
        await db.commit()
        logger.warning(
            "render_server_unavailable",
            session_id=session.id,
            url=settings.RENDER_SERVER_URL,
        )
    except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
        session.status = StreamSessionStatus.FAILED
        await db.commit()
        logger.error("render_server_signal_failed", session_id=session.id, error=str(e))

    logger.info("stream_session_created", session_id=session.id)
    return session


@router.get("/sessions/{session_id}", response_model=StreamSessionResponse)
async def get_stream_session(
    session_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post("/sessions/{session_id}/offer")
async def handle_offer(
    session_id: int,
    offer: WebRTCOffer,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        client = _get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/offer",
            json={"sdp": offer.sdp, "type": offer.type},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        resp.raise_for_status()
        answer_data = resp.json()
        session.status = StreamSessionStatus.ACTIVE
        session.started_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "status": "offer_forwarded",
            "session_id": session_id,
            "answer": answer_data,
        }
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Render server timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Render server error: {e.response.status_code}"
        )
    except OSError as e:
        logger.error("offer_forward_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to forward offer")


@router.post("/sessions/{session_id}/answer")
async def handle_answer(
    session_id: int,
    answer: WebRTCAnswer,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        client = _get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/answer",
            json={"sdp": answer.sdp, "type": answer.type},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        resp.raise_for_status()
        return {"status": "answer_forwarded", "session_id": session_id}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Render server timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=502, detail=f"Render server error: {e.response.status_code}"
        )
    except OSError as e:
        logger.error("answer_forward_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to forward answer")


@router.post("/sessions/{session_id}/end", response_model=StreamSessionResponse)
async def end_stream_session(
    session_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    session = await db.scalar(
        select(StreamSession).where(
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id,
        )
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session.status not in (
        StreamSessionStatus.DISCONNECTED,
        StreamSessionStatus.FAILED,
    ):
        session.status = StreamSessionStatus.DISCONNECTED
        session.ended_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(session)
    return session


@router.post("/sessions/{session_id}/candidate")
async def handle_candidate(
    session_id: int,
    candidate: ICECandidate,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        client = _get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/candidate",
            json={
                "candidate": candidate.candidate,
                "sdp_mid": candidate.sdp_mid,
                "sdp_mline_index": candidate.sdp_mline_index,
            },
            timeout=httpx.Timeout(5.0, connect=3.0),
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        logger.warning(
            "candidate_forward_failed_render_unavailable", session_id=session_id
        )
        raise HTTPException(status_code=503, detail="Render server unavailable")
    except httpx.TimeoutException:
        logger.warning("candidate_forward_timeout", session_id=session_id)
        raise HTTPException(status_code=504, detail="Render server timeout")
    except httpx.HTTPStatusError as e:
        logger.warning(
            "candidate_forward_http_error",
            session_id=session_id,
            status=e.response.status_code,
        )
        raise HTTPException(
            status_code=502, detail=f"Render server error: {e.response.status_code}"
        )
    except OSError as e:
        logger.warning("candidate_forward_error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to forward candidate")

    return {"status": "candidate_forwarded", "session_id": session_id}


@router.post("/sessions/{session_id}/input")
async def handle_input(
    session_id: int,
    input_packet: InputPacket,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    event = RuntimeEvent(
        session_id=session_id,
        event_type=f"input_{input_packet.input_type}",
        payload_json=input_packet.payload,
    )
    db.add(event)
    await db.commit()

    try:
        client = _get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/input",
            json={
                "input_type": input_packet.input_type,
                "payload": input_packet.payload,
                "timestamp": input_packet.timestamp,
            },
            timeout=httpx.Timeout(5.0, connect=3.0),
        )
        resp.raise_for_status()
    except httpx.ConnectError:
        logger.warning("input_forward_failed_render_unavailable", session_id=session_id)
        raise HTTPException(status_code=503, detail="Render server unavailable")
    except httpx.TimeoutException:
        logger.warning("input_forward_timeout", session_id=session_id)
        raise HTTPException(status_code=504, detail="Render server timeout")
    except httpx.HTTPStatusError as e:
        logger.warning(
            "input_forward_http_error",
            session_id=session_id,
            status=e.response.status_code,
        )
        raise HTTPException(
            status_code=502, detail=f"Render server error: {e.response.status_code}"
        )
    except OSError as e:
        logger.warning("input_forward_error", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to forward input")

    return {"status": "input_received", "session_id": session_id}


@router.post("/sessions/{session_id}/agent/message")
async def copilot_message(
    session_id: int,
    message: CopilotMessage,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from app.models.agent_action import AgentAction

    agent_action = AgentAction(
        session_id=session_id,
        action_type="copilot_message",
        payload_json={"message": message.message, "context": message.context},
    )
    db.add(agent_action)
    await db.commit()

    try:
        client = _get_http_client()
        resp = await client.post(
            f"{settings.LLM_ROUTER_URL}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": message.message}],
                "task_type": "copilot_chat",
                "sensitivity": "internal",
            },
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        resp.raise_for_status()
        data = resp.json()
        response_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        return {
            "response": response_text,
            "actions": [],
            "provider": data.get("provider", "unknown"),
        }
    except httpx.ConnectError:
        logger.warning("copilot_llm_unavailable", session_id=session_id)
        return JSONResponse(
            status_code=503,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )
    except httpx.TimeoutException:
        logger.warning("copilot_llm_timeout", session_id=session_id)
        return JSONResponse(
            status_code=504,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )
    except httpx.HTTPStatusError as e:
        logger.warning(
            "copilot_llm_http_error",
            session_id=session_id,
            status=e.response.status_code,
        )
        return JSONResponse(
            status_code=502,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )
    except (ValueError, OSError) as e:
        logger.error("copilot_llm_failed", session_id=session_id, error=str(e))
        return JSONResponse(
            status_code=500,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )


@router.post("/sessions/{session_id}/voice/transcript")
async def voice_transcript(
    session_id: int,
    transcript: VoiceTranscript,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    from app.models.voice_session import VoiceSession

    voice_session = VoiceSession(
        session_id=session_id,
        transcript=transcript.transcript,
    )
    db.add(voice_session)
    await db.commit()

    try:
        client = _get_http_client()
        resp = await client.post(
            f"{settings.LLM_ROUTER_URL}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": transcript.transcript}],
                "task_type": "copilot_chat",
                "sensitivity": "internal",
            },
            timeout=httpx.Timeout(30.0, connect=5.0),
        )
        resp.raise_for_status()
        data = resp.json()
        response_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        voice_session.response_text = response_text
        await db.commit()
        return {"response": response_text, "tts_audio_url": None}
    except httpx.ConnectError:
        logger.warning("voice_llm_unavailable", session_id=session_id)
        return JSONResponse(
            status_code=503,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )
    except httpx.TimeoutException:
        logger.warning("voice_llm_timeout", session_id=session_id)
        return JSONResponse(
            status_code=504,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )
    except httpx.HTTPStatusError as e:
        logger.warning(
            "voice_llm_http_error", session_id=session_id, status=e.response.status_code
        )
        return JSONResponse(
            status_code=502,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )
    except (ValueError, OSError) as e:
        logger.error("voice_llm_failed", session_id=session_id, error=str(e))
        return JSONResponse(
            status_code=500,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )


# WebSocket signaling for WebRTC


class SignalingManager:
    """Manages WebSocket connections for WebRTC signaling."""

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.session_participants: Dict[str, Dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: str, client_type: str):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = set()
        self.active_connections[session_id].add(websocket)

        if session_id not in self.session_participants:
            self.session_participants[session_id] = {}
        self.session_participants[session_id][client_type] = websocket

        logger.info(
            "signaling.connected", session_id=session_id, client_type=client_type
        )

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

        if session_id in self.session_participants:
            to_remove = [
                k
                for k, v in self.session_participants[session_id].items()
                if v == websocket
            ]
            for k in to_remove:
                del self.session_participants[session_id][k]
            if not self.session_participants[session_id]:
                del self.session_participants[session_id]

    async def send_to_other(self, session_id: str, sender: WebSocket, message: dict):
        if session_id in self.active_connections:
            for conn in self.active_connections[session_id]:
                if conn != sender:
                    try:
                        await conn.send_json(message)
                    except (WebSocketDisconnect, OSError):
                        pass

    async def send_to_client(self, session_id: str, client_type: str, message: dict):
        if session_id in self.session_participants:
            ws = self.session_participants[session_id].get(client_type)
            if ws:
                try:
                    await ws.send_json(message)
                except (WebSocketDisconnect, OSError):
                    pass


signaling_manager = SignalingManager()


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
    auth_header = websocket.headers.get("authorization") or websocket.headers.get("Authorization")
    token: str | None = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
    else:
        # Check Sec-WebSocket-Protocol may contain token
        proto = websocket.headers.get("sec-websocket-protocol") or websocket.headers.get("Sec-WebSocket-Protocol")
        if proto and proto.lower().startswith("bearer "):
            token = proto[7:].strip()
        else:
            token = websocket.query_params.get("token")
            if token:
                logger.warning("ws_token_in_query_deprecated", session_id=session_id)

    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return

    # Rate limit WS handshakes (per IP before auth)
    try:
        client_host = websocket.client.host if websocket.client else "unknown"
        limited, _ = await is_rate_limited(f"ws:handshake:{client_host}", "20/minute")
        if limited:
            await websocket.close(code=4029, reason="Rate limited")
            return
    except Exception:
        # Fail-closed would already be handled inside is_rate_limited; if that fails, close
        pass

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

    # Rate limit per user after auth
    try:
        limited_user, _ = await is_rate_limited(f"ws:user:{user_id}", "30/minute")
        if limited_user:
            await websocket.close(code=4029, reason="Rate limited")
            return
    except Exception:
        pass

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

    await signaling_manager.connect(websocket, session_id, client_type)

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
                await signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "answer":
                await signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "candidate":
                await signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "input":
                await signaling_manager.send_to_client(
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
        signaling_manager.disconnect(websocket, session_id)

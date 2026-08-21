from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Set, Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import structlog
from jose import JWTError
from app.core.config import get_settings
from app.core.dependencies import get_current_user, require_viewer
from app.core.security import decode_token, is_token_revoked
from app.db.session import get_db, AsyncSessionLocal
from app.models.stream_session import StreamSession, StreamSessionStatus
from app.models.project import Project
from app.models.user import User, UserRole
from app.models.runtime_event import RuntimeEvent

router = APIRouter()
settings = get_settings()
logger = structlog.get_logger()


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
    ended_at: Optional[str] = None


class WebRTCOffer(BaseModel):
    sdp: str
    type: str


class WebRTCAnswer(BaseModel):
    sdp: str
    type: str


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


@router.post("/sessions", response_model=StreamSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_stream_session(
    session_data: StreamSessionCreate,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Project).where(
            Project.id == session_data.project_id,
            Project.organization_id == current_user.organization_id
        )
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if project.status != "published":
        raise HTTPException(status_code=400, detail="Project must be published to stream")

    session = StreamSession(
        project_id=session_data.project_id,
        user_id=current_user.id,
        status=StreamSessionStatus.PENDING,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.RENDER_SERVER_URL}/api/sessions",
                json={"session_id": session.id, "project_id": session.project_id},
            )
            if resp.status_code == 200:
                session.status = StreamSessionStatus.CONNECTING
                session.signaling_session_id = resp.json().get("signaling_session_id")
                await db.commit()
                await db.refresh(session)
    except httpx.ConnectError:
        logger.warning("render_server_unavailable", session_id=session.id, url=settings.RENDER_SERVER_URL)
    except (httpx.TimeoutException, httpx.HTTPStatusError) as e:
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
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id
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
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/offer",
                json={"sdp": offer.sdp, "type": offer.type},
            )
            resp.raise_for_status()
            answer_data = resp.json()
            session.status = StreamSessionStatus.ACTIVE
            await db.commit()
            return {"status": "offer_forwarded", "session_id": session_id, "answer": answer_data}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Render server timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Render server error: {e.response.status_code}")
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
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/answer",
                json={"sdp": answer.sdp, "type": answer.type},
            )
            resp.raise_for_status()
        return {"status": "answer_forwarded", "session_id": session_id}
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Render server unavailable")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Render server timeout")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Render server error: {e.response.status_code}")
    except OSError as e:
        logger.error("answer_forward_failed", session_id=session_id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to forward answer")


@router.post("/sessions/{session_id}/candidate")
async def handle_candidate(
    session_id: int,
    candidate: ICECandidate,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/candidate",
                json={"candidate": candidate.candidate, "sdp_mid": candidate.sdp_mid, "sdp_mline_index": candidate.sdp_mline_index},
            )
    except httpx.ConnectError:
        logger.warning("candidate_forward_failed_render_unavailable", session_id=session_id)
    except httpx.TimeoutException:
        logger.warning("candidate_forward_timeout", session_id=session_id)
    except (httpx.HTTPStatusError, OSError) as e:
        logger.warning("candidate_forward_error", session_id=session_id, error=str(e))

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
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id
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
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/input",
                json={"input_type": input_packet.input_type, "payload": input_packet.payload, "timestamp": input_packet.timestamp},
            )
    except httpx.ConnectError:
        logger.warning("input_forward_failed_render_unavailable", session_id=session_id)
    except httpx.TimeoutException:
        logger.warning("input_forward_timeout", session_id=session_id)
    except (httpx.HTTPStatusError, OSError) as e:
        logger.warning("input_forward_error", session_id=session_id, error=str(e))

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
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.LLM_ROUTER_URL}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": message.message}],
                    "task_type": "copilot_chat",
                    "sensitivity": "internal",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {"response": response_text, "actions": [], "provider": data.get("provider", "unknown")}
    except httpx.ConnectError:
        logger.warning("copilot_llm_unavailable", session_id=session_id)
        return JSONResponse(status_code=503, content={"response": "Service temporarily unavailable.", "actions": []})
    except httpx.TimeoutException:
        logger.warning("copilot_llm_timeout", session_id=session_id)
        return JSONResponse(status_code=504, content={"response": "Service temporarily unavailable.", "actions": []})
    except httpx.HTTPStatusError as e:
        logger.warning("copilot_llm_http_error", session_id=session_id, status=e.response.status_code)
        return JSONResponse(status_code=502, content={"response": "Service temporarily unavailable.", "actions": []})
    except (ValueError, OSError) as e:
        logger.error("copilot_llm_failed", session_id=session_id, error=str(e))
        return JSONResponse(status_code=500, content={"response": "Service temporarily unavailable.", "actions": []})


@router.post("/sessions/{session_id}/voice/transcript")
async def voice_transcript(
    session_id: int,
    transcript: VoiceTranscript,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id,
            StreamSession.user_id == current_user.id
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.LLM_ROUTER_URL}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": transcript.transcript}],
                    "task_type": "copilot_chat",
                    "sensitivity": "internal",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            response_text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            voice_session.response_text = response_text
            await db.commit()
            return {"response": response_text, "tts_audio_url": None}
    except httpx.ConnectError:
        logger.warning("voice_llm_unavailable", session_id=session_id)
        return JSONResponse(status_code=503, content={"response": "I didn't catch that. Could you repeat?", "tts_audio_url": None})
    except httpx.TimeoutException:
        logger.warning("voice_llm_timeout", session_id=session_id)
        return JSONResponse(status_code=504, content={"response": "I didn't catch that. Could you repeat?", "tts_audio_url": None})
    except httpx.HTTPStatusError as e:
        logger.warning("voice_llm_http_error", session_id=session_id, status=e.response.status_code)
        return JSONResponse(status_code=502, content={"response": "I didn't catch that. Could you repeat?", "tts_audio_url": None})
    except (ValueError, OSError) as e:
        logger.error("voice_llm_failed", session_id=session_id, error=str(e))
        return JSONResponse(status_code=500, content={"response": "I didn't catch that. Could you repeat?", "tts_audio_url": None})


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

        logger.info("signaling.connected", session_id=session_id, client_type=client_type)

    def disconnect(self, websocket: WebSocket, session_id: str):
        if session_id in self.active_connections:
            self.active_connections[session_id].discard(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

        if session_id in self.session_participants:
            to_remove = [k for k, v in self.session_participants[session_id].items() if v == websocket]
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
        if session_id in self.session_participants.get(session_id, {}):
            ws = self.session_participants[session_id].get(client_type)
            if ws:
                try:
                    await ws.send_json(message)
                except (WebSocketDisconnect, OSError):
                    pass

signaling_manager = SignalingManager()

@router.websocket("/ws/{session_id}")
async def websocket_signaling(websocket: WebSocket, session_id: str, token: str = Query(...), type: Literal["android", "render_server", "unknown"] = Query("unknown")):
    """WebSocket endpoint for WebRTC signaling between render server and Android client."""
    # Validate session_id is numeric
    try:
        session_id_int = int(session_id)
    except (ValueError, TypeError):
        await websocket.close(code=4002, reason="Invalid session ID")
        return

    # Decode and validate token
    try:
        payload = decode_token(token)
        if payload.get("type") not in ("access", None):
            await websocket.close(code=4001, reason="Invalid token type")
            return
        user_id = payload.get("sub")
        if user_id is None:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except (JWTError, ValueError):
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Check token revocation
    if await is_token_revoked(token):
        await websocket.close(code=4001, reason="Token revoked")
        return

    client_type = type

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
        if str(session.user_id) != user_id:
            await websocket.close(code=4003, reason="Forbidden")
            return

        # Verify user is active
        user_result = await db.execute(select(User).where(User.id == int(user_id)))
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            await websocket.close(code=4001, reason="User inactive")
            return

        # Verify user's org matches session's project's org
        project_result = await db.execute(select(Project).where(Project.id == session.project_id))
        project = project_result.scalar_one_or_none()
        if project and project.organization_id != user.organization_id:
            await websocket.close(code=4003, reason="Forbidden")
            return
    finally:
        await db.close()

    await signaling_manager.connect(websocket, session_id, client_type)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")
            payload = data.get("payload", {})

            if msg_type == "register":
                await websocket.send_json({
                    "type": "registered",
                    "payload": {"session_id": session_id, "client_type": client_type}
                })

            elif msg_type == "offer":
                await signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "answer":
                await signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "candidate":
                await signaling_manager.send_to_other(session_id, websocket, data)

            elif msg_type == "input":
                await signaling_manager.send_to_client(session_id, "render_server", data)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong", "id": data.get("id", "")})

    except WebSocketDisconnect:
        signaling_manager.disconnect(websocket, session_id)
        logger.info("signaling.disconnected", session_id=session_id, client_type=client_type)
    except (WebSocketDisconnect, OSError) as e:
        logger.error("signaling.error", session_id=session_id, error=str(e))
        signaling_manager.disconnect(websocket, session_id)

from datetime import datetime
from fastapi import (
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Dict, Set, Any, Literal
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
import structlog
from app.core.config import get_settings
from app.models.stream_session import StreamSession
from app.services.scene_packages import get_latest_scene_package_url
from cymatic_shared.http import admin_headers, build_async_client

settings = get_settings()
logger = structlog.get_logger()
# Reuse global httpx client (avoid per-request AsyncClient creation)
_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = build_async_client(
            settings.STREAM_HTTP_TIMEOUT_SECONDS,
            settings.LLM_ROUTER_CONNECT_TIMEOUT_SECONDS,
            settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
            settings.HTTP_MAX_CONNECTIONS,
        )
    return _http_client


def _router_headers() -> dict[str, str]:
    """Auth headers for LLM-router calls (requires ADMIN_API_KEY when set)."""
    return admin_headers(settings.ADMIN_API_KEY)


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
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    scene_package_url: Optional[str] = None


async def _build_session_response(
    session: StreamSession, db: AsyncSession
) -> StreamSessionResponse:
    resp = StreamSessionResponse.model_validate(session)
    resp.scene_package_url = await get_latest_scene_package_url(db, session.project_id)
    return resp


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
    input_type: Literal["gaze", "controller", "head_pose", "voice", "hand_tracking"]
    payload: Dict[str, Any] = Field(default_factory=dict, max_length=50)
    timestamp: float = Field(ge=0)


class CopilotMessage(BaseModel):
    message: str = Field(min_length=1, max_length=10000)
    context: Optional[Dict[str, Any]] = Field(default_factory=dict)


class VoiceTranscript(BaseModel):
    transcript: str = Field(min_length=1, max_length=25000)
    language: str = Field(default="en", max_length=10)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


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

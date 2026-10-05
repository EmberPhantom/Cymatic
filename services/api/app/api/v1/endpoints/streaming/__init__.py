"""Stream session endpoints (split package; routes unchanged)."""

import httpx  # noqa: F401  (patch target: tests mock streaming.httpx)

from .common import (  # noqa: F401
    _get_http_client,
    _router_headers,
    _build_session_response,
    signaling_manager,
    SignalingManager,
    StreamSessionCreate,
    StreamSessionResponse,
    WebRTCOffer,
    WebRTCAnswer,
    ICECandidate,
    InputPacket,
    CopilotMessage,
    VoiceTranscript,
)
from . import sessions as _sessions  # noqa: F401
from . import copilot as _copilot  # noqa: F401
from . import ws as _ws  # noqa: F401
from .ws import websocket_signaling  # noqa: F401
from fastapi import APIRouter

router = APIRouter()
router.include_router(_sessions.router)
router.include_router(_copilot.router)
router.include_router(_ws.router)

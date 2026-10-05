"""Stream session REST endpoints (split, no logic change)."""

from datetime import datetime, timezone
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import structlog
from app.core.config import get_settings
from app.core.dependencies import require_creator, require_viewer
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.stream_session import StreamSession, StreamSessionStatus
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.models.runtime_event import RuntimeEvent

# Agent/HTTP helpers resolve via the streaming package namespace
# (app.api.v1.endpoints.streaming.*) so tests can monkeypatch them.
from app.api.v1.endpoints import streaming as _ns
from .common import (
    StreamSessionCreate,
    StreamSessionResponse,
    WebRTCOffer,
    WebRTCAnswer,
    ICECandidate,
    InputPacket,
    _build_session_response,
)

settings = get_settings()
logger = structlog.get_logger()

router = APIRouter()


@router.post(
    "/sessions",
    response_model=StreamSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_API))],
)
async def create_stream_session(
    session_data: StreamSessionCreate,
    current_user: User = Depends(require_creator),
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

    # MVP: one concurrent stream per user unless multiplayer enabled.
    if not settings.ENABLE_MULTIPLAYER:
        active = await db.scalar(
            select(StreamSession).where(
                StreamSession.user_id == current_user.id,
                StreamSession.status.in_(
                    [
                        StreamSessionStatus.PENDING,
                        StreamSessionStatus.CONNECTING,
                        StreamSessionStatus.ACTIVE,
                    ]
                ),
            )
        )
        if active is not None:
            raise HTTPException(
                status_code=409,
                detail="A stream session is already active",
            )

    # Signaling is client-pulled: both the Android client and the Unity render
    # server connect directly to /v1/stream/ws/{session_id}. There is no
    # separate HTTP push to a render-server listener (see legacy note on
    # handle_offer/handle_answer below) — the session id itself is the
    # rendezvous point, so it can stay PENDING until a client joins the socket.
    session = StreamSession(
        project_id=session_data.project_id,
        user_id=current_user.id,
        status=StreamSessionStatus.PENDING,
        signaling_session_id=None,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    logger.info("stream_session_created", session_id=session.id)
    return await _build_session_response(session, db)


@router.get("/sessions/active", response_model=StreamSessionResponse)
async def get_active_stream_session(
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Most recent non-terminal session for the caller, so a render server can
    discover which session to join without a push from the API (single-user MVP:
    at most one such session exists at a time unless multiplayer is enabled).

    Registered before /sessions/{session_id} so the literal "active" path
    segment isn't swallowed by the int-typed session_id route."""
    session = await db.scalar(
        select(StreamSession)
        .where(
            StreamSession.user_id == current_user.id,
            StreamSession.status.in_(
                [
                    StreamSessionStatus.PENDING,
                    StreamSessionStatus.CONNECTING,
                    StreamSessionStatus.ACTIVE,
                ]
            ),
        )
        .order_by(StreamSession.id.desc())
    )
    if not session:
        raise HTTPException(status_code=404, detail="No active session")
    return await _build_session_response(session, db)


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
    return await _build_session_response(session, db)


@router.post(
    "/sessions/{session_id}/offer",
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_API))],
)
async def handle_offer(
    session_id: int,
    offer: WebRTCOffer,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Legacy HTTP-push signaling transport.

    Not used by the current Android or Unity clients — both exchange
    offer/answer/candidate over the /v1/stream/ws/{session_id} WebSocket
    relay instead. Kept only as a possible future alternate transport for a
    render server that runs its own HTTP listener; it will always fail with
    503 against the current Unity render server, which has no such listener.
    """
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        client = _ns._get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/offer",
            json={"sdp": offer.sdp, "type": offer.type},
            timeout=httpx.Timeout(
                settings.STREAM_HTTP_TIMEOUT_SECONDS,
                connect=settings.LLM_ROUTER_CONNECT_TIMEOUT_SECONDS,
            ),
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


@router.post(
    "/sessions/{session_id}/answer",
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_API))],
)
async def handle_answer(
    session_id: int,
    answer: WebRTCAnswer,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Legacy HTTP-push signaling transport — see handle_offer docstring."""
    result = await db.execute(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == current_user.id
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        client = _ns._get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/answer",
            json={"sdp": answer.sdp, "type": answer.type},
            timeout=httpx.Timeout(
                settings.STREAM_HTTP_TIMEOUT_SECONDS,
                connect=settings.LLM_ROUTER_CONNECT_TIMEOUT_SECONDS,
            ),
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


@router.post(
    "/sessions/{session_id}/candidate",
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_API))],
)
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
        client = _ns._get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/candidate",
            json={
                "candidate": candidate.candidate,
                "sdp_mid": candidate.sdp_mid,
                "sdp_mline_index": candidate.sdp_mline_index,
            },
            timeout=httpx.Timeout(
                settings.STREAM_FORWARD_TIMEOUT_SECONDS,
                connect=settings.STREAM_FORWARD_CONNECT_SECONDS,
            ),
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


@router.post(
    "/sessions/{session_id}/input",
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_API))],
)
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

    # Forward FIRST: the runtime event is only persisted when the render
    # forward succeeds. Committing before the forward left phantom
    # input_* events in analytics/replay on 503/504.
    try:
        client = _ns._get_http_client()
        resp = await client.post(
            f"{settings.RENDER_SERVER_URL}/api/sessions/{session_id}/input",
            json={
                "input_type": input_packet.input_type,
                "payload": input_packet.payload,
                "timestamp": input_packet.timestamp,
            },
            timeout=httpx.Timeout(
                settings.STREAM_FORWARD_TIMEOUT_SECONDS,
                connect=settings.STREAM_FORWARD_CONNECT_SECONDS,
            ),
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

    event = RuntimeEvent(
        session_id=session_id,
        event_type=f"input_{input_packet.input_type}",
        payload_json=input_packet.payload,
    )
    db.add(event)
    await db.commit()

    return {"status": "input_received", "session_id": session_id}

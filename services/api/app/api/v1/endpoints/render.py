"""Native mobile render sessions (Unity-free path).

The Android renderer is a pure API client: login -> create render session ->
fetch scene JSON + assets -> render on-device in stereo. No WebRTC, no
render server. Session/input/copilot/voice semantics mirror streaming.py;
sessions share the stream_sessions table so analytics stay unified.
"""

import base64
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import require_creator, require_viewer
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.mobile_device import MobileDevice
from app.models.project import Project, ProjectStatus
from app.models.stream_session import StreamSession, StreamSessionStatus
from app.models.user import User
from app.services.scene_packages import get_latest_scene_package_url
from cymatic_shared.http import admin_headers, build_async_client

router = APIRouter()
settings = get_settings()
logger = structlog.get_logger()

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = build_async_client(
            settings.LLM_ROUTER_TIMEOUT_SECONDS,
            settings.LLM_ROUTER_CONNECT_TIMEOUT_SECONDS,
            settings.HTTP_MAX_KEEPALIVE_CONNECTIONS,
            settings.HTTP_MAX_CONNECTIONS,
        )
    assert _http_client is not None
    return _http_client


def _router_headers() -> dict[str, str]:
    return admin_headers(settings.ADMIN_API_KEY)


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in v.strip().split(".")[:3])
    except (ValueError, AttributeError):
        return (0,)


class RenderSessionCreate(BaseModel):
    project_id: int
    device_id: str = Field(min_length=1, max_length=128)
    app_version: str = Field(min_length=1, max_length=32, default="0.1.0")


class RenderSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    status: str
    device_id: Optional[str] = None
    scene_url: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


async def _check_device(
    db: AsyncSession, user: User, device_id: str, app_version: str
) -> MobileDevice:
    """Register-or-verify a mobile device. Revoked devices get 403."""
    if _version_tuple(app_version) < _version_tuple(settings.MOBILE_MIN_APP_VERSION):
        raise HTTPException(
            status_code=status.HTTP_426_UPGRADE_REQUIRED,
            detail=f"App {settings.MOBILE_MIN_APP_VERSION}+ required",
        )
    device = await db.scalar(
        select(MobileDevice).where(
            MobileDevice.user_id == user.id, MobileDevice.device_id == device_id
        )
    )
    now = datetime.now(timezone.utc)
    if device is None:
        device = MobileDevice(
            user_id=user.id,
            device_id=device_id,
            app_version=app_version,
            last_seen_at=now,
        )
        db.add(device)
        await db.flush()
    else:
        if device.revoked:
            raise HTTPException(status_code=403, detail="Device revoked")
        device.app_version = app_version
        device.last_seen_at = now
    return device


async def _get_owned_session(
    db: AsyncSession, session_id: int, user: User
) -> StreamSession:
    session = await db.scalar(
        select(StreamSession).where(
            StreamSession.id == session_id, StreamSession.user_id == user.id
        )
    )
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.post(
    "/sessions",
    response_model=RenderSessionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_API))],
)
async def create_render_session(
    session_data: RenderSessionCreate,
    current_user: User = Depends(require_creator),
    db: AsyncSession = Depends(get_db),
):
    """Create a native render session and hand the renderer everything it needs."""
    device = await _check_device(
        db, current_user, session_data.device_id, session_data.app_version
    )

    project = await db.scalar(
        select(Project).where(
            Project.id == session_data.project_id,
            Project.organization_id == current_user.organization_id,
        )
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    if project.status != ProjectStatus.PUBLISHED:
        raise HTTPException(
            status_code=400, detail="Project must be published to render"
        )

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
                status_code=409, detail="A render session is already active"
            )

    now = datetime.now(timezone.utc)
    session = StreamSession(
        project_id=project.id,
        user_id=current_user.id,
        status=StreamSessionStatus.PENDING,
        device_id=device.device_id,
        started_at=now,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    from app.services.scene_packages import ScenePackageUnavailable

    try:
        scene_url = await get_latest_scene_package_url(db, project.id)
    except ScenePackageUnavailable as exc:
        # A session without a fetchable scene is a dead end for the renderer:
        # roll back and report storage failure instead of scene_url=null.
        await db.delete(session)
        await db.commit()
        raise HTTPException(
            status_code=503, detail="Scene package temporarily unavailable"
        ) from exc
    logger.info(
        "render_session_created",
        session_id=session.id,
        device_id=device.device_id,
        user_id=current_user.id,
        org_id=current_user.organization_id,
    )
    resp = RenderSessionResponse.model_validate(session)
    resp.scene_url = scene_url
    return resp


@router.post("/sessions/{session_id}/heartbeat")
async def render_heartbeat(
    session_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Renderer keep-alive. First heartbeat flips PENDING->ACTIVE (proof of live render).
    Sweeps the caller's stale sessions (>timeout, silent) to DISCONNECTED."""
    session = await _get_owned_session(db, session_id, current_user)
    now = datetime.now(timezone.utc)
    if session.status == StreamSessionStatus.PENDING:
        session.status = StreamSessionStatus.ACTIVE
    session.last_heartbeat_at = now

    cutoff = now.timestamp() - settings.RENDER_HEARTBEAT_TIMEOUT_SECONDS
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=timezone.utc)
    # Cutoff pushed into SQL: sessions never heartbeated (NULL) or silent
    # past the timeout. Bounded scan, no full-table Python filter.
    stale = (
        (
            await db.execute(
                select(StreamSession)
                .where(
                    StreamSession.user_id == current_user.id,
                    StreamSession.id != session_id,
                    StreamSession.status.in_(
                        [
                            StreamSessionStatus.PENDING,
                            StreamSessionStatus.CONNECTING,
                            StreamSessionStatus.ACTIVE,
                        ]
                    ),
                    (StreamSession.last_heartbeat_at.is_(None))
                    | (StreamSession.last_heartbeat_at < cutoff_dt),
                )
                .limit(100)
            )
        )
        .scalars()
        .all()
    )
    swept = 0
    for s in stale:
        s.status = StreamSessionStatus.DISCONNECTED
        s.ended_at = now
        swept += 1
    await db.commit()
    return {
        "session_id": session.id,
        "status": session.status.value,
        "swept_stale": swept,
    }


@router.post("/sessions/{session_id}/end")
async def end_render_session(
    session_id: int,
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    session = await _get_owned_session(db, session_id, current_user)
    session.status = StreamSessionStatus.DISCONNECTED
    session.ended_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info(
        "render_session_ended",
        session_id=session.id,
        user_id=current_user.id,
        org_id=current_user.organization_id,
    )
    return {"session_id": session.id, "status": session.status.value}


@router.post(
    "/sessions/{session_id}/voice/audio",
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_LLM))],
)
async def render_voice_audio(
    session_id: int,
    audio: UploadFile = File(...),
    language: str = Form(default="en"),
    current_user: User = Depends(require_viewer),
    db: AsyncSession = Depends(get_db),
):
    """Push-to-talk for the native renderer: multipart PCM/WAV -> STT ->
    copilot chat -> TTS. Returns transcript + spoken reply audio (base64)."""
    session = await _get_owned_session(db, session_id, current_user)

    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty audio")
    if len(raw) > settings.MAX_VOICE_AUDIO_BYTES:
        raise HTTPException(status_code=400, detail="Audio too large (2MB max)")
    if len(language) > settings.MAX_VOICE_LANGUAGE_LEN:
        raise HTTPException(status_code=400, detail="Invalid language")

    from app.models.voice_session import VoiceSession

    # STT + chat + TTS first: the VoiceSession row is only created after
    # the downstream calls succeed. Adding before left uncommitted/dead
    # rows when chat failed (and held the DB session across network I/O).
    try:
        client = _get_http_client()
        stt_resp = await client.post(
            f"{settings.LLM_ROUTER_URL}/v1/audio/transcriptions",
            json={"audio_data": base64.b64encode(raw).decode(), "language": language},
            headers=_router_headers(),
        )
        stt_resp.raise_for_status()
        transcript = stt_resp.json().get("text", "")
        if not transcript:
            return JSONResponse(
                status_code=502,
                content={
                    "transcript": "",
                    "response": "I didn't catch that.",
                    "audio_data": None,
                },
            )

        chat_resp = await client.post(
            f"{settings.LLM_ROUTER_URL}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": transcript}],
                "task_type": "copilot_chat",
                "sensitivity": "internal",
            },
            headers=_router_headers(),
        )
        chat_resp.raise_for_status()
        data = chat_resp.json()
        response_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )

        voice_session = VoiceSession(
            session_id=session.id,
            transcript=transcript,
            response_text=response_text,
        )
        db.add(voice_session)

        tts_audio: Any = None
        try:
            tts_resp = await client.post(
                f"{settings.LLM_ROUTER_URL}/v1/audio/speech",
                json={"text": response_text, "language": language},
                headers=_router_headers(),
            )
            tts_resp.raise_for_status()
            tts_audio = tts_resp.json().get("audio_data")
        except httpx.HTTPError as e:
            logger.warning(
                "render_tts_failed",
                session_id=session_id,
                user_id=current_user.id,
                org_id=current_user.organization_id,
                error=str(e),
            )

        await db.commit()
        return {
            "transcript": transcript,
            "response": response_text,
            "audio_data": tts_audio,
        }
    except httpx.ConnectError:
        logger.warning(
            "render_voice_unavailable",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
        )
        return JSONResponse(
            status_code=503,
            content={
                "transcript": "",
                "response": "Service temporarily unavailable.",
                "audio_data": None,
            },
        )
    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={
                "transcript": "",
                "response": "Service temporarily unavailable.",
                "audio_data": None,
            },
        )
    except httpx.HTTPStatusError as e:
        logger.warning(
            "render_voice_http_error",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
            status=e.response.status_code,
        )
        return JSONResponse(
            status_code=502,
            content={
                "transcript": "",
                "response": "Service temporarily unavailable.",
                "audio_data": None,
            },
        )

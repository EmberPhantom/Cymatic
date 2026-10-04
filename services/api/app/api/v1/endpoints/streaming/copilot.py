"""Copilot + voice endpoints (split, no logic change)."""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
)
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
import structlog
from app.core.config import get_settings
from app.core.dependencies import require_viewer
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.stream_session import StreamSession
from app.models.user import User

# Agent/HTTP helpers resolve via the streaming package namespace
# (app.api.v1.endpoints.streaming.*) so tests can monkeypatch them.
from app.api.v1.endpoints import streaming as _ns
from .common import CopilotMessage, VoiceTranscript

settings = get_settings()
logger = structlog.get_logger()

router = APIRouter()


@router.post(
    "/sessions/{session_id}/agent/message",
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_LLM))],
)
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
    from datetime import datetime, timezone

    # LLM call FIRST: the AgentAction row is only created after the
    # downstream chat succeeds. Committing before left dead rows on
    # 502/503/504.
    try:
        client = _ns._get_http_client()
        resp = await client.post(
            f"{settings.LLM_ROUTER_URL}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": message.message}],
                "task_type": "copilot_chat",
                "sensitivity": "internal",
            },
            headers=_ns._router_headers(),
            timeout=httpx.Timeout(
                settings.LLM_ROUTER_TIMEOUT_SECONDS,
                connect=settings.LLM_ROUTER_CONNECT_TIMEOUT_SECONDS,
            ),
        )
        resp.raise_for_status()
        data = resp.json()
        response_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
    except httpx.ConnectError:
        logger.warning(
            "copilot_llm_unavailable",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
        )
        return JSONResponse(
            status_code=503,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )
    except httpx.TimeoutException:
        logger.warning(
            "copilot_llm_timeout",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
        )
        return JSONResponse(
            status_code=504,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )
    except httpx.HTTPStatusError as e:
        logger.warning(
            "copilot_llm_http_error",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
            status=e.response.status_code,
        )
        return JSONResponse(
            status_code=502,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )
    except (ValueError, OSError) as e:
        logger.error(
            "copilot_llm_failed",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
            error=str(e),
        )
        return JSONResponse(
            status_code=500,
            content={"response": "Service temporarily unavailable.", "actions": []},
        )

    agent_action = AgentAction(
        session_id=session_id,
        action_type="copilot_message",
        payload_json={"message": message.message, "context": message.context},
        status="completed",
        completed_at=datetime.now(timezone.utc),
    )
    db.add(agent_action)
    await db.commit()
    return {
        "response": response_text,
        "actions": [],
        "provider": data.get("provider", "unknown"),
    }


@router.post(
    "/sessions/{session_id}/voice/transcript",
    dependencies=[Depends(rate_limit(settings.RATE_LIMIT_LLM))],
)
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

    # LLM call FIRST: the VoiceSession row is only created after the
    # downstream chat succeeds. Committing before left dead rows on
    # 502/503/504.
    try:
        client = _ns._get_http_client()
        resp = await client.post(
            f"{settings.LLM_ROUTER_URL}/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": transcript.transcript}],
                "task_type": "copilot_chat",
                "sensitivity": "internal",
            },
            headers=_ns._router_headers(),
            timeout=httpx.Timeout(
                settings.LLM_ROUTER_TIMEOUT_SECONDS,
                connect=settings.LLM_ROUTER_CONNECT_TIMEOUT_SECONDS,
            ),
        )
        resp.raise_for_status()
        data = resp.json()
        response_text = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
    except httpx.ConnectError:
        logger.warning(
            "voice_llm_unavailable",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
        )
        return JSONResponse(
            status_code=503,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )
    except httpx.TimeoutException:
        logger.warning(
            "voice_llm_timeout",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
        )
        return JSONResponse(
            status_code=504,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )
    except httpx.HTTPStatusError as e:
        logger.warning(
            "voice_llm_http_error",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
            status=e.response.status_code,
        )
        return JSONResponse(
            status_code=502,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )
    except (ValueError, OSError) as e:
        logger.error(
            "voice_llm_failed",
            session_id=session_id,
            user_id=current_user.id,
            org_id=current_user.organization_id,
            error=str(e),
        )
        return JSONResponse(
            status_code=500,
            content={
                "response": "I didn't catch that. Could you repeat?",
                "tts_audio_url": None,
            },
        )

    voice_session = VoiceSession(
        session_id=session_id,
        transcript=transcript.transcript,
        response_text=response_text,
    )
    db.add(voice_session)
    await db.commit()
    return {"response": response_text, "tts_audio_url": None}


# WebSocket signaling for WebRTC

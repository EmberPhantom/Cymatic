from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import hmac

import litellm
import structlog
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.core.config import get_settings
from app.core.rate_limit import rate_limit
from app.providers.litellm_client import (
    ChatCompletionRequest,
    EmbeddingRequest,
    STTRequest,
    TTSRequest,
    chat_completion,
    embedding,
    stt,
    tts,
)
from app.routing.cache import llm_cache
from app.routing.engine import routing_engine
from app.routing.usage import usage_tracker
from cymatic_shared.auth import configure_logging, verify_admin_key_dependency

logger = structlog.get_logger()
settings = get_settings()

litellm.set_verbose = settings.DEBUG
litellm.drop_params = True


configure_logging("llm-router", getattr(settings, "LOG_FORMAT", "json"))

verify_admin_key = verify_admin_key_dependency(lambda: settings.ADMIN_API_KEY or "")

_fallback_warned = False


def _extract_token(
    x_api_key: str | None, authorization: str | None
) -> str | None:
    if x_api_key:
        return x_api_key.strip()
    if authorization:
        auth = authorization.strip()
        return auth[7:].strip() if auth.lower().startswith("bearer ") else auth
    return None


async def verify_data_plane_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-Api-Key"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> None:
    """Data-plane auth: LLM_API_KEY, falling back to ADMIN_API_KEY.

    On success marks the request authenticated (and records which key
    plane was used) so downstream dependencies (e.g. rate limiting) can
    prefer server-verified identity over client-controlled headers.
    """
    global _fallback_warned
    data_key = settings.LLM_API_KEY or ""
    admin_key = settings.ADMIN_API_KEY or ""
    effective = data_key or admin_key
    if not data_key and admin_key and not _fallback_warned:
        logger.warning(
            "llm_api_key_fallback",
            detail="LLM_API_KEY unset; data-plane routes accept ADMIN_API_KEY. "
            "Set LLM_API_KEY to separate data and admin planes.",
        )
        _fallback_warned = True
    if not effective:
        raise HTTPException(status_code=503, detail="LLM API key not configured")
    token = _extract_token(x_api_key, authorization)
    if token is None or not hmac.compare_digest(token, effective):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    request.state.authenticated = True
    request.state.api_key_plane = "data" if data_key else "admin-fallback"


def _is_admin_request(request: Request) -> bool:
    """True when the request carries a valid admin key (never raises)."""
    admin_key = settings.ADMIN_API_KEY or ""
    if not admin_key:
        return False
    token = _extract_token(
        request.headers.get("X-Api-Key"), request.headers.get("Authorization")
    )
    if not token:
        return False
    return hmac.compare_digest(token, admin_key)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    await usage_tracker.connect()
    await llm_cache.connect()
    yield
    await usage_tracker.disconnect()
    await llm_cache.disconnect()


app = FastAPI(
    title="CYMATIC LLM Router",
    version="0.1.0",
    description="Centralized LLM access layer with routing policies",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check(request: Request) -> dict[str, Any]:
    # Public response carries no per-provider/per-key detail (provider
    # enablement and cloud-key booleans are admin-only).
    if not _is_admin_request(request):
        return {"status": "healthy", "service": "llm-router"}
    providers = {
        name: provider.enabled for name, provider in routing_engine.providers.items()
    }
    cloud_keys = {
        "groq": bool(settings.GROQ_API_KEY),
        "openrouter": bool(settings.OPENROUTER_API_KEY),
        "openai": bool(settings.OPENAI_API_KEY),
        "nim": bool(settings.NVIDIA_NIM_API_KEY),
        "sarvam": bool(settings.SARVAM_API_KEY),
        "apinex": bool(getattr(settings, "APINEX_API_KEY", "")),
    }
    local_enabled = bool(getattr(settings, "ENABLE_LOCAL_LLM", False))
    any_cloud = any(cloud_keys.values())
    hint = None
    if not local_enabled and not any_cloud:
        hint = (
            "No LLM provider configured. For offline LAN: "
            "docker compose --profile local up -d ollama && "
            "docker exec <ollama-ctr> ollama pull phi3:mini, then set "
            "ENABLE_LOCAL_LLM=true. For cloud: set APINEX_API_KEY, GROQ_API_KEY, or "
            "OPENROUTER_API_KEY."
        )
    return {
        "status": "healthy",
        "service": "llm-router",
        "providers": providers,
        "local_enabled": local_enabled,
        "cloud_keys_configured": cloud_keys,
        "hint": hint,
    }


@app.get("/metrics")
async def metrics(_admin: None = Depends(verify_admin_key)) -> PlainTextResponse:
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "CYMATIC LLM Router", "version": "0.1.0"}


@app.post(
    "/v1/chat/completions",
    dependencies=[
        Depends(verify_data_plane_key),
        Depends(rate_limit()),
    ],
)
async def chat_completions(request: ChatCompletionRequest) -> Any:
    try:
        return await chat_completion(request)
    except ValueError as e:
        logger.warning("chat_completion_bad_request", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException as e:
        # Pass through quota/rate limit errors
        raise e
    except (OSError, Exception) as e:
        logger.error("chat_completion_failed", error=str(e))
        local_enabled = bool(getattr(settings, "ENABLE_LOCAL_LLM", False))
        hint = "No LLM provider available. " + (
            "Ollama sidecar unreachable — start it with "
            "'docker compose --profile local up -d ollama' and pull "
            "'phi3:mini'."
            if local_enabled
            else "Set ENABLE_LOCAL_LLM=true with ollama profile, or set "
            "APINEX_API_KEY/GROQ_API_KEY/OPENROUTER_API_KEY."
        )
        raise HTTPException(
            status_code=502, detail=f"LLM provider request failed: {hint}"
        ) from e


@app.post(
    "/v1/embeddings",
    dependencies=[
        Depends(verify_data_plane_key),
        Depends(rate_limit()),
    ],
)
async def embeddings(request: EmbeddingRequest) -> Any:
    try:
        return await embedding(request)
    except ValueError as e:
        logger.warning("embedding_bad_request", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException as e:
        raise e
    except (OSError, Exception) as e:
        logger.error("embedding_failed", error=str(e))
        raise HTTPException(
            status_code=502, detail="LLM provider request failed"
        ) from e


@app.post(
    "/v1/audio/transcriptions",
    dependencies=[
        Depends(verify_data_plane_key),
        Depends(rate_limit()),
    ],
)
async def transcribe(request: STTRequest) -> Any:
    try:
        return await stt(request)
    except ValueError as e:
        logger.warning("stt_bad_request", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException as e:
        raise e
    except (OSError, Exception) as e:
        logger.error("stt_failed", error=str(e))
        raise HTTPException(
            status_code=502, detail="STT provider request failed"
        ) from e


@app.post(
    "/v1/audio/speech",
    dependencies=[
        Depends(verify_data_plane_key),
        Depends(rate_limit()),
    ],
)
async def speech(request: TTSRequest) -> Any:
    try:
        return await tts(request)
    except ValueError as e:
        logger.warning("tts_bad_request", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException as e:
        raise e
    except (OSError, Exception) as e:
        logger.error("tts_failed", error=str(e))
        raise HTTPException(
            status_code=502, detail="TTS provider request failed"
        ) from e


@app.get("/v1/router/providers")
async def list_providers(_admin: None = Depends(verify_admin_key)) -> dict[str, Any]:
    return {
        "providers": [
            {
                "name": name.value,
                "enabled": provider.enabled,
                "priority": provider.priority,
                "supported_tasks": [t.value for t in provider.supported_tasks],
                "supported_sensitivity": [
                    s.value for s in provider.supported_sensitivity
                ],
                "models": list(provider.models.keys()),
                "status": routing_engine.status[name].model_dump(),
            }
            for name, provider in routing_engine.providers.items()
        ]
    }


@app.get("/v1/router/policies")
async def list_policies(_admin: None = Depends(verify_admin_key)) -> dict[str, Any]:
    return {
        "policies": [
            {
                "task_type": key.split("_")[0],
                "sensitivity": key.split("_")[1] if "_" in key else "default",
                "preferred_profile": policy.preferred_profile,
                "fallback_profile": policy.fallback_profile,
                "allowed_providers": [p.value for p in policy.allowed_providers],
            }
            for key, policy in routing_engine.policies.items()
        ]
    }


@app.get("/v1/router/usage/stats")
async def get_usage_stats(
    days: int = 7, _admin: None = Depends(verify_admin_key)
) -> dict[str, Any]:
    # Clamp days to match usage tracker cap
    if days > 30:
        days = 30
    if days < 1:
        days = 1
    return await usage_tracker.get_usage_stats(days)


@app.get("/v1/router/usage/quota/{provider}")
async def get_quota(
    provider: str, _admin: None = Depends(verify_admin_key)
) -> dict[str, Any]:
    return await usage_tracker.get_quota_status(provider)


@app.get("/v1/router/cache/stats")
async def get_cache_stats(_admin: None = Depends(verify_admin_key)) -> dict[str, Any]:
    return await llm_cache.get_stats()


@app.post("/v1/router/cache/invalidate")
async def invalidate_cache(
    task_type: str | None = None,
    model: str | None = None,
    _admin: None = Depends(verify_admin_key),
) -> dict[str, int]:
    count = await llm_cache.invalidate(task_type, model)
    return {"invalidated": count}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)

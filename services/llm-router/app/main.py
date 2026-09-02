from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import litellm
from app.core.config import get_settings
from app.providers.litellm_client import (
    litellm_client, ChatCompletionRequest, EmbeddingRequest,
    STTRequest, TTSRequest, chat_completion, embedding, stt, tts
)
from app.routing.engine import routing_engine
from app.routing.usage import usage_tracker, UsageLog
from app.routing.cache import llm_cache
import structlog
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

logger = structlog.get_logger()
settings = get_settings()

litellm.set_verbose = settings.DEBUG
litellm.drop_params = True


def verify_admin_key(x_api_key: str = Header(None)):
    """Simple API key check for admin endpoints."""
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API key is not configured")
    if x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing admin API key")


@asynccontextmanager
async def lifespan(app: FastAPI):
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
async def health_check():
    return {
        "status": "healthy",
        "service": "llm-router",
        "providers": {name: provider.enabled for name, provider in routing_engine.providers.items()},
    }


@app.get("/metrics")
async def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {"name": "CYMATIC LLM Router", "version": "0.1.0"}


@app.post("/v1/chat/completions")
async def chat_completions(request: ChatCompletionRequest):
    try:
        return await chat_completion(request)
    except ValueError as e:
        logger.warning("chat_completion_bad_request", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except (OSError, HTTPException) as e:
        logger.error("chat_completion_failed", error=str(e))
        raise HTTPException(status_code=502, detail="LLM provider request failed")


@app.post("/v1/embeddings")
async def embeddings(request: EmbeddingRequest):
    try:
        return await embedding(request)
    except ValueError as e:
        logger.warning("embedding_bad_request", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except (OSError, HTTPException) as e:
        logger.error("embedding_failed", error=str(e))
        raise HTTPException(status_code=502, detail="LLM provider request failed")


@app.post("/v1/audio/transcriptions")
async def transcribe(request: STTRequest):
    try:
        return await stt(request)
    except (ValueError, OSError) as e:
        logger.error("stt_failed", error=str(e))
        raise HTTPException(status_code=502, detail="STT provider request failed")


@app.post("/v1/audio/speech")
async def speech(request: TTSRequest):
    try:
        return await tts(request)
    except (ValueError, OSError) as e:
        logger.error("tts_failed", error=str(e))
        raise HTTPException(status_code=502, detail="TTS provider request failed")


@app.get("/v1/router/providers")
async def list_providers(_admin: None = Depends(verify_admin_key)):
    return {
        "providers": [
            {
                "name": name.value,
                "enabled": provider.enabled,
                "priority": provider.priority,
                "supported_tasks": [t.value for t in provider.supported_tasks],
                "supported_sensitivity": [s.value for s in provider.supported_sensitivity],
                "models": list(provider.models.keys()),
                "status": routing_engine.status[name].model_dump(),
            }
            for name, provider in routing_engine.providers.items()
        ]
    }


@app.get("/v1/router/policies")
async def list_policies(_admin: None = Depends(verify_admin_key)):
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
async def get_usage_stats(days: int = 7, _admin: None = Depends(verify_admin_key)):
    return await usage_tracker.get_usage_stats(days)


@app.get("/v1/router/usage/quota/{provider}")
async def get_quota(provider: str, _admin: None = Depends(verify_admin_key)):
    return await usage_tracker.get_quota_status(provider)


@app.get("/v1/router/cache/stats")
async def get_cache_stats(_admin: None = Depends(verify_admin_key)):
    return await llm_cache.get_stats()


@app.post("/v1/router/cache/invalidate")
async def invalidate_cache(
    task_type: Optional[str] = None,
    model: Optional[str] = None,
    _admin: None = Depends(verify_admin_key),
):
    count = await llm_cache.invalidate(task_type, model)
    return {"invalidated": count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

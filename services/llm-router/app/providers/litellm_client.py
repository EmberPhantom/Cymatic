"""LiteLLM Client Wrapper for Provider Abstraction"""

import asyncio
import base64
import time
import uuid
from typing import Any

import litellm
import structlog
from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.providers.sanitize import (  # noqa: F401  (re-export for tests/callers)
    _MAX_MESSAGE_CHARS,
    _MAX_MESSAGES,
    _sanitize_messages,
    _sanitize_text,
)
from app.routing.cache import LLMCache, get_cached_response, set_cached_response
from app.routing.engine import routing_engine
from app.routing.usage import UsageTracker, log_llm_usage
from app.schemas.providers import ProviderName, SensitivityLevel, TaskType

logger = structlog.get_logger()
settings = get_settings()

# Configure LiteLLM
litellm.set_verbose = settings.DEBUG
litellm.drop_params = True  # Drop unsupported params

# Concurrency & size caps
_MAX_CONCURRENT_LLM = 50
# Clarification/intent are highly context-dependent (prompt-specific questions).
# Caching them on {domain, answers} alone leaks identical questions across
# different projects, so they bypass the cache entirely.
_NO_CACHE_TASKS = {"clarification", "intent_extraction"}
# Local Ollama SLM on 8GB CPU box: serialize to avoid OOM (phi-3-mini q4 ~2.3GB)
_MAX_CONCURRENT_LOCAL = 2
_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB decoded
_MAX_AUDIO_B64_CHARS = 35 * 1024 * 1024
_MAX_TTS_CHARS = 5000


class ChatCompletionRequest(BaseModel):
    messages: list[dict[str, str]]
    model: str | None = None
    task_type: TaskType = TaskType.COPILOT_CHAT
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    temperature: float = 0.7
    max_tokens: int | None = None
    top_p: float = 1.0
    stream: bool = False
    response_format: dict[str, Any] | None = None
    user_id: str | None = None
    organization_id: str | None = None
    project_id: str | None = None
    use_cache: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int]
    provider: str
    routed_model: str
    latency_ms: int
    cached: bool = False


class EmbeddingRequest(BaseModel):
    input: list[str]
    model: str | None = None
    task_type: TaskType = TaskType.EMBEDDING
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    user_id: str | None = None
    organization_id: str | None = None


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[dict[str, Any]]
    model: str
    usage: dict[str, int]
    provider: str
    latency_ms: int


class STTRequest(BaseModel):
    audio_data: str  # base64 encoded
    language: str = "en"
    model: str | None = None
    task_type: TaskType = TaskType.STT
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    user_id: str | None = None
    organization_id: str | None = None


class STTResponse(BaseModel):
    text: str
    language: str
    confidence: float
    provider: str
    model: str
    latency_ms: int


class TTSRequest(BaseModel):
    text: str
    language: str = "en"
    speaker: str = "anushka"
    model: str | None = None
    task_type: TaskType = TaskType.TTS
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    user_id: str | None = None
    organization_id: str | None = None


class TTSResponse(BaseModel):
    audio_data: str  # base64 encoded
    format: str = "wav"
    provider: str
    model: str
    latency_ms: int


class LiteLLMClient:
    """Wrapper around LiteLLM with routing, caching, and usage tracking."""

    def __init__(self) -> None:
        self.usage_tracker = UsageTracker()
        self.cache = LLMCache()
        self._semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LLM)
        self._local_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_LOCAL)

    @staticmethod
    def _is_local_provider(provider: ProviderName | str) -> bool:
        return (
            provider == ProviderName.LOCAL or str(provider) == ProviderName.LOCAL.value
        )

    @staticmethod
    def _is_apinex_provider(provider: ProviderName | str) -> bool:
        return (
            provider == ProviderName.APINEX
            or str(provider) == ProviderName.APINEX.value
            or str(provider) == "apinex"
        )

    def _semaphore_for(self, provider: ProviderName | str) -> asyncio.Semaphore:
        """CPU-bound local SLM gets its own small semaphore to avoid OOM."""
        if self._is_local_provider(provider):
            return self._local_semaphore
        return self._semaphore

    def _resolve_audio_route(
        self,
        task: TaskType,
        sensitivity: SensitivityLevel,
        model: str | None,
    ) -> tuple[str, ProviderName]:
        """Resolve STT/TTS model/provider with the same policy checks as chat.

        Explicit request.model values are allowlisted against registered
        provider models and must satisfy sensitivity support, enablement,
        and the task policy's allowed/blocked provider lists. Without an
        explicit model, routing goes through the policy engine (which
        denies sensitivities such as REGULATED that have no audio policy).
        """
        policy = routing_engine.get_policy(task, sensitivity)
        if model:
            found = self._find_provider_for_model(model)
            if not found:
                raise ValueError(f"Model {model} not found in any provider")
            cfg = routing_engine.providers.get(found)
            if cfg is None or sensitivity not in cfg.supported_sensitivity:
                raise ValueError(
                    f"Provider {found} does not support sensitivity {sensitivity}"
                )
            if not cfg.enabled:
                raise ValueError(f"Provider {found} is disabled")
            if found in policy.blocked_providers:
                raise ValueError(f"Provider {found} blocked for {sensitivity}")
            if policy.allowed_providers and found not in policy.allowed_providers:
                raise ValueError(f"Provider {found} not allowed for {task}")
            return model, found
        decision = routing_engine.route(task, sensitivity)
        return decision.model, decision.provider

    async def chat_completion(
        self, request: ChatCompletionRequest
    ) -> ChatCompletionResponse:
        """Execute chat completion with routing, caching, and fallbacks."""
        start_time = time.time()
        request_id = str(uuid.uuid4())

        # Sanitize messages early (prevents prompt injection)
        request.messages = _sanitize_messages(request.messages)
        # Size guard for messages
        total_chars = sum(len(str(m.get("content", ""))) for m in request.messages)
        if total_chars > 200000:
            raise ValueError("Prompt too large")

        # Determine model/provider with sensitivity validation
        model: str
        provider_name: ProviderName | str
        policy = routing_engine.get_policy(request.task_type, request.sensitivity)
        if not request.model:
            routing_decision = routing_engine.route(
                request.task_type, request.sensitivity
            )
            model = routing_decision.model
            provider_name = routing_decision.provider
        else:
            model = request.model
            found = self._find_provider_for_model(model)
            if not found:
                raise ValueError(f"Model {model} not found in any provider")
            provider_name = found
            # Explicit model sensitivity bypass fix: validate provider supports sensitivity
            cfg = routing_engine.providers.get(provider_name)
            if cfg is None or request.sensitivity not in cfg.supported_sensitivity:
                raise ValueError(
                    f"Provider {provider_name} does not support sensitivity {request.sensitivity}"
                )
            if not cfg.enabled:
                raise ValueError(f"Provider {provider_name} is disabled")
            # Check blocked providers per policy
            if provider_name in policy.blocked_providers:
                raise ValueError(
                    f"Provider {provider_name} blocked for {request.sensitivity}"
                )
            # Check allowed providers per policy
            if (
                policy.allowed_providers
                and provider_name not in policy.allowed_providers
            ):
                raise ValueError(
                    f"Provider {provider_name} not allowed for {request.task_type}"
                )

        provider_str = (
            provider_name.value
            if isinstance(provider_name, ProviderName)
            else str(provider_name)
        )

        # Pre-flight quota check (Redis)
        estimated_tokens = self._estimate_chat_tokens(
            request.messages, request.max_tokens
        )
        # Fix tpm never trip for STT/TTS not applicable here, but ensure at least 100
        estimated_tokens = max(estimated_tokens, 100)
        try:
            allowed = await self.usage_tracker.check_quota(
                provider_str, estimated_tokens
            )
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail=f"Quota exceeded for provider {provider_str}",
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("quota_check_failed", error=str(e))
            # Fail-closed: an unavailable quota backend must deny, not allow.
            raise HTTPException(
                status_code=429,
                detail=f"Quota check unavailable for provider {provider_str}",
            ) from e

        # Check cache first (isolated via sensitivity/provider/org)
        task_value = (
            request.task_type.value
            if hasattr(request.task_type, "value")
            else str(request.task_type)
        )
        if (
            request.use_cache
            and not request.stream
            and task_value not in _NO_CACHE_TASKS
        ):
            # Do not cache tenant-sensitive/regulated to avoid leak
            should_cache = request.sensitivity in (
                SensitivityLevel.PUBLIC,
                SensitivityLevel.INTERNAL,
            )
            if should_cache:
                cache_key_prompt = self._messages_to_prompt(request.messages)
                cached = await get_cached_response(
                    request.task_type.value,
                    model,
                    cache_key_prompt,
                    {
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                        "response_format": request.response_format,
                    },
                    sensitivity=request.sensitivity.value,
                    provider=provider_str,
                    organization_id=request.organization_id,
                )
                if cached:
                    latency_ms = int((time.time() - start_time) * 1000)
                    logger.info("cache_hit", request_id=request_id, model=model)
                    cached_choices: list[dict[str, Any]] = cached.get("choices", [])
                    cached_usage: dict[str, int] = cached.get("usage", {})
                    return ChatCompletionResponse(
                        id=request_id,
                        created=int(time.time()),
                        model=model,
                        choices=cached_choices,
                        usage=cached_usage,
                        provider="cache",
                        routed_model="cached",
                        latency_ms=latency_ms,
                        cached=True,
                    )

        # Prepare LiteLLM params with sanitized messages
        params: dict[str, Any] = {
            "model": self._to_litellm_model(provider_name, model),
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": request.stream,
        }

        if self._is_local_provider(provider_name):
            # Route to the Ollama sidecar instead of a cloud endpoint.
            # getattr keeps this working before OLLAMA_URL lands in Settings (W1.5).
            params["api_base"] = getattr(settings, "OLLAMA_URL", "http://ollama:11434")
        elif self._is_apinex_provider(provider_name):
            # Route to APInex OpenAI-compatible multi-model gateway
            params["api_base"] = getattr(
                settings, "APINEX_BASE_URL", "https://api.apinex.bond/v1"
            )
            params["api_key"] = getattr(settings, "APINEX_API_KEY", "")

        if request.response_format:
            params["response_format"] = request.response_format

        # Execute with retries respecting policy max_retries
        max_retries = policy.max_retries
        last_error: Exception | None = None

        # Streaming contract: streaming responses are not cached and not retried via fallback same way
        if request.stream:
            # Streaming – single attempt, concurrency guarded
            async with self._semaphore_for(provider_name):
                try:
                    return await self._stream_completion(params, model, provider_str)
                except Exception as e:
                    logger.error("stream_failed", error=str(e))
                    raise

        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    "llm_request",
                    request_id=request_id,
                    model=model,
                    provider=provider_str,
                    attempt=attempt,
                )

                async with self._semaphore_for(provider_name):
                    response_any: Any = await litellm.acompletion(**params)

                # Extract usage
                usage_obj = getattr(response_any, "usage", None)
                if usage_obj is not None:
                    prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                    completion_tokens = int(
                        getattr(usage_obj, "completion_tokens", 0) or 0
                    )
                    total_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0)
                else:
                    prompt_tokens = 0
                    completion_tokens = 0
                    total_tokens = 0
                usage: dict[str, int] = {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }

                latency_ms = int((time.time() - start_time) * 1000)

                # Log usage
                await log_llm_usage(
                    task_type=request.task_type.value,
                    provider=provider_str,
                    model=model,
                    sensitivity=request.sensitivity.value,
                    prompt_tokens=usage["prompt_tokens"],
                    completion_tokens=usage["completion_tokens"],
                    latency_ms=latency_ms,
                    status="success",
                    user_id=request.user_id,
                    organization_id=request.organization_id,
                    project_id=request.project_id,
                )

                # Record success for circuit breaker
                routing_engine.record_provider_result(
                    provider_str, True, float(latency_ms)
                )

                # Cache successful response – tenant isolation via sensitivity/provider/org
                # Skip context-sensitive planning tasks (see _NO_CACHE_TASKS).
                if request.use_cache and task_value not in _NO_CACHE_TASKS:
                    # Only cache for non-sensitive to prevent leak
                    if request.sensitivity in (
                        SensitivityLevel.PUBLIC,
                        SensitivityLevel.INTERNAL,
                    ):
                        cache_key_prompt = self._messages_to_prompt(request.messages)
                        choices_raw: Any = getattr(response_any, "choices", [])
                        choices_list: list[dict[str, Any]] = []
                        for c in choices_raw:
                            if hasattr(c, "model_dump"):
                                choices_list.append(c.model_dump())  # type: ignore
                            elif isinstance(c, dict):
                                choices_list.append(c)
                            else:
                                try:
                                    choices_list.append(dict(c))  # type: ignore
                                except Exception:
                                    choices_list.append({"content": str(c)})
                        await set_cached_response(
                            request.task_type.value,
                            model,
                            cache_key_prompt,
                            {
                                "choices": choices_list,
                                "usage": usage,
                            },
                            {
                                "temperature": request.temperature,
                                "max_tokens": request.max_tokens,
                                "response_format": request.response_format,
                            },
                            sensitivity=request.sensitivity.value,
                            provider=provider_str,
                            organization_id=request.organization_id,
                        )

                # Normalize choices for response
                choices_raw2: Any = getattr(response_any, "choices", [])
                final_choices: list[dict[str, Any]] = []
                for c in choices_raw2:
                    if hasattr(c, "model_dump"):
                        final_choices.append(c.model_dump())  # type: ignore
                    elif isinstance(c, dict):
                        final_choices.append(c)
                    else:
                        try:
                            final_choices.append(dict(c))  # type: ignore
                        except Exception:
                            final_choices.append({"content": str(c)})

                return ChatCompletionResponse(
                    id=request_id,
                    created=int(time.time()),
                    model=model,
                    choices=final_choices,
                    usage=usage,
                    provider=provider_str,
                    routed_model=model,
                    latency_ms=latency_ms,
                )

            except Exception as e:
                # P0-1: litellm raises APIConnectionError/BadRequestError/
                # RateLimitError/Timeout etc., none of which subclass
                # (ValueError, OSError). Catching only those bypassed
                # policy.max_retries fallback rotation and surfaced 502
                # whenever Ollama was down or a key was missing.
                # Do not swallow quota 429 — propagate immediately.
                if isinstance(e, HTTPException) and e.status_code == 429:
                    raise
                last_error = e
                latency_ms = int((time.time() - start_time) * 1000)

                logger.warning(
                    "llm_request_failed",
                    request_id=request_id,
                    model=model,
                    provider=provider_str,
                    attempt=attempt,
                    error=str(e),
                )

                await log_llm_usage(
                    task_type=request.task_type.value,
                    provider=provider_str,
                    model=model,
                    sensitivity=request.sensitivity.value,
                    prompt_tokens=0,
                    completion_tokens=0,
                    latency_ms=latency_ms,
                    status="error",
                    error_message=str(e),
                    user_id=request.user_id,
                    organization_id=request.organization_id,
                    project_id=request.project_id,
                )

                routing_engine.record_provider_result(
                    provider_str, False, float(latency_ms)
                )

                if attempt < max_retries:
                    routing_decision = routing_engine.route(
                        request.task_type, request.sensitivity
                    )
                    # Fallback should not reuse same provider; ensure we rotate
                    candidate = routing_decision.fallback or routing_decision.provider
                    if candidate != provider_name:
                        provider_name = candidate
                        provider_str = (
                            provider_name.value
                            if isinstance(provider_name, ProviderName)
                            else str(provider_name)
                        )
                        model = routing_decision.model
                        params["model"] = self._to_litellm_model(provider_name, model)
                        if self._is_local_provider(provider_name):
                            params["api_base"] = getattr(
                                settings, "OLLAMA_URL", "http://ollama:11434"
                            )
                            params.pop("api_key", None)
                        elif self._is_apinex_provider(provider_name):
                            params["api_base"] = getattr(
                                settings,
                                "APINEX_BASE_URL",
                                "https://api.apinex.bond/v1",
                            )
                            params["api_key"] = getattr(settings, "APINEX_API_KEY", "")
                        else:
                            params.pop("api_base", None)
                            params.pop("api_key", None)
                        # Re-check quota for fallback provider (fail-closed)
                        try:
                            allowed_fb = await self.usage_tracker.check_quota(
                                provider_str, estimated_tokens
                            )
                            if not allowed_fb:
                                logger.warning(
                                    "fallback_quota_exceeded", provider=provider_str
                                )
                                continue
                        except HTTPException:
                            raise
                        except Exception as e:
                            logger.warning(
                                "fallback_quota_check_failed",
                                provider=provider_str,
                                error=str(e),
                            )
                            raise HTTPException(
                                status_code=429,
                                detail="Quota check unavailable "
                                f"for provider {provider_str}",
                            ) from e
                        continue

                if attempt == max_retries:
                    raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("chat_completion failed without exception")

    async def _stream_completion(
        self, params: dict[str, Any], model: str, provider: str
    ) -> ChatCompletionResponse:
        """Handle streaming completion — accumulates chunks into a final response (non-cached)."""
        request_id = str(uuid.uuid4())
        start_time = time.time()

        collected_choices: list[dict[str, Any]] = []
        total_usage: dict[str, int] = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

        try:
            # Ensure stream flag
            params = {**params, "stream": True}
            stream: Any = await litellm.acompletion(**params)
            async for chunk in stream:
                chunk_any: Any = chunk
                if getattr(chunk_any, "choices", None):
                    for choice_delta in chunk_any.choices:
                        delta_obj = getattr(choice_delta, "delta", None)
                        if delta_obj is not None and hasattr(delta_obj, "model_dump"):
                            delta_dict = delta_obj.model_dump()  # type: ignore
                        elif delta_obj is not None and hasattr(delta_obj, "__dict__"):
                            delta_dict = dict(delta_obj.__dict__)
                        else:
                            delta_dict = {}
                        collected_choices.append(
                            {
                                "index": getattr(choice_delta, "index", 0),
                                "delta": delta_dict,
                                "finish_reason": getattr(
                                    choice_delta, "finish_reason", None
                                ),
                            }
                        )
                usage_obj = getattr(chunk_any, "usage", None)
                if usage_obj:
                    total_usage["prompt_tokens"] = int(
                        getattr(usage_obj, "prompt_tokens", 0) or 0
                    )
                    total_usage["completion_tokens"] = int(
                        getattr(usage_obj, "completion_tokens", 0) or 0
                    )
                    total_usage["total_tokens"] = (
                        total_usage["prompt_tokens"] + total_usage["completion_tokens"]
                    )
        except Exception as e:
            if isinstance(e, HTTPException):
                raise HTTPException(
                    status_code=502, detail=f"Streaming failed: {e}"
                ) from e
            logger.warning("stream_completion_chunk_error", error=str(e))
            raise HTTPException(status_code=502, detail=f"Streaming failed: {e}") from e

        latency_ms = int((time.time() - start_time) * 1000)
        routing_engine.record_provider_result(provider, True, float(latency_ms))

        return ChatCompletionResponse(
            id=request_id,
            created=int(time.time()),
            model=model,
            choices=collected_choices,
            usage=total_usage,
            provider=provider,
            routed_model=model,
            latency_ms=latency_ms,
        )

    async def embedding(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Generate embeddings with sensitivity validation, quota and concurrency."""
        start_time = time.time()
        _request_id = str(uuid.uuid4())

        # Sanitize inputs
        sanitized_inputs = [_sanitize_text(t, max_len=10000) for t in request.input]
        if not sanitized_inputs:
            raise ValueError("Embedding input empty")
        if len(sanitized_inputs) > 100:
            raise ValueError("Too many embedding inputs")
        request.input = sanitized_inputs

        model: str
        provider_name: ProviderName | str | None
        policy = routing_engine.get_policy(TaskType.EMBEDDING, request.sensitivity)
        if not request.model:
            routing_decision = routing_engine.route(
                TaskType.EMBEDDING, request.sensitivity
            )
            model = routing_decision.model
            provider_name = routing_decision.provider
        else:
            model = request.model
            provider_name = self._find_provider_for_model(model)
            if provider_name is None:
                raise ValueError(f"Model {model} not found in any provider")
            cfg = routing_engine.providers.get(provider_name)
            if cfg is None or request.sensitivity not in cfg.supported_sensitivity:
                raise ValueError(
                    f"Provider {provider_name} does not support sensitivity {request.sensitivity}"
                )
            if provider_name in policy.blocked_providers:
                raise ValueError(
                    f"Provider {provider_name} blocked for {request.sensitivity}"
                )

        assert provider_name is not None
        provider_str = (
            provider_name.value
            if isinstance(provider_name, ProviderName)
            else str(provider_name)
        )

        # Pre-flight quota (estimate tokens as sum len//4)
        est_tokens = sum(len(t) // 4 for t in request.input) + 10
        allowed = await self.usage_tracker.check_quota(
            provider_str, max(est_tokens, 100)
        )
        if not allowed:
            raise HTTPException(
                status_code=429, detail=f"Quota exceeded for provider {provider_str}"
            )

        try:
            async with self._semaphore:
                response_any: Any = await litellm.aembedding(
                    model=self._to_litellm_model(provider_name, model),
                    input=request.input,
                )

            usage_obj = getattr(response_any, "usage", None)
            if usage_obj is not None:
                prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                total_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0)
            else:
                prompt_tokens = est_tokens
                total_tokens = est_tokens
            usage: dict[str, int] = {
                "prompt_tokens": prompt_tokens,
                "total_tokens": total_tokens,
            }

            latency_ms = int((time.time() - start_time) * 1000)

            await log_llm_usage(
                task_type=TaskType.EMBEDDING.value,
                provider=provider_str,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=0,
                latency_ms=latency_ms,
                status="success",
                user_id=request.user_id,
                organization_id=request.organization_id,
            )

            routing_engine.record_provider_result(provider_str, True, float(latency_ms))

            data_list: list[dict[str, Any]] = []
            resp_data: Any = getattr(response_any, "data", [])
            for i, d in enumerate(resp_data):
                emb = getattr(d, "embedding", None)
                if emb is None and isinstance(d, dict):
                    emb = d.get("embedding")
                data_list.append({"embedding": emb, "index": i})

            return EmbeddingResponse(
                data=data_list,
                model=model,
                usage=usage,
                provider=provider_str,
                latency_ms=latency_ms,
            )

        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            latency_ms = int((time.time() - start_time) * 1000)
            await log_llm_usage(
                task_type=TaskType.EMBEDDING.value,
                provider=provider_str,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="error",
                error_message=str(e),
                user_id=request.user_id,
                organization_id=request.organization_id,
            )
            routing_engine.record_provider_result(
                provider_str, False, float(latency_ms)
            )
            raise

    async def stt(self, request: STTRequest) -> STTResponse:
        """Speech-to-text transcription with size caps, quota and sanitization."""
        start_time = time.time()

        # Size caps
        if len(request.audio_data) > _MAX_AUDIO_B64_CHARS:
            raise ValueError("Audio data too large")
        try:
            audio_bytes = base64.b64decode(request.audio_data, validate=True)
        except Exception as e:
            raise ValueError("Invalid base64 audio_data") from e
        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            raise ValueError(
                f"Decoded audio too large: {len(audio_bytes)} > {_MAX_AUDIO_BYTES}"
            )
        if len(audio_bytes) == 0:
            raise ValueError("Empty audio")

        model, provider_name = self._resolve_audio_route(
            TaskType.STT, request.sensitivity, request.model
        )
        provider_str = (
            provider_name.value
            if isinstance(provider_name, ProviderName)
            else str(provider_name)
        )

        # Quota check – STT tokens estimated as 150 per request
        est_tokens = 150
        allowed = await self.usage_tracker.check_quota(provider_str, est_tokens)
        if not allowed:
            raise HTTPException(
                status_code=429, detail=f"Quota exceeded for provider {provider_str}"
            )

        try:
            async with self._semaphore:
                response_any: Any = await litellm.atranscription(
                    model=model,
                    file=("audio.wav", audio_bytes, "audio/wav"),
                    language=request.language,
                )

            latency_ms = int((time.time() - start_time) * 1000)

            await log_llm_usage(
                task_type=TaskType.STT.value,
                provider=provider_str,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="success",
                user_id=request.user_id,
                organization_id=request.organization_id,
            )

            routing_engine.record_provider_result(provider_str, True, float(latency_ms))

            text_val: str = str(getattr(response_any, "text", ""))
            text_val = _sanitize_text(text_val, max_len=20000)
            return STTResponse(
                text=text_val,
                language=request.language,
                confidence=1.0,
                provider=provider_str,
                model=model,
                latency_ms=latency_ms,
            )

        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            latency_ms = int((time.time() - start_time) * 1000)
            await log_llm_usage(
                task_type=TaskType.STT.value,
                provider=provider_str,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="error",
                error_message=str(e),
                user_id=request.user_id,
                organization_id=request.organization_id,
            )
            routing_engine.record_provider_result(
                provider_str, False, float(latency_ms)
            )
            raise

    async def tts(self, request: TTSRequest) -> TTSResponse:
        """Text-to-speech synthesis with size caps."""
        start_time = time.time()

        # Size caps before sanitization truncation
        if not request.text or len(request.text.strip()) == 0:
            raise ValueError("TTS text empty")
        if len(request.text) > _MAX_TTS_CHARS:
            raise ValueError(
                f"TTS text too long: {len(request.text)} > {_MAX_TTS_CHARS}"
            )
        request.text = _sanitize_text(request.text, max_len=_MAX_TTS_CHARS)

        model, provider_name = self._resolve_audio_route(
            TaskType.TTS, request.sensitivity, request.model
        )
        provider_str = (
            provider_name.value
            if isinstance(provider_name, ProviderName)
            else str(provider_name)
        )

        est_tokens = max(10, len(request.text) // 4)
        allowed = await self.usage_tracker.check_quota(provider_str, est_tokens)
        if not allowed:
            raise HTTPException(
                status_code=429, detail=f"Quota exceeded for provider {provider_str}"
            )

        try:
            async with self._semaphore:
                response_any: Any = await litellm.aspeech(
                    model=model,
                    input=request.text,
                    voice=request.speaker,
                    response_format="wav",
                )

            content = getattr(response_any, "content", b"")
            if isinstance(content, str):
                content_bytes = content.encode()
            else:
                content_bytes = bytes(content) if content is not None else b""
            if len(content_bytes) > _MAX_AUDIO_BYTES:
                raise ValueError("TTS response audio too large")
            audio_b64 = base64.b64encode(content_bytes).decode()

            latency_ms = int((time.time() - start_time) * 1000)

            await log_llm_usage(
                task_type=TaskType.TTS.value,
                provider=provider_str,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="success",
                user_id=request.user_id,
                organization_id=request.organization_id,
            )

            routing_engine.record_provider_result(provider_str, True, float(latency_ms))

            return TTSResponse(
                audio_data=audio_b64,
                format="wav",
                provider=provider_str,
                model=model,
                latency_ms=latency_ms,
            )

        except Exception as e:
            if isinstance(e, HTTPException):
                raise
            latency_ms = int((time.time() - start_time) * 1000)
            await log_llm_usage(
                task_type=TaskType.TTS.value,
                provider=provider_str,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="error",
                error_message=str(e),
                user_id=request.user_id,
                organization_id=request.organization_id,
            )
            routing_engine.record_provider_result(
                provider_str, False, float(latency_ms)
            )
            raise

    def _estimate_chat_tokens(
        self, messages: list[dict[str, str]], max_tokens: int | None
    ) -> int:
        chars = sum(len(str(m.get("content", ""))) for m in messages)
        prompt_est = max(10, chars // 4)
        if max_tokens:
            return prompt_est + max_tokens
        return prompt_est + 500

    def _messages_to_prompt(self, messages: list[dict[str, str]]) -> str:
        """Convert messages to single prompt string for caching (KeyError-safe)."""
        parts: list[str] = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            parts.append(f"{role}: {content}")
        return "\n".join(parts)

    @staticmethod
    def _to_litellm_model(provider: ProviderName | str, model: str) -> str:
        """Prefix model with litellm provider slug, dedup if already prefixed.

        LOCAL (Ollama) models resolve to `ollama/<ollama_model>` using the
        `ollama_model` metadata on the ModelProfile (e.g. `phi3:mini`),
        falling back to the internal model id.
        """
        if provider is None:
            return model
        provider_val = (
            provider.value if isinstance(provider, ProviderName) else str(provider)
        )
        if provider_val == ProviderName.LOCAL.value:
            ollama_model = model
            try:
                local_cfg = routing_engine.providers.get(ProviderName.LOCAL)
                if local_cfg is not None:
                    profile = local_cfg.models.get(model)
                    if profile is not None:
                        ollama_model = str(profile.metadata.get("ollama_model", model))
            except Exception:
                pass
            if ollama_model.startswith("ollama/"):
                return ollama_model
            return f"ollama/{ollama_model}"
        if provider_val == ProviderName.APINEX.value or provider_val == "apinex":
            clean_model = model
            if clean_model.startswith("apinex/"):
                clean_model = clean_model[len("apinex/") :]
            if clean_model.startswith("openai/"):
                return clean_model
            return f"openai/{clean_model}"
        # Dedup: if model already starts with provider_val/
        if model.startswith(f"{provider_val}/"):
            return model
        return f"{provider_val}/{model}"

    def _find_provider_for_model(self, model: str) -> ProviderName | None:
        """Find which provider has the given model."""
        for provider_name, provider in routing_engine.providers.items():
            if model in provider.models:
                return provider_name
        return None


# Global client instance
litellm_client = LiteLLMClient()


async def chat_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    return await litellm_client.chat_completion(request)


async def embedding(request: EmbeddingRequest) -> EmbeddingResponse:
    return await litellm_client.embedding(request)


async def stt(request: STTRequest) -> STTResponse:
    return await litellm_client.stt(request)


async def tts(request: TTSRequest) -> TTSResponse:
    return await litellm_client.tts(request)

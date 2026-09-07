"""LiteLLM Client Wrapper for Provider Abstraction"""
import asyncio
import base64
import time
import uuid
from typing import Any

import litellm
import structlog
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.routing.cache import LLMCache, get_cached_response, set_cached_response
from app.routing.engine import routing_engine
from app.routing.usage import UsageTracker, log_llm_usage
from app.schemas.providers import ProviderName, SensitivityLevel, TaskType

logger = structlog.get_logger()
settings = get_settings()


# Configure LiteLLM
litellm.set_verbose = settings.DEBUG
litellm.drop_params = True  # Drop unsupported params


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

    async def chat_completion(self, request: ChatCompletionRequest) -> ChatCompletionResponse:
        """Execute chat completion with routing, caching, and fallbacks."""
        start_time = time.time()
        request_id = str(uuid.uuid4())

        # Check cache first
        if request.use_cache and not request.stream:
            cache_key_prompt = self._messages_to_prompt(request.messages)
            cached = await get_cached_response(
                request.task_type.value,
                request.model or "auto",
                cache_key_prompt,
                {
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "response_format": request.response_format,
                },
            )
            if cached:
                latency_ms = int((time.time() - start_time) * 1000)
                logger.info("cache_hit", request_id=request_id, model=request.model)
                cached_choices: list[dict[str, Any]] = cached.get("choices", [])
                cached_usage: dict[str, int] = cached.get("usage", {})
                return ChatCompletionResponse(
                    id=request_id,
                    created=int(time.time()),
                    model=request.model or "cached",
                    choices=cached_choices,
                    usage=cached_usage,
                    provider="cache",
                    routed_model="cached",
                    latency_ms=latency_ms,
                    cached=True,
                )

        # Determine model if not specified
        model: str
        provider_name: ProviderName | str
        if not request.model:
            routing_decision = routing_engine.route(request.task_type, request.sensitivity)
            model = routing_decision.model
            provider_name = routing_decision.provider
        else:
            model = request.model
            found = self._find_provider_for_model(model)
            if not found:
                raise ValueError(f"Model {model} not found in any provider")
            provider_name = found

        # Prepare LiteLLM params
        params: dict[str, Any] = {
            "model": self._to_litellm_model(provider_name, model),
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "top_p": request.top_p,
            "stream": request.stream,
        }

        if request.response_format:
            params["response_format"] = request.response_format

        # Execute with retries
        max_retries = 2
        last_error: Exception | None = None
        provider_str = provider_name.value if isinstance(provider_name, ProviderName) else str(provider_name)

        for attempt in range(max_retries + 1):
            try:
                logger.info(
                    "llm_request", request_id=request_id, model=model, provider=provider_str, attempt=attempt
                )

                if request.stream:
                    # Streaming not cached
                    response = await self._stream_completion(params, model, provider_str)
                    return response
                else:
                    response_any: Any = await litellm.acompletion(**params)

                    # Extract usage
                    usage_obj = getattr(response_any, "usage", None)
                    if usage_obj is not None:
                        prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                        completion_tokens = int(getattr(usage_obj, "completion_tokens", 0) or 0)
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
                    routing_engine.record_provider_result(provider_str, True, float(latency_ms))

                    # Cache successful response
                    if request.use_cache:
                        cache_key_prompt = self._messages_to_prompt(request.messages)
                        # Normalize choices to dicts
                        choices_raw: Any = getattr(response_any, "choices", [])
                        choices_list: list[dict[str, Any]] = []
                        for c in choices_raw:
                            if hasattr(c, "model_dump"):
                                choices_list.append(c.model_dump())
                            elif isinstance(c, dict):
                                choices_list.append(c)
                            else:
                                choices_list.append(dict(c))
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
                        )

                    # Normalize choices for response
                    choices_raw2: Any = getattr(response_any, "choices", [])
                    final_choices: list[dict[str, Any]] = []
                    for c in choices_raw2:
                        if hasattr(c, "model_dump"):
                            final_choices.append(c.model_dump())
                        elif isinstance(c, dict):
                            final_choices.append(c)
                        else:
                            final_choices.append(dict(c))

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

            except (ValueError, OSError) as e:
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

                routing_engine.record_provider_result(provider_str, False, float(latency_ms))

                if attempt < max_retries:
                    routing_decision = routing_engine.route(request.task_type, request.sensitivity)
                    if routing_decision.fallback and routing_decision.fallback != provider_name:
                        provider_name = routing_decision.fallback
                        provider_str = (
                            provider_name.value
                            if isinstance(provider_name, ProviderName)
                            else str(provider_name)
                        )
                        model = routing_decision.model
                        params["model"] = self._to_litellm_model(provider_name, model)
                        continue

                if attempt == max_retries:
                    raise

        if last_error is not None:
            raise last_error
        raise RuntimeError("chat_completion failed without exception")

    async def _stream_completion(
        self, params: dict[str, Any], model: str, provider: str
    ) -> ChatCompletionResponse:
        """Handle streaming completion — accumulates chunks into a final response."""
        request_id = str(uuid.uuid4())
        start_time = time.time()

        collected_choices: list[dict[str, Any]] = []
        total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        try:
            stream: Any = await litellm.acompletion(**params, stream=True)
            async for chunk in stream:
                chunk_any: Any = chunk
                if getattr(chunk_any, "choices", None):
                    for choice_delta in chunk_any.choices:
                        delta_obj = getattr(choice_delta, "delta", None)
                        if delta_obj is not None and hasattr(delta_obj, "model_dump"):
                            delta_dict = delta_obj.model_dump()
                        elif delta_obj is not None and hasattr(delta_obj, "__dict__"):
                            delta_dict = dict(delta_obj.__dict__)
                        else:
                            delta_dict = {}
                        collected_choices.append(
                            {
                                "index": getattr(choice_delta, "index", 0),
                                "delta": delta_dict,
                                "finish_reason": getattr(choice_delta, "finish_reason", None),
                            }
                        )
                usage_obj = getattr(chunk_any, "usage", None)
                if usage_obj:
                    total_usage["prompt_tokens"] = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                    total_usage["completion_tokens"] = int(getattr(usage_obj, "completion_tokens", 0) or 0)
                    total_usage["total_tokens"] = (
                        total_usage["prompt_tokens"] + total_usage["completion_tokens"]
                    )
        except (ValueError, KeyError, asyncio.TimeoutError) as e:
            logger.warning("stream_completion_chunk_error", error=str(e))

        latency_ms = int((time.time() - start_time) * 1000)

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
        """Generate embeddings."""
        start_time = time.time()
        _request_id = str(uuid.uuid4())

        model: str
        provider_name: ProviderName | str | None
        if not request.model:
            routing_decision = routing_engine.route(TaskType.EMBEDDING, request.sensitivity)
            model = routing_decision.model
            provider_name = routing_decision.provider
        else:
            model = request.model
            provider_name = self._find_provider_for_model(model)
            if provider_name is None:
                raise ValueError(f"Model {model} not found in any provider")

        provider_str = (
            provider_name.value if isinstance(provider_name, ProviderName) else str(provider_name)
        )

        try:
            response_any: Any = await litellm.aembedding(
                model=self._to_litellm_model(provider_name, model),
                input=request.input,
            )

            usage_obj = getattr(response_any, "usage", None)
            if usage_obj is not None:
                prompt_tokens = int(getattr(usage_obj, "prompt_tokens", 0) or 0)
                total_tokens = int(getattr(usage_obj, "total_tokens", 0) or 0)
            else:
                prompt_tokens = 0
                total_tokens = 0
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

            # Record success for circuit breaker
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

        except (ValueError, OSError) as e:
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

            # Record failure for circuit breaker
            routing_engine.record_provider_result(provider_str, False, float(latency_ms))
            raise

    async def stt(self, request: STTRequest) -> STTResponse:
        """Speech-to-text transcription."""
        start_time = time.time()
        _request_id = str(uuid.uuid4())

        model = request.model or "saarika:v2"
        provider_name = ProviderName.SARVAM

        audio_bytes = base64.b64decode(request.audio_data)

        try:
            # Sarvam STT
            response_any: Any = await litellm.atranscription(
                model=model,
                file=("audio.wav", audio_bytes, "audio/wav"),
                language=request.language,
            )

            latency_ms = int((time.time() - start_time) * 1000)

            await log_llm_usage(
                task_type=TaskType.STT.value,
                provider=provider_name.value,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="success",
                user_id=request.user_id,
                organization_id=request.organization_id,
            )

            # Record success for circuit breaker
            routing_engine.record_provider_result(provider_name.value, True, float(latency_ms))

            text_val: str = str(getattr(response_any, "text", ""))
            return STTResponse(
                text=text_val,
                language=request.language,
                confidence=1.0,  # Sarvam doesn't return confidence
                provider=provider_name.value,
                model=model,
                latency_ms=latency_ms,
            )

        except (ValueError, OSError) as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await log_llm_usage(
                task_type=TaskType.STT.value,
                provider=provider_name.value,
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

            # Record failure for circuit breaker
            routing_engine.record_provider_result(provider_name.value, False, float(latency_ms))
            raise

    async def tts(self, request: TTSRequest) -> TTSResponse:
        """Text-to-speech synthesis."""
        start_time = time.time()
        _request_id = str(uuid.uuid4())

        model = request.model or "bulbul:v1"
        provider_name = ProviderName.SARVAM

        try:
            # Sarvam TTS
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
            audio_b64 = base64.b64encode(content_bytes).decode()

            latency_ms = int((time.time() - start_time) * 1000)

            await log_llm_usage(
                task_type=TaskType.TTS.value,
                provider=provider_name.value,
                model=model,
                sensitivity=request.sensitivity.value,
                prompt_tokens=0,
                completion_tokens=0,
                latency_ms=latency_ms,
                status="success",
                user_id=request.user_id,
                organization_id=request.organization_id,
            )

            # Record success for circuit breaker
            routing_engine.record_provider_result(provider_name.value, True, float(latency_ms))

            return TTSResponse(
                audio_data=audio_b64,
                format="wav",
                provider=provider_name.value,
                model=model,
                latency_ms=latency_ms,
            )

        except (ValueError, OSError) as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await log_llm_usage(
                task_type=TaskType.TTS.value,
                provider=provider_name.value,
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

            # Record failure for circuit breaker
            routing_engine.record_provider_result(provider_name.value, False, float(latency_ms))
            raise

    def _messages_to_prompt(self, messages: list[dict[str, str]]) -> str:
        """Convert messages to single prompt string for caching."""
        return "\n".join([f"{m['role']}: {m['content']}" for m in messages])

    @staticmethod
    def _to_litellm_model(provider: ProviderName | str, model: str) -> str:
        """Prefix model with litellm provider slug (e.g. groq/openai/gpt-oss-20b).

        Model IDs are provider-relative and may themselves contain slashes
        (e.g. 'openai/gpt-oss-20b' on Groq), so always prepend the routed
        provider slug.
        """
        if provider is None:
            return model
        provider_val = provider.value if isinstance(provider, ProviderName) else str(provider)
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

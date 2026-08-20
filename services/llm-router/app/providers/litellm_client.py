"""LiteLLM Client Wrapper for Provider Abstraction"""
import asyncio
import base64
import time
import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator
from pydantic import BaseModel, Field
import litellm
import structlog
from app.schemas.providers import ProviderName, TaskType, SensitivityLevel, ModelProfile
from app.routing.engine import routing_engine, RoutingDecision
from app.routing.usage import log_llm_usage, UsageTracker
from app.routing.cache import get_cached_response, set_cached_response, LLMCache
from app.core.config import get_settings

logger = structlog.get_logger()
settings = get_settings()


# Configure LiteLLM
litellm.set_verbose = settings.DEBUG
litellm.drop_params = True  # Drop unsupported params


class ChatCompletionRequest(BaseModel):
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    task_type: TaskType = TaskType.COPILOT_CHAT
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    stream: bool = False
    response_format: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    project_id: Optional[str] = None
    use_cache: bool = True
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Dict[str, int]
    provider: str
    routed_model: str
    latency_ms: int
    cached: bool = False


class EmbeddingRequest(BaseModel):
    input: List[str]
    model: Optional[str] = None
    task_type: TaskType = TaskType.EMBEDDING
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    user_id: Optional[str] = None
    organization_id: Optional[str] = None


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[Dict[str, Any]]
    model: str
    usage: Dict[str, int]
    provider: str
    latency_ms: int


class STTRequest(BaseModel):
    audio_data: str  # base64 encoded
    language: str = "en"
    model: Optional[str] = None
    task_type: TaskType = TaskType.STT
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    user_id: Optional[str] = None
    organization_id: Optional[str] = None


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
    model: Optional[str] = None
    task_type: TaskType = TaskType.TTS
    sensitivity: SensitivityLevel = SensitivityLevel.INTERNAL
    user_id: Optional[str] = None
    organization_id: Optional[str] = None


class TTSResponse(BaseModel):
    audio_data: str  # base64 encoded
    format: str = "wav"
    provider: str
    model: str
    latency_ms: int


class LiteLLMClient:
    """Wrapper around LiteLLM with routing, caching, and usage tracking."""
    
    def __init__(self):
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
                }
            )
            if cached:
                latency_ms = int((time.time() - start_time) * 1000)
                logger.info("cache_hit", request_id=request_id, model=request.model)
                return ChatCompletionResponse(
                    id=request_id,
                    created=int(time.time()),
                    model=request.model or "cached",
                    choices=cached.get("choices", []),
                    usage=cached.get("usage", {}),
                    provider="cache",
                    routed_model="cached",
                    latency_ms=latency_ms,
                    cached=True
                )
        
        # Determine model if not specified
        model = request.model
        if not model:
            routing_decision = routing_engine.route(request.task_type, request.sensitivity)
            model = routing_decision.model
            provider_name = routing_decision.provider
        else:
            # Find provider for specified model
            provider_name = self._find_provider_for_model(model)
            if not provider_name:
                raise ValueError(f"Model {model} not found in any provider")
        
        # Prepare LiteLLM params
        params = {
            "model": model,
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
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                logger.info("llm_request", request_id=request_id, model=model, provider=provider_name, attempt=attempt)
                
                if request.stream:
                    # Streaming not cached
                    response = await self._stream_completion(params, model, provider_name)
                    latency_ms = int((time.time() - start_time) * 1000)
                    return response
                else:
                    response = await litellm.acompletion(**params)
                    
                    # Extract usage
                    usage = {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    }
                    
                    latency_ms = int((time.time() - start_time) * 1000)
                    
                    # Log usage
                    await log_llm_usage(
                        task_type=request.task_type.value,
                        provider=provider_name,
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
                    routing_engine.record_provider_result(provider_name, True, latency_ms)
                    
                    # Cache successful response
                    if request.use_cache:
                        cache_key_prompt = self._messages_to_prompt(request.messages)
                        await set_cached_response(
                            request.task_type.value,
                            model,
                            cache_key_prompt,
                            {
                                "choices": [c.model_dump() for c in response.choices],
                                "usage": usage,
                            },
                            {
                                "temperature": request.temperature,
                                "max_tokens": request.max_tokens,
                                "response_format": request.response_format,
                            }
                        )
                    
                    return ChatCompletionResponse(
                        id=request_id,
                        created=int(time.time()),
                        model=model,
                        choices=[c.model_dump() for c in response.choices],
                        usage=usage,
                        provider=provider_name,
                        routed_model=model,
                        latency_ms=latency_ms,
                    )
                    
            except Exception as e:
                last_error = e
                latency_ms = int((time.time() - start_time) * 1000)
                
                logger.warning("llm_request_failed", request_id=request_id, model=model, provider=provider_name, attempt=attempt, error=str(e))
                
                await log_llm_usage(
                    task_type=request.task_type.value,
                    provider=provider_name,
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
                
                routing_engine.record_provider_result(provider_name, False, latency_ms)
                
                if attempt < max_retries:
                    routing_decision = routing_engine.route(request.task_type, request.sensitivity)
                    if routing_decision.fallback and routing_decision.fallback != provider_name:
                        provider_name = routing_decision.fallback
                        model = routing_decision.model
                        continue
                
                if attempt == max_retries:
                    raise
        
        raise last_error
    
    async def _stream_completion(self, params: Dict, model: str, provider: str) -> ChatCompletionResponse:
        """Handle streaming completion — accumulates chunks into a final response."""
        request_id = str(uuid.uuid4())
        start_time = time.time()
        
        collected_choices: List[Dict[str, Any]] = []
        total_usage: Dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        try:
            stream = await litellm.acompletion(**params, stream=True)
            async for chunk in stream:
                if chunk.choices:
                    for choice_delta in chunk.choices:
                        collected_choices.append({
                            "index": choice_delta.index,
                            "delta": choice_delta.delta.model_dump() if hasattr(choice_delta.delta, "model_dump") else choice_delta.delta.__dict__,
                            "finish_reason": choice_delta.finish_reason,
                        })
                if hasattr(chunk, "usage") and chunk.usage:
                    total_usage["prompt_tokens"] = chunk.usage.prompt_tokens or 0
                    total_usage["completion_tokens"] = chunk.usage.completion_tokens or 0
                    total_usage["total_tokens"] = total_usage["prompt_tokens"] + total_usage["completion_tokens"]
        except Exception:
            pass
        
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
        request_id = str(uuid.uuid4())
        
        model = request.model
        if not model:
            routing_decision = routing_engine.route(TaskType.EMBEDDING, request.sensitivity)
            model = routing_decision.model
            provider_name = routing_decision.provider
        else:
            provider_name = self._find_provider_for_model(model)
        
        try:
            response = await litellm.aembedding(
                model=model,
                input=request.input,
            )
            
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            }
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            await log_llm_usage(
                task_type=TaskType.EMBEDDING.value,
                provider=provider_name,
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
            routing_engine.record_provider_result(provider_name, True, latency_ms)
            
            return EmbeddingResponse(
                data=[{"embedding": d.embedding, "index": i} for i, d in enumerate(response.data)],
                model=model,
                usage=usage,
                provider=provider_name,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            await log_llm_usage(
                task_type=TaskType.EMBEDDING.value,
                provider=provider_name,
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
            routing_engine.record_provider_result(provider_name, False, latency_ms)
            raise
    
    async def stt(self, request: STTRequest) -> STTResponse:
        """Speech-to-text transcription."""
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        model = request.model or "saarika:v2"
        provider_name = ProviderName.SARVAM
        
        audio_bytes = base64.b64decode(request.audio_data)
        
        try:
            # Sarvam STT
            response = await litellm.atranscription(
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
            routing_engine.record_provider_result(provider_name.value, True, latency_ms)
            
            return STTResponse(
                text=response.text,
                language=request.language,
                confidence=1.0,  # Sarvam doesn't return confidence
                provider=provider_name.value,
                model=model,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
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
            routing_engine.record_provider_result(provider_name.value, False, latency_ms)
            raise
    
    async def tts(self, request: TTSRequest) -> TTSResponse:
        """Text-to-speech synthesis."""
        start_time = time.time()
        request_id = str(uuid.uuid4())
        
        model = request.model or "bulbul:v1"
        provider_name = ProviderName.SARVAM
        
        try:
            # Sarvam TTS
            response = await litellm.aspeech(
                model=model,
                input=request.text,
                voice=request.speaker,
                response_format="wav",
            )
            
            audio_b64 = base64.b64encode(response.content).decode()
            
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
            routing_engine.record_provider_result(provider_name.value, True, latency_ms)
            
            return TTSResponse(
                audio_data=audio_b64,
                format="wav",
                provider=provider_name.value,
                model=model,
                latency_ms=latency_ms,
            )
            
        except Exception as e:
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
            routing_engine.record_provider_result(provider_name.value, False, latency_ms)
            raise
    
    def _messages_to_prompt(self, messages: List[Dict[str, str]]) -> str:
        """Convert messages to single prompt string for caching."""
        return "\n".join([f"{m['role']}: {m['content']}" for m in messages])
    
    def _find_provider_for_model(self, model: str) -> Optional[ProviderName]:
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
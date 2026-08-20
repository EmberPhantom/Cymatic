"""LLM Router Client - shared across API and Worker services"""
import httpx
import json
from typing import Dict, List, Any, Optional
import structlog

logger = structlog.get_logger()

# Lazy-loaded settings to avoid import-time failures
_settings = None


def _get_settings():
    global _settings
    if _settings is None:
        try:
            from cymatic_shared.config import get_settings
            _settings = get_settings()
        except ImportError:
            try:
                from app.core.config import get_settings
                _settings = get_settings()
            except ImportError:
                class _FallbackSettings:
                    LLM_ROUTER_URL = "http://localhost:8001"
                _settings = _FallbackSettings()
    return _settings


class LLMRouterClient:
    """Client for calling LLM Router from any service."""

    def __init__(self, base_url: str = None):
        settings = _get_settings()
        self.base_url = base_url or settings.LLM_ROUTER_URL
        self.client = httpx.AsyncClient(timeout=120.0)

    async def close(self):
        await self.client.aclose()

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        task_type: str = "copilot_chat",
        sensitivity: str = "internal",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Call chat completions endpoint."""
        request = {
            "messages": messages,
            "task_type": task_type,
            "sensitivity": sensitivity,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "user_id": user_id,
            "organization_id": organization_id,
            "project_id": project_id,
        }

        response = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json=request,
        )
        response.raise_for_status()
        return response.json()

    async def embedding(
        self,
        input: List[str],
        task_type: str = "embedding",
        sensitivity: str = "internal",
    ) -> Dict[str, Any]:
        """Call embeddings endpoint."""
        request = {
            "input": input,
            "task_type": task_type,
            "sensitivity": sensitivity,
        }

        response = await self.client.post(
            f"{self.base_url}/v1/embeddings",
            json=request,
        )
        response.raise_for_status()
        return response.json()

    async def stt(
        self,
        audio_data: str,
        language: str = "en",
    ) -> Dict[str, Any]:
        """Call STT endpoint."""
        request = {
            "audio_data": audio_data,
            "language": language,
            "task_type": "stt",
            "sensitivity": "internal",
        }

        response = await self.client.post(
            f"{self.base_url}/v1/audio/transcriptions",
            json=request,
        )
        response.raise_for_status()
        return response.json()

    async def tts(
        self,
        text: str,
        language: str = "en",
        speaker: str = "anushka",
    ) -> Dict[str, Any]:
        """Call TTS endpoint."""
        request = {
            "text": text,
            "language": language,
            "speaker": speaker,
            "task_type": "tts",
            "sensitivity": "internal",
        }

        response = await self.client.post(
            f"{self.base_url}/v1/audio/speech",
            json=request,
        )
        response.raise_for_status()
        return response.json()


# Global client instance
llm_router_client = LLMRouterClient()


async def call_llm(
    messages: List[Dict[str, str]],
    task_type: str = "copilot_chat",
    sensitivity: str = "internal",
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    response_format: Optional[Dict[str, Any]] = None,
) -> str:
    """Convenience function to call LLM and return content."""
    result = await llm_router_client.chat_completion(
        messages=messages,
        task_type=task_type,
        sensitivity=sensitivity,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format=response_format,
    )

    choices = result.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return ""


async def call_llm_json(
    messages: List[Dict[str, str]],
    task_type: str = "copilot_chat",
    sensitivity: str = "internal",
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Call LLM and parse JSON response."""
    result = await llm_router_client.chat_completion(
        messages=messages,
        task_type=task_type,
        sensitivity=sensitivity,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )

    content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.warning("llm_json_parse_failed", content=content[:200])
        return {}


async def call_llm_structured(
    messages: List[Dict[str, str]],
    schema: Dict[str, Any],
    task_type: str = "copilot_chat",
    sensitivity: str = "internal",
) -> Dict[str, Any]:
    """Call LLM with structured output schema."""
    system_msg = {
        "role": "system",
        "content": f"Respond with valid JSON matching this schema: {json.dumps(schema)}"
    }
    messages = [system_msg] + messages

    return await call_llm_json(messages, task_type, sensitivity)

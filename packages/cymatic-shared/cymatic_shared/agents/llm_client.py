"""LLM Router Client - shared across API and Worker services"""

import httpx
import json
from typing import Dict, List, Any, Optional
import structlog
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

logger = structlog.get_logger()

_RETRYABLE = (httpx.TimeoutException, httpx.ConnectError, httpx.ReadTimeout)

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


def _reset_settings() -> None:
    """Clear the cached settings (test hook; next access re-resolves)."""
    global _settings
    _settings = None


# Fallback when no settings object provides LLM_TIMEOUT (e.g. standalone
# shared-package use without a service config on the path).
_DEFAULT_LLM_TIMEOUT = 60.0


def _default_llm_timeout() -> float:
    """Default router timeout, sourced from settings (LLM_TIMEOUT).

    Per-agent overrides take precedence over this default and are passed
    per-request: intake ~120s, clarification ~180s, local SLM
    LOCAL_LLM_TIMEOUT ~300s (CPU inference). The cloud architect path uses
    this default (no per-request override).
    """
    try:
        return float(getattr(_get_settings(), "LLM_TIMEOUT", _DEFAULT_LLM_TIMEOUT))
    except (TypeError, ValueError):
        return _DEFAULT_LLM_TIMEOUT


class LLMRouterClient:
    """Client for calling LLM Router from any service.

    `timeout` defaults to settings LLM_TIMEOUT (fallback 60.0s); pass an
    explicit value — or the per-request `timeout` on chat_completion — for
    slow paths (intake 120s, clarification 180s, local SLM 300s).
    """

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        api_key: str | None = None,
    ):
        settings = _get_settings()
        self.base_url = base_url or settings.LLM_ROUTER_URL
        # Router enforces ADMIN_API_KEY on /v1/*; without this every worker
        # call gets 401 whenever the router key is configured.
        # None means "use configured default"; explicit "" forces no header
        # (e.g. probing an open router). `or` would wrongly fall back to env.
        self.api_key = (
            getattr(settings, "ADMIN_API_KEY", "") or "" if api_key is None else api_key
        )
        resolved_timeout = timeout if timeout is not None else _default_llm_timeout()
        self.client = httpx.AsyncClient(timeout=resolved_timeout)

    async def close(self):
        await self.client.aclose()

    @property
    def _headers(self) -> Dict[str, str]:
        if self.api_key:
            return {"X-Api-Key": self.api_key}
        return {}

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_RETRYABLE),
        before_sleep=before_sleep_log(logger, 20),
    )
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
        model: Optional[str] = None,
        timeout: Optional[float] = None,
        use_cache: bool = True,
    ) -> Dict[str, Any]:
        """Call chat completions endpoint with retry.

        `model` optionally pins an explicit router model id (e.g. a local
        SLM like `phi-3-mini-3.8b-q4`); when None the router picks by policy.
        `timeout` overrides the client default per request (needed for slow
        local SLM inference on CPU); None keeps the client default.
        `use_cache` false bypasses router caching (retries after bad output).
        """
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
            "model": model,
            "use_cache": use_cache,
        }

        response = await self.client.post(
            f"{self.base_url}/v1/chat/completions",
            json=request,
            headers=self._headers,
            timeout=self.client.timeout if timeout is None else timeout,
        )
        # Retry on 502/503 gateway errors
        if response.status_code in (502, 503):
            raise httpx.ConnectError(f"LLM router {response.status_code}")
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
            headers=self._headers,
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
            headers=self._headers,
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
            headers=self._headers,
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
    model: Optional[str] = None,
    timeout: Optional[float] = None,
    use_cache: bool = True,
    required_non_empty_keys: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Call LLM and parse JSON response.

    `model` optionally pins an explicit router model id (e.g. a local SLM).
    `timeout` optionally overrides the client default per request.
    `use_cache` false bypasses the router cache — REQUIRED for retries after
    truncated/error outputs, otherwise the retry replays cached garbage.
    `required_non_empty_keys` names keys that must be present and non-empty
    in a salvaged object — i.e. one recovered via {...}-extraction or
    truncation repair (e.g. ["entities"] for architect results); a salvaged
    parse that misses this completeness bar returns {} so the caller's
    documented failure/fallback path triggers instead of a false success.
    Clean first-try parses are unaffected (callers validate those).

    Robust to common LLM output faults: markdown fences (```json),
    leading prose, trailing commas, mid-object truncation (3B SLMs emit EOS
    early). Returns {} only when unrecoverable — callers MUST treat {} as
    failure and fall back.
    """
    result = await llm_router_client.chat_completion(
        messages=messages,
        task_type=task_type,
        sensitivity=sensitivity,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        model=model,
        timeout=timeout,
        use_cache=use_cache,
    )

    content = result.get("choices", [{}])[0].get("message", {}).get("content", "{}")
    if not isinstance(content, str):
        content = str(content)
    content = content.strip()
    if not content:
        logger.warning("llm_json_empty_content", task_type=task_type)
        return {}

    cleaned = _strip_code_fences(content)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass

    # Attempt to extract the largest {...} block (handles leading prose).
    extracted = _extract_json_object(cleaned)
    if extracted is not None:
        try:
            parsed = json.loads(extracted)
            if isinstance(parsed, dict):
                if required_non_empty_keys and not _meets_completeness_bar(
                    parsed, required_non_empty_keys
                ):
                    logger.warning(
                        "llm_json_extraction_incomplete",
                        task_type=task_type,
                        required=required_non_empty_keys,
                        preview=content[:200],
                    )
                    return {}
                logger.warning(
                    "llm_json_recovered_via_extraction",
                    task_type=task_type,
                    preview=content[:200],
                )
                return parsed
            return {}
        except json.JSONDecodeError:
            pass

    # Last resort: repair mid-object truncation (SLM EOS). Salvages complete
    # entities instead of discarding a nearly-good response.
    repaired = _repair_truncated_json(cleaned)
    if repaired is not None:
        try:
            parsed = json.loads(repaired)
            if isinstance(parsed, dict):
                if required_non_empty_keys and not _meets_completeness_bar(
                    parsed, required_non_empty_keys
                ):
                    logger.warning(
                        "llm_json_repair_incomplete",
                        task_type=task_type,
                        required=required_non_empty_keys,
                        preview=content[:200],
                    )
                    return {}
                logger.warning(
                    "llm_json_recovered_via_repair",
                    task_type=task_type,
                    preview=content[:200],
                )
                return parsed
            return {}
        except json.JSONDecodeError:
            pass

    logger.warning("llm_json_parse_failed", task_type=task_type, content=content[:500])
    return {}


def _repair_truncated_json(content: str) -> Optional[str]:
    """Close a JSON document cut off mid-object (truncated LLM output).

    Strategy: cut back to the last structurally complete point (a `}` or `]`
    that leaves balanced depth), drop any dangling partial string, then close
    remaining open brackets. Returns None when nothing salvageable remains.
    """
    text = content.strip()
    # Find the last index where bracket depth returns to a closable state by
    # scanning while tracking strings.
    depth = 0
    in_str = False
    esc = False
    last_balanced = -1
    last_comma = -1
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{" or ch == "[":
            depth += 1
        elif ch == "}" or ch == "]":
            depth -= 1
            if depth >= 0:
                last_balanced = i
        elif ch == "," and depth > 0:
            last_comma = i
    cut = last_balanced
    if cut <= 0 and last_comma > 0:
        # No balanced close at all (cut very early): fall back to the last
        # complete value boundary.
        cut = last_comma
    if cut <= 0:
        return None
    candidate = text[: cut + 1].rstrip().rstrip(",").rstrip(":").rstrip()
    # Recompute open brackets to close them.
    depth = 0
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in candidate:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            stack.append("}")
        elif ch == "[":
            stack.append("]")
        elif ch == "}" or ch == "]":
            if stack:
                stack.pop()
    candidate += "".join(reversed(stack))
    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict) and parsed:
            return candidate
    except json.JSONDecodeError:
        pass
    return None


def _meets_completeness_bar(parsed: Dict[str, Any], required_keys: List[str]) -> bool:
    """Check a repaired object meets the minimum completeness bar.

    Every key in `required_keys` must be present and non-empty (non-empty
    list/dict/str, non-None scalar). Prevents truncation repair from
    reporting success on a structurally valid but content-free object.
    """
    for key in required_keys:
        value = parsed.get(key)
        if value is None:
            return False
        if isinstance(value, (list, dict, str)) and len(value) == 0:
            return False
    return True


def _strip_code_fences(content: str) -> str:
    """Remove markdown code fences like ```json ... ``` or ``` ... ```."""
    text = content.strip()
    if text.startswith("```"):
        # Drop opening fence line (``` or ```json)
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1 :]
        else:
            text = text[3:]
        # Drop closing fence
        closing = text.rfind("```")
        if closing != -1:
            text = text[:closing]
        text = text.strip()
    return text


def _extract_json_object(content: str) -> Optional[str]:
    """Return the largest balanced {...} substring, or None."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    candidate = content[start : end + 1]
    # Quick balance check to avoid returning obviously truncated JSON
    if candidate.count("{") != candidate.count("}"):
        # Try to find a balanced prefix by scanning
        depth = 0
        in_str = False
        esc = False
        for i, ch in enumerate(candidate):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return candidate[: i + 1]
        return None
    return candidate


async def call_llm_structured(
    messages: List[Dict[str, str]],
    schema: Dict[str, Any],
    task_type: str = "copilot_chat",
    sensitivity: str = "internal",
) -> Dict[str, Any]:
    """Call LLM with structured output schema."""
    system_msg = {
        "role": "system",
        "content": f"Respond with valid JSON matching this schema: {json.dumps(schema)}",
    }
    messages = [system_msg] + messages

    return await call_llm_json(messages, task_type, sensitivity)

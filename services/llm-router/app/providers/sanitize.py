"""Prompt sanitization helpers (extracted from providers.litellm_client)."""

import re

_MAX_MESSAGE_CHARS = 20000
_MAX_MESSAGES = 100

_SANITIZE_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
]


def _sanitize_text(text: str, max_len: int = _MAX_MESSAGE_CHARS) -> str:
    # Truncate
    if len(text) > max_len:
        text = text[:max_len]
    # Basic prompt injection sanitization: mask common injection phrases
    for pat in _SANITIZE_PATTERNS:
        text = pat.sub("[filtered]", text)
    # Strip excessive whitespace and control chars
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
    return text


def _sanitize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(messages) > _MAX_MESSAGES:
        raise ValueError(f"Too many messages: {len(messages)} > {_MAX_MESSAGES}")
    sanitized: list[dict[str, str]] = []
    allowed_roles = {"system", "user", "assistant", "tool", "function"}
    for m in messages:
        role = str(m.get("role", "user")).strip().lower()
        if role not in allowed_roles:
            role = "user"
        content = str(m.get("content", ""))
        content = _sanitize_text(content)
        # Preserve other fields like name/tool_call_id if present
        new_m: dict[str, str] = {"role": role, "content": content}
        # Keep optional fields sanitized
        for k, v in m.items():
            if k not in ("role", "content") and isinstance(v, str):
                new_m[k] = _sanitize_text(v, max_len=5000)
        sanitized.append(new_m)
    return sanitized

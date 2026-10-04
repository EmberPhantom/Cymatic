"""Prompt sanitization helpers (extracted from providers.litellm_client)."""

import base64
import re
import unicodedata

_MAX_MESSAGE_CHARS = 20000
_MAX_MESSAGES = 100

# Zero-width / invisible chars stripped after NFKC (obfuscation bypass).
_ZERO_WIDTH_RE = re.compile(
    "[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff\u00ad\u061c]"
)

_SANITIZE_PATTERNS = [
    re.compile(r"ignore\s+previous\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"override\s+(all\s+)?(previous|prior|safety|system)\s+instructions", re.IGNORECASE),
    re.compile(r"system\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"developer\s*:\s*", re.IGNORECASE),
    re.compile(r"assistant\s*:\s*you\s+are", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"jailbreak|danjailbreak|do\s+anything\s+now", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(system|hidden|secret)\s+(prompt|instructions)", re.IGNORECASE),
    re.compile(r"exfiltrate|leak\s+(api|secret)\s*key", re.IGNORECASE),
]

_B64_CANDIDATE_RE = re.compile(r"[A-Za-z0-9+/]{20,}={0,2}")


def _normalize_obfuscation(text: str) -> str:
    """NFKC + zero-width strip to defeat unicode/base64-obfuscation."""
    text = unicodedata.normalize("NFKC", text)
    text = _ZERO_WIDTH_RE.sub("", text)
    return text


def _filter_b64_obfuscation(text: str) -> str:
    """Decode base64 blobs; if decoded text matches an injection pattern, filter the blob."""

    def _repl(m: re.Match[str]) -> str:
        blob = m.group(0)
        if len(blob) % 4 != 0 or len(blob) < 20:
            return blob
        try:
            decoded = base64.b64decode(blob, validate=True).decode("utf-8", "ignore")
        except Exception:
            return blob
        if not decoded or not decoded.strip():
            return blob
        probe = _normalize_obfuscation(decoded)
        # Only treat printable, mostly-text decodes as smuggling
        printable = 0
        for ch in probe:
            if ch.isprintable() or ch.isspace():
                printable += 1
        if len(probe) < 4 or printable / max(len(probe), 1) < 0.7:
            return blob
        for pat in _SANITIZE_PATTERNS:
            if pat.search(probe):
                return "[filtered]"
        return blob

    # Bound work: only scan when plausible b64 present
    if len(text) < 20:
        return text
    try:
        return _B64_CANDIDATE_RE.sub(_repl, text)
    except Exception:
        return text


def _sanitize_text(text: str, max_len: int = _MAX_MESSAGE_CHARS) -> str:
    # Truncate
    if len(text) > max_len:
        text = text[:max_len]
    # Normalize unicode obfuscation first so patterns match homoglyphs
    text = _normalize_obfuscation(text)
    # Base64-smuggled injections
    text = _filter_b64_obfuscation(text)
    # Basic prompt injection sanitization: mask common injection phrases
    for pat in _SANITIZE_PATTERNS:
        text = pat.sub("[filtered]", text)
    # Strip excessive whitespace and control chars
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text)
    return text


# Roles that pass through; everything else (developer, tool, function, ...)
# is coerced to user and flagged.
_ALLOWED_ROLES = {"system", "user", "assistant"}
# Spoof fields dropped when the role was coerced.
_SPOOF_FIELDS = {"name", "tool_call_id", "tool_calls", "function_call"}


def _sanitize_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(messages) > _MAX_MESSAGES:
        raise ValueError(f"Too many messages: {len(messages)} > {_MAX_MESSAGES}")
    sanitized: list[dict[str, str]] = []
    for m in messages:
        raw_role = str(m.get("role", "user")).strip().lower()
        coerced_from: str | None = None
        role = raw_role
        if role not in _ALLOWED_ROLES:
            coerced_from = raw_role
            role = "user"
        content = str(m.get("content", ""))
        content = _sanitize_text(content)
        if coerced_from:
            content = f"[role:{coerced_from} coerced to user] {content}"
        # Preserve other fields like name/tool_call_id if present
        new_m: dict[str, str] = {"role": role, "content": content}
        # Keep optional fields sanitized; drop spoof fields when coerced
        for k, v in m.items():
            if k not in ("role", "content") and isinstance(v, str):
                if coerced_from and k in _SPOOF_FIELDS:
                    new_m[f"stripped_{k}"] = "[dropped]"
                    continue
                new_m[k] = _sanitize_text(v, max_len=5000)
        sanitized.append(new_m)
    return sanitized

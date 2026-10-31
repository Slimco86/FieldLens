"""Bounding and conservative redaction for activity-log text and structured payloads.

Everything persisted in the log passes through here: secrets-like strings are replaced by
``[redacted]``, long strings are cut with an explicit ``[truncated N chars]`` marker, and
oversized structures are replaced by a size marker. Postgres cannot store NUL characters, so
they are dropped. Raw document text is only ever kept as a bounded excerpt."""

from __future__ import annotations

import json
import re
from typing import Any

REDACTED = "[redacted]"
SUMMARY_LIMIT = 1000
QUESTION_LIMIT = 2000
STRING_LIMIT = 500
KEY_LIMIT = 64
MAX_DEPTH = 4
MAX_ITEMS = 50
MAX_PAYLOAD_BYTES = 8192

_SECRET_KEY = re.compile(
    r"(api[_-]?key|secret|token|password|passwd|authorization|credential|bearer|private[_-]?key"
    r"|cookie|session)",
    re.IGNORECASE,
)
_PATTERNS = (
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)", re.S
    ),
    re.compile(r"(?i)\b(?:authorization|proxy-authorization)\s*[:=]\s*[^\r\n]+"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(
        r"(?i)\b[\w.-]*(?:api[_-]?key|secret|token|password|passwd|credential)[\w.-]*"
        r"\s*[:=]\s*[\"']?[^\s\"',;&]+"
    ),
    re.compile(r"\b(?:sk|pk|rk|ghp|gho|ghs|xox[abprs]|AKIA|ASIA|AIza)[-_A-Za-z0-9]{12,}"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]*)?"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@\S+"),
)
_LONG_TOKEN = re.compile(r"[A-Za-z0-9_+/=-]{32,}")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _long_token(match: re.Match[str]) -> str:
    token = match.group(0)
    if _UUID.match(token) or _SHA256.match(token):
        return token  # identifiers and content hashes are not credentials
    has_digit = any(c.isdigit() for c in token)
    has_alpha = any(c.isalpha() for c in token)
    return REDACTED if has_digit and has_alpha else token


def redact(text: str) -> str:
    """Replace credential-looking substrings; conservative (may over-redact)."""
    text = text.replace("\x00", "")
    for pattern in _PATTERNS:
        text = pattern.sub(REDACTED, text)
    return _LONG_TOKEN.sub(_long_token, text)


def bound_text(text: str, limit: int) -> tuple[str, bool]:
    """Redact then cut to ``limit`` characters plus an explicit marker; True when cut."""
    text = redact(text)
    if len(text) <= limit:
        return text, False
    return f"{text[:limit]}...[truncated {len(text) - limit} chars]", True


def _walk(value: Any, depth: int, state: list[bool]) -> Any:
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            state[0] = True
            return None
        return value
    if isinstance(value, str):
        text, cut = bound_text(value, STRING_LIMIT)
        state[0] = state[0] or cut
        return text
    if depth >= MAX_DEPTH:
        state[0] = True
        return "[truncated: nesting too deep]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= MAX_ITEMS:
                state[0] = True
                out["_truncated_items"] = len(value) - MAX_ITEMS
                break
            key, _ = bound_text(str(k), KEY_LIMIT)
            out[key] = REDACTED if _SECRET_KEY.search(str(k)) else _walk(v, depth + 1, state)
        return out
    if isinstance(value, list | tuple):
        items = [_walk(v, depth + 1, state) for v in list(value)[:MAX_ITEMS]]
        if len(value) > MAX_ITEMS:
            state[0] = True
            items.append(f"[truncated {len(value) - MAX_ITEMS} items]")
        return items
    state[0] = True
    text, _ = bound_text(str(value), STRING_LIMIT)
    return text


def sanitize_detail(detail: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    """Bounded, redacted JSON object; replaced by a size marker when still too large."""
    state = [False]
    cleaned = _walk(detail or {}, 0, state)
    size = len(json.dumps(cleaned, ensure_ascii=False).encode())
    if size > MAX_PAYLOAD_BYTES:
        return {
            "_truncated": True,
            "original_bytes": size,
            "keys": [str(k)[:KEY_LIMIT] for k in list(cleaned)[:20]],
        }, True
    return dict(cleaned), state[0]

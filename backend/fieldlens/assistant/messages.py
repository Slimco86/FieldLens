"""Provider-neutral message model: text, image parts, tool calls/results, opaque reasoning.

These are internal adapter types (not public API contracts). Image bytes are carried as base64
text so a request can be hashed, recorded and replayed. Opaque reasoning is never rendered in
``repr`` and is never logged; it exists only so a provider can replay it on a later turn.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

MAX_IMAGE_BYTES = 10 * 1024 * 1024
TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
CALL_ID = re.compile(r"^[A-Za-z0-9_\-:.]{1,128}$")


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class TextPart(_Frozen):
    type: Literal["text"] = "text"
    text: str


class ImagePart(_Frozen):
    """A page image (FL-022) sent as an input content part."""

    type: Literal["image"] = "image"
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    data_base64: str = Field(repr=False)

    @field_validator("data_base64")
    @classmethod
    def _valid_base64(cls, value: str) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("image data must be valid base64") from exc
        if not raw or len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("image must be 1 byte to 10 MiB")
        return value

    @classmethod
    def from_bytes(
        cls, media_type: Literal["image/png", "image/jpeg", "image/webp"], raw: bytes
    ) -> ImagePart:
        return cls(media_type=media_type, data_base64=base64.b64encode(raw).decode("ascii"))

    @property
    def byte_size(self) -> int:
        return len(base64.b64decode(self.data_base64))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(base64.b64decode(self.data_base64)).hexdigest()


class ToolCallPart(_Frozen):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    arguments: dict[str, JsonValue]

    @field_validator("call_id")
    @classmethod
    def _call_id(cls, value: str) -> str:
        if not CALL_ID.match(value):
            raise ValueError("invalid tool call id")
        return value

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not TOOL_NAME.match(value):
            raise ValueError("invalid tool name")
        return value


class ToolResultPart(_Frozen):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    content: str
    is_error: bool = False

    @field_validator("call_id")
    @classmethod
    def _call_id(cls, value: str) -> str:
        if not CALL_ID.match(value):
            raise ValueError("invalid tool call id")
        return value


class ReasoningPart(_Frozen):
    """Opaque provider reasoning, replayed verbatim; never logged or displayed."""

    type: Literal["reasoning"] = "reasoning"
    opaque: str = Field(repr=False)
    item_id: str | None = None


Part = Annotated[
    TextPart | ImagePart | ToolCallPart | ToolResultPart | ReasoningPart,
    Field(discriminator="type"),
]


class Message(_Frozen):
    role: Literal["system", "user", "assistant", "tool"]
    parts: tuple[Part, ...]

    @field_validator("parts")
    @classmethod
    def _non_empty(cls, value: tuple[Part, ...]) -> tuple[Part, ...]:
        if not value:
            raise ValueError("a message needs at least one part")
        return value

    def tool_calls(self) -> list[ToolCallPart]:
        return [p for p in self.parts if isinstance(p, ToolCallPart)]


class ToolSpec(_Frozen):
    """An allowlisted, typed, read-only tool. ``parameters`` is a closed JSON-Schema subset."""

    name: str
    description: str
    parameters: dict[str, JsonValue]

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not TOOL_NAME.match(value):
            raise ValueError("invalid tool name")
        return value


class Usage(_Frozen):
    """Provider-reported usage. ``None`` means unavailable, never zero."""

    input_tokens: int | None = Field(None, ge=0)
    cached_input_tokens: int | None = Field(None, ge=0)
    output_tokens: int | None = Field(None, ge=0)
    web_search_queries: int | None = Field(None, ge=0)

    @property
    def complete(self) -> bool:
        return self.input_tokens is not None and self.output_tokens is not None


Effort = Literal["minimal", "low", "medium", "high"]
EFFORTS: tuple[str, ...] = ("minimal", "low", "medium", "high")


class ProviderRequest(_Frozen):
    model: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    max_output_tokens: int = Field(4096, ge=1, le=8192)
    effort: Effort | None = None
    """Requested ``reasoning.effort``. ``None`` omits the field: the provider default applies
    (``high`` on muse-spark-1.3 in MI-6, which exhausted small output budgets)."""

    def fingerprint(self) -> str:
        """Stable hash of the request for replay lookup and idempotency (no secrets inside).

        An unset effort is left out of the hash, so fingerprints (and recordings) made before the
        effort field existed stay valid; any explicit effort yields a different fingerprint.
        """
        data = self.model_dump(mode="json")
        if self.effort is None:
            data.pop("effort")
        return hashlib.sha256(canonical_json(data).encode()).hexdigest()


class ProviderResponse(_Frozen):
    status: Literal["completed", "refusal", "truncated"] = "completed"
    parts: tuple[Part, ...] = ()
    usage: Usage | None = None
    model: str | None = None
    provider_request_id: str | None = None
    refusal_text: str | None = Field(None, repr=False)

    def tool_calls(self) -> list[ToolCallPart]:
        return [p for p in self.parts if isinstance(p, ToolCallPart)]

    def text(self) -> str:
        return "".join(p.text for p in self.parts if isinstance(p, TextPart))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


_TYPES: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def validate_tool_arguments(spec: ToolSpec, arguments: dict[str, JsonValue]) -> str | None:
    """Closed-schema check (required, no extras, primitive types, enum). Returns a problem or None."""
    props = spec.parameters.get("properties", {})
    required = spec.parameters.get("required", [])
    if not isinstance(props, dict) or not isinstance(required, list):
        return "tool schema is malformed"
    for key in required:
        if key not in arguments:
            return f"missing required argument {key!r}"
    for key, value in arguments.items():
        schema = props.get(key)
        if not isinstance(schema, dict):
            return f"unexpected argument {key!r}"
        expected = schema.get("type")
        if isinstance(expected, str) and expected in _TYPES:
            ok = isinstance(value, _TYPES[expected])
            if expected in ("integer", "number") and isinstance(value, bool):
                ok = False
            if not ok:
                return f"argument {key!r} must be {expected}"
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            return f"argument {key!r} is not an allowed value"
    return None

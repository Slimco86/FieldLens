"""Deterministic stub provider, recorded-replay provider and a recorder.

None of these touch the network. The stub is scripted (responses, typed errors or callables) or,
without a script, echoes deterministically: image parts are described by hash/size, tool results
are acknowledged and text is hashed. Replay serves recordings keyed by request fingerprint;
recordings hold responses and typed error codes only, never requests, prompts or credentials.
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from . import errors
from .errors import AssistantError, ProviderMalformed, ReplayMiss
from .messages import (
    ImagePart,
    Message,
    ProviderRequest,
    ProviderResponse,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Usage,
)
from .provider import CancelToken, Provider, scrub

StubStep = ProviderResponse | AssistantError | Callable[[ProviderRequest], ProviderResponse]

ERROR_CLASSES: dict[str, type[AssistantError]] = {
    cls.code: cls
    for cls in (
        errors.ProviderAuthError,
        errors.ProviderRateLimited,
        errors.ProviderServerError,
        errors.ProviderTimeout,
        errors.ProviderConnectionError,
        errors.ProviderMalformed,
        errors.ProviderRejected,
    )
}
RECORDING_SCHEMA = 1


def text_response(text: str, usage: Usage | None = None, **kw: Any) -> ProviderResponse:
    return ProviderResponse(parts=(TextPart(text=text),), usage=usage, **kw)


def tool_call_response(
    *calls: tuple[str, str, dict[str, Any]], usage: Usage | None = None
) -> ProviderResponse:
    """``(call_id, tool_name, arguments)`` triples as one assistant turn."""
    parts = tuple(ToolCallPart(call_id=i, name=n, arguments=a) for i, n, a in calls)
    return ProviderResponse(parts=parts, usage=usage)


def refusal_response(usage: Usage | None = None) -> ProviderResponse:
    return ProviderResponse(status="refusal", refusal_text="declined", usage=usage)


def truncated_response(partial: str = "", usage: Usage | None = None) -> ProviderResponse:
    parts = (TextPart(text=partial),) if partial else ()
    return ProviderResponse(status="truncated", parts=parts, usage=usage)


def default_usage(request: ProviderRequest, output_chars: int) -> Usage:
    """Deterministic synthetic usage (bytes/4 style); clearly synthetic, only for the stub."""
    size = sum(
        len(p.text) if isinstance(p, TextPart) else 64
        for m in request.messages
        for p in m.parts
        if isinstance(p, TextPart | ImagePart | ToolResultPart)
    )
    return Usage(
        input_tokens=max(size // 4, 1),
        cached_input_tokens=0,
        output_tokens=max(output_chars // 4, 1),
    )


def echo_response(request: ProviderRequest) -> ProviderResponse:
    last: Message = request.messages[-1]
    images = [p for m in request.messages for p in m.parts if isinstance(p, ImagePart)]
    results = [p for p in last.parts if isinstance(p, ToolResultPart)]
    if results:
        text = "stub: tool results " + ",".join(
            f"{r.call_id}={'error' if r.is_error else 'ok'}" for r in results
        )
    elif images:
        text = "stub: images " + ",".join(f"{i.sha256[:8]}:{i.byte_size}" for i in images)
    else:
        text = f"stub: {request.fingerprint()[:12]}"
    return text_response(text, usage=default_usage(request, len(text)), model=request.model)


class StubProvider:
    """Scripted deterministic provider. Every call is recorded in ``calls``."""

    name = "stub"

    def __init__(
        self, script: Sequence[StubStep] | None = None, *, loop_last: bool = False
    ) -> None:
        self._script: deque[StubStep] = deque(script or ())
        self._scripted = script is not None
        self._loop_last = loop_last
        self._last: StubStep | None = None
        self.calls: list[ProviderRequest] = []

    def complete(
        self, request: ProviderRequest, *, timeout_s: float, cancel: CancelToken
    ) -> ProviderResponse:
        cancel.raise_if_cancelled()
        self.calls.append(request)
        if not self._scripted:
            return echo_response(request)
        if self._script:
            step = self._script.popleft()
            self._last = step
        elif self._loop_last and self._last is not None:
            step = self._last
        else:
            raise ProviderMalformed("stub script exhausted")
        if isinstance(step, AssistantError):
            raise step
        if isinstance(step, ProviderResponse):
            return step
        return step(request)


class ReplayProvider:
    """Serves recorded responses keyed by request fingerprint, in recorded order per key."""

    name = "replay"

    def __init__(self, recordings: Sequence[dict[str, Any]]) -> None:
        self._by_key: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        for item in recordings:
            self._by_key[item["fingerprint"]].append(item)
        self.calls: list[ProviderRequest] = []

    @classmethod
    def from_file(cls, path: Path) -> ReplayProvider:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema") != RECORDING_SCHEMA:
            raise ProviderMalformed("unsupported recording schema")
        return cls(data["recordings"])

    def complete(
        self, request: ProviderRequest, *, timeout_s: float, cancel: CancelToken
    ) -> ProviderResponse:
        cancel.raise_if_cancelled()
        self.calls.append(request)
        queue = self._by_key.get(request.fingerprint())
        if not queue:
            raise ReplayMiss("no recording for this request fingerprint")
        item = queue.popleft()
        if "error" in item:
            cls = ERROR_CLASSES.get(item["error"]["code"])
            if cls is None:
                raise ProviderMalformed("unknown recorded error code")
            raise cls()
        return ProviderResponse.model_validate(item["response"])


class RecordingProvider:
    """Wraps another provider and collects sanitized recordings (responses/errors only)."""

    def __init__(self, inner: Provider) -> None:
        self.name = f"recording:{inner.name}"
        self._inner = inner
        self.recordings: list[dict[str, Any]] = []

    def complete(
        self, request: ProviderRequest, *, timeout_s: float, cancel: CancelToken
    ) -> ProviderResponse:
        key = request.fingerprint()
        try:
            response = self._inner.complete(request, timeout_s=timeout_s, cancel=cancel)
        except AssistantError as exc:
            if exc.code in ERROR_CLASSES:
                self.recordings.append(
                    {"fingerprint": key, "effort": request.effort, "error": {"code": exc.code}}
                )
            raise
        self.recordings.append(
            {
                "fingerprint": key,
                "effort": request.effort,
                "response": response.model_dump(mode="json"),
            }
        )
        return response

    def to_json(self) -> str:
        text = json.dumps(
            {"schema": RECORDING_SCHEMA, "recordings": self.recordings}, indent=1, sort_keys=True
        )
        if scrub(text) != text:
            raise ProviderMalformed("recording contains a credential-like value; refusing to write")
        return text

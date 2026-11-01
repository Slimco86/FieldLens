"""Fixtures for the extraction-harness tests: a real project (PostgreSQL) with a perforation
table, a text-layer PDF and a scan-like PDF, an offline fixture provider and a harness factory.
All values are invented; nothing here makes a network call or spends credits."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from fieldlens.assistant.errors import AssistantError
from fieldlens.assistant.messages import (
    ProviderRequest,
    ProviderResponse,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Usage,
)
from fieldlens.assistant.provider import CancelToken
from fieldlens.assistant.stub import text_response, tool_call_response

Responder = Callable[[ProviderRequest, int], ProviderResponse | AssistantError]


def usage(inp: int = 1200, out: int = 300) -> Usage:
    return Usage(input_tokens=inp, cached_input_tokens=0, output_tokens=out)


def json_response(candidates: list[dict[str, Any]], u: Usage | None = None) -> ProviderResponse:
    return text_response(json.dumps({"candidates": candidates}), usage=u or usage())


def call_response(name: str, args: dict[str, Any], call_id: str = "c1") -> ProviderResponse:
    return tool_call_response((call_id, name, args), usage=usage())


@dataclass
class FixtureProvider:
    """Responder-driven provider with an in-flight counter and optional simulated latency.

    ``responder(request, call_number)`` returns a response or an AssistantError to raise."""

    responder: Responder
    latency_s: float = 0.0
    name: str = "fixture-stub"
    calls: list[ProviderRequest] = field(default_factory=list)
    in_flight: int = 0
    max_in_flight: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def complete(
        self, request: ProviderRequest, *, timeout_s: float, cancel: CancelToken
    ) -> ProviderResponse:
        cancel.raise_if_cancelled()
        with self._lock:
            self.calls.append(request)
            number = len(self.calls)
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.latency_s:
                time.sleep(self.latency_s)
            result = self.responder(request, number)
        finally:
            with self._lock:
                self.in_flight -= 1
        if isinstance(result, AssistantError):
            raise result
        return result


def first_user_text(request: ProviderRequest) -> str:
    for message in request.messages:
        if message.role == "user":
            for part in message.parts:
                if isinstance(part, TextPart):
                    return part.text
    return ""


def tool_results(request: ProviderRequest) -> list[ToolResultPart]:
    return [p for m in request.messages for p in m.parts if isinstance(p, ToolResultPart)]


def tool_calls_in(request: ProviderRequest) -> list[ToolCallPart]:
    return [p for m in request.messages for p in m.parts if isinstance(p, ToolCallPart)]


ZERO = Decimal(0)

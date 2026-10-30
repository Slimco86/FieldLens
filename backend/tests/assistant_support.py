"""Shared constants/helpers for the offline provider tests."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal

from fieldlens.assistant.messages import Message, TextPart, ToolSpec
from fieldlens.assistant.provider import Pricing
from fieldlens.assistant.runner import WorkUnit

MakeUnit = Callable[..., WorkUnit]

MODEL = "stub-model-1"
PRICING = Pricing(
    revision="test-rates-1",
    model=MODEL,
    input_usd_per_mtok=Decimal("1.00"),
    output_usd_per_mtok=Decimal("4.00"),
    cached_input_usd_per_mtok=Decimal("0.25"),
)
LOOKUP_TOOL = ToolSpec(
    name="read_page",
    description="Read one page of a source document.",
    parameters={
        "type": "object",
        "properties": {"page": {"type": "integer"}},
        "required": ["page"],
    },
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def user(text: str) -> Message:
    return Message(role="user", parts=(TextPart(text=text),))

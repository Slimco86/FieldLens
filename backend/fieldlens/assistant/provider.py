"""Provider protocol, cancellation token, pricing and the conservative cost bounds."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

from .errors import InvalidPricing, RequestCancelled
from .messages import (
    ImagePart,
    ProviderRequest,
    ProviderResponse,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Usage,
    canonical_json,
)

MILLION = Decimal(1_000_000)
MAX_RATE_USD_PER_MTOK = Decimal(1000)  # sanity bound against per-token/per-Ktok unit mistakes
_REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_CENT_FRACTION = Decimal("0.000001")


class CancelToken:
    """Cooperative cancellation shared by a work unit and its provider calls."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise RequestCancelled("request cancelled")

    def wait(self, seconds: float) -> bool:
        """Sleep up to ``seconds``; True when cancelled meanwhile."""
        return self._event.wait(seconds)


class Provider(Protocol):
    """One synchronous model call. Retries, budgets and limits belong to the runner."""

    name: str

    def complete(
        self, request: ProviderRequest, *, timeout_s: float, cancel: CancelToken
    ) -> ProviderResponse: ...


@dataclass(frozen=True)
class Pricing:
    """Owner-supplied rates (USD per million tokens). No rate is assumed by the code."""

    revision: str
    model: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    cached_input_usd_per_mtok: Decimal | None = None

    def validate(self) -> Pricing:
        """Reject a rate card that could silently zero or distort cost accounting."""
        if not _REVISION.fullmatch(self.revision):
            raise InvalidPricing("pricing revision must be a 1-64 character slug")
        rates = [("input", self.input_usd_per_mtok), ("output", self.output_usd_per_mtok)]
        if self.cached_input_usd_per_mtok is not None:
            rates.append(("cached input", self.cached_input_usd_per_mtok))
        for label, rate in rates:
            if not rate.is_finite() or rate <= 0:
                raise InvalidPricing(f"{label} rate must be a finite positive USD per Mtok")
            if rate > MAX_RATE_USD_PER_MTOK:
                raise InvalidPricing(f"{label} rate exceeds the USD per Mtok sanity bound")
        if (
            self.cached_input_usd_per_mtok is not None
            and self.cached_input_usd_per_mtok > self.input_usd_per_mtok
        ):
            raise InvalidPricing("cached input rate cannot exceed the input rate")
        if not self.model.strip():
            raise InvalidPricing("pricing model is required")
        return self

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> Pricing:
        """Build from rate-card data (strings or numbers; never floats-through-code)."""
        try:
            cached = data.get("cached_input_usd_per_mtok")
            card = cls(
                revision=str(data["revision"]),
                model=str(data["model"]),
                input_usd_per_mtok=Decimal(str(data["input_usd_per_mtok"])),
                output_usd_per_mtok=Decimal(str(data["output_usd_per_mtok"])),
                cached_input_usd_per_mtok=None if cached is None else Decimal(str(cached)),
            )
        except (KeyError, InvalidOperation, ValueError, TypeError) as exc:
            raise InvalidPricing("rate card is missing a field or has a non-numeric rate") from exc
        return card.validate()

    def input_rate(self, cached: bool) -> Decimal:
        if cached and self.cached_input_usd_per_mtok is not None:
            return self.cached_input_usd_per_mtok
        return self.input_usd_per_mtok


def load_pricing(path: Path) -> Pricing:
    """Load an owner-supplied rate card (JSON data file). Rates live in data, not in code.

    Register the result with ``BudgetLedger.register_pricing`` under a new ``revision``; an
    existing revision with different rates is rejected, so a new rate card is a new revision.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InvalidPricing("rate card could not be read as JSON") from exc
    if not isinstance(data, dict):
        raise InvalidPricing("rate card must be a JSON object")
    return Pricing.from_mapping(data)


def _quantize_up(value: Decimal) -> Decimal:
    return (value / _CENT_FRACTION).to_integral_value(rounding="ROUND_CEILING") * _CENT_FRACTION


# Hidden-token allowances for the input bound, chosen from MI-6 (muse-spark-1.3, Responses):
# a one-tool request estimated at 245 bytes-as-tokens billed 552 input tokens (about 307 hidden),
# and the follow-up step with the tool result and two replayed reasoning items billed 992.
# Each allowance is deliberately above what that single data point implies, so a reservation
# is not exceeded by the measured cases; over-reserving costs little against the USD 0.50 cap.
TOOLS_PRESENT_OVERHEAD_TOKENS = 512  # provider-added tool/system preamble when any tool is sent
PER_TOOL_OVERHEAD_TOKENS = 128  # per tool definition, on top of its JSON bytes
TOOL_ROUND_TRIP_OVERHEAD_TOKENS = 128  # per tool call or tool result item replayed in input
REASONING_ITEM_OVERHEAD_TOKENS = 256  # per replayed opaque reasoning item, on top of its bytes


def estimate_input_tokens(request: ProviderRequest, image_token_bound: int) -> int:
    """Upper bound: one token per UTF-8 byte of text/JSON, a fixed bound per image, plus
    allowances for tool definitions, tool round trips and replayed opaque reasoning items.

    Image bytes are not counted per byte; the configured per-image bound stands in and is an
    owner-visible assumption (MI-6: measured at most 242 tokens for 680x280 px, bound 8192).
    The tool/reasoning allowances exist because MI-6 showed bytes-as-tokens under-counting tool
    requests by 2.3x (245 estimated vs 552 billed).
    """
    total = 0
    if request.tools:
        total += TOOLS_PRESENT_OVERHEAD_TOKENS
    for tool in request.tools:
        total += PER_TOOL_OVERHEAD_TOKENS
        total += len(canonical_json(tool.model_dump(mode="json")).encode())
    for message in request.messages:
        total += 4
        for part in message.parts:
            if isinstance(part, TextPart):
                total += len(part.text.encode())
            elif isinstance(part, ImagePart):
                total += image_token_bound
            elif isinstance(part, ToolCallPart):
                total += TOOL_ROUND_TRIP_OVERHEAD_TOKENS
                total += len(part.name.encode()) + len(canonical_json(part.arguments).encode())
            elif isinstance(part, ToolResultPart):
                total += TOOL_ROUND_TRIP_OVERHEAD_TOKENS + len(part.content.encode())
            elif isinstance(part, ReasoningPart):
                total += REASONING_ITEM_OVERHEAD_TOKENS + len(part.opaque.encode())
    return max(total, 1)


def attempt_upper_bound_usd(
    request: ProviderRequest, pricing: Pricing, image_token_bound: int
) -> Decimal:
    """Upper bound for one dispatch: full-price input plus the full output allowance."""
    tokens_in = Decimal(estimate_input_tokens(request, image_token_bound))
    tokens_out = Decimal(request.max_output_tokens)
    return _quantize_up(
        (tokens_in * pricing.input_usd_per_mtok + tokens_out * pricing.output_usd_per_mtok)
        / MILLION
    )


def actual_cost_usd(usage: Usage | None, pricing: Pricing) -> Decimal | None:
    """Billed amount from provider usage, or None when usage is unavailable/incomplete."""
    if usage is None or not usage.complete:
        return None
    assert usage.input_tokens is not None and usage.output_tokens is not None  # for mypy
    cached = min(usage.cached_input_tokens or 0, usage.input_tokens)
    fresh = usage.input_tokens - cached
    amount = (
        Decimal(fresh) * pricing.input_rate(False)
        + Decimal(cached) * pricing.input_rate(True)
        + Decimal(usage.output_tokens) * pricing.output_usd_per_mtok
    ) / MILLION
    return _quantize_up(amount)


_PATTERNS = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-~+/=]{6,}"),
    re.compile(r"\b(?:sk|pk|key|meta|llm)[-_][A-Za-z0-9_\-]{12,}"),
    re.compile(r"(?i)(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[^\s\"',;]{6,}"),
)


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """Remove known secret values and credential-looking tokens from diagnostic text."""
    out = text
    for secret in secrets:
        if secret and len(secret) >= 4:
            out = out.replace(secret, "[redacted]")
    out = _PATTERNS[0].sub("Bearer [redacted]", out)
    out = _PATTERNS[1].sub("[redacted]", out)
    out = _PATTERNS[2].sub(r"\1[redacted]", out)
    return out

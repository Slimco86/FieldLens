"""Chat runtime: provider, pricing, usage ledger periods and the runaway-loop bounds.

Owner decision D4: the assistant has NO spend cap. The ledger only *records* usage for visibility.
The shared ledger has a hard 150 USD per-period database constraint that other features rely on, so
chat usage is booked in rotating ``chat-assistant-N`` periods: when the current period cannot
reserve a turn's small bounded reservation (or is paused) the next period is used. Nothing blocks a
turn on money. Step, tool-call and time bounds stay in force against runaway loops.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.errors import ReservationStateError
from fieldlens.assistant.provider import Pricing, Provider
from fieldlens.assistant.runner import RequestLimits
from fieldlens.config import Settings
from fieldlens.retrieval.search import RetrievalService
from fieldlens.series.service import SeriesService

if TYPE_CHECKING:
    from fieldlens.processing.runtime import MetaContext

logger = logging.getLogger(__name__)

PERIOD_PREFIX = "chat-assistant-"
BALANCE_SOURCE = "auto: chat usage is recorded for visibility only (no spend cap)"
MAX_PERIOD_ROTATIONS = 200


@dataclass(frozen=True)
class ChatLimits:
    """Runaway-loop bounds (not spend bounds)."""

    max_steps: int = 12
    max_tool_calls: int = 10
    deadline_s: float = 150.0
    max_output_tokens: int = 4096
    reservation_usd: Decimal = Decimal("5")
    lease_s: float = 60.0
    retry_backoff_s: float = 0.5

    def request_limits(self) -> RequestLimits:
        return RequestLimits(
            max_attempts=self.max_steps,
            max_tool_calls=self.max_tool_calls,
            deadline_s=self.deadline_s,
            max_output_tokens=self.max_output_tokens,
            max_reserved_usd=self.reservation_usd,
            retry_backoff_s=self.retry_backoff_s,
            default_effort="low",
        )


class ChatPeriods:
    """Picks a ledger period able to hold one turn's reservation; rotates instead of blocking."""

    def __init__(self, ledger: BudgetLedger, settings: Settings) -> None:
        self._ledger = ledger
        self._settings = settings
        self._lock = threading.Lock()
        self._index = 1

    def _open(self, index: int) -> UUID:
        s = self._settings
        period = self._ledger.ensure_period(
            f"{PERIOD_PREFIX}{index}",
            ledger_cap_usd=s.budget_ledger_cap_usd,
            warn_usd=s.budget_warn_usd,
            unattended_block_usd=s.budget_unattended_block_usd,
        )
        try:
            self._ledger.confirm_balance(period, s.budget_ledger_cap_usd, BALANCE_SOURCE)
        except ReservationStateError:
            pass  # already confirmed
        return period

    def acquire(self, need_usd: Decimal) -> UUID:
        with self._lock:
            for _ in range(MAX_PERIOD_ROTATIONS):
                period = self._open(self._index)
                status = self._ledger.status(period)
                if not status.paused and status.available_usd >= need_usd:
                    return period
                self._index += 1
            raise ReservationStateError("no chat ledger period could hold a reservation")

    def rotate(self) -> None:
        """The current period refused a reservation (race); move on."""
        with self._lock:
            self._index += 1


@dataclass
class ChatRuntime:
    factory: sessionmaker[Session]
    retrieval: RetrievalService | None
    series: SeriesService | None
    ledger: BudgetLedger
    periods: ChatPeriods
    provider: Provider | None
    model: str
    pricing_id: UUID | None
    pricing: Pricing | None
    limits: ChatLimits = field(default_factory=ChatLimits)
    unavailable_reason: str | None = None

    @property
    def live(self) -> bool:
        return (
            self.provider is not None and self.pricing is not None and self.pricing_id is not None
        )


def build_chat_runtime(
    factory: sessionmaker[Session],
    settings: Settings,
    retrieval: RetrievalService | None,
    series: SeriesService | None,
    *,
    meta: MetaContext | None = None,
    provider: Provider | None = None,
    limits: ChatLimits | None = None,
) -> ChatRuntime:
    """``provider`` is for tests (a stub with nominal rates). Otherwise the live Meta provider and
    owner-supplied rates are reused from the processing runtime; if they are absent the runtime is
    explicitly unavailable and every turn fails as a provider outage (never a fake success)."""
    ledger = BudgetLedger(factory)
    periods = ChatPeriods(ledger, settings)
    lim = limits or ChatLimits()
    if provider is not None:
        stub_pricing = Pricing(
            revision="chat-stub",
            model="stub-chat",
            input_usd_per_mtok=Decimal("1"),
            output_usd_per_mtok=Decimal("1"),
        )
        return ChatRuntime(
            factory,
            retrieval,
            series,
            ledger,
            periods,
            provider,
            stub_pricing.model,
            ledger.register_pricing(stub_pricing, "stub rates for tests"),
            stub_pricing,
            lim,
        )
    if meta is None:
        return ChatRuntime(
            factory,
            retrieval,
            series,
            ledger,
            periods,
            None,
            settings.meta_model,
            None,
            None,
            lim,
            "no live model is configured (MODEL_API_KEY and processing rates are required)",
        )
    return ChatRuntime(
        factory,
        retrieval,
        series,
        ledger,
        periods,
        meta.provider,
        meta.pricing.model,
        ledger.register_pricing(meta.pricing, "owner-supplied rates, reused for chat"),
        meta.pricing,
        lim,
    )

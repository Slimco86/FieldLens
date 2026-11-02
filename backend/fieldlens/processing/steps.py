"""Provider and step seams for processing runs (TASK-054).

The run machinery (estimate, confirm, lease, cancel, per-document state, budget stop) is real. What
happens to a page is a *step* (``ProcessingStep``) that reads pages through a *provider*. This
increment ships only the deterministic stub provider and the stub step: no network, no spend, no
extraction. TASK-055 replaces the step with classification and label-driven extraction and a
live provider only after the orchestrator authorizes live spend (PROCESSING_FLOW D7).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from fieldlens.config import Settings
from fieldlens.contracts.processing import ProcessingFailureCode

QUANT = Decimal("0.000001")
STUB_PRICING_SOURCE = "stub_illustrative"
STUB_STEP = "stub"


def quantize(value: Decimal) -> Decimal:
    return value.quantize(QUANT)


@dataclass(frozen=True)
class PageUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class PageFailure(Exception):
    """A typed page failure; the document becomes ``failed`` with this code (retryable)."""

    def __init__(
        self, code: ProcessingFailureCode, message: str, *, retryable: bool = True
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class RunStop(Exception):
    """Stop the whole run (cancel, lost lease or confirmed estimate exceeded)."""

    def __init__(self, code: ProcessingFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class DocumentTask:
    """What a step may know about one document of a run. Labels are hints, never evidence."""

    project_id: UUID
    run_id: UUID
    document_id: UUID
    source_revision_id: UUID
    storage_key: str
    page_count: int
    page_start: int
    page_end: int
    label_hints: tuple[str, ...]

    @property
    def pages(self) -> range:
        return range(self.page_start, self.page_end + 1)


@dataclass(frozen=True)
class Pricing:
    source: str
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return quantize(
            Decimal(input_tokens) * self.input_usd_per_mtok / Decimal(1_000_000)
            + Decimal(output_tokens) * self.output_usd_per_mtok / Decimal(1_000_000)
        )


class PageProvider(Protocol):
    name: str
    pricing: Pricing

    def read_page(self, task: DocumentTask, page: int) -> PageUsage:
        """Read one page; raise :class:`PageFailure` for refusal/truncation/provider errors."""
        ...


Checkpoint = Callable[[int, PageUsage], None]
"""``checkpoint(page, usage)`` records progress; it raises :class:`RunStop` to stop the run."""


class ProcessingStep(Protocol):
    """Seam for TASK-055: owns the page loop of one document and reports every page."""

    name: str

    @property
    def max_pages_per_document(self) -> int | None:
        """Pages of a document the step will read at most (``None``: the run's page cap only).
        The estimate stores and counts the window clipped to this, so spend never exceeds it."""
        ...

    def run_document(
        self, task: DocumentTask, provider: PageProvider, checkpoint: Checkpoint
    ) -> None: ...


class StubProvider:
    """Deterministic offline provider. Tests script failures and usage; it never spends."""

    name = "stub"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.pricing = Pricing(
            STUB_PRICING_SOURCE,
            settings.processing_stub_input_usd_per_mtok,
            settings.processing_stub_output_usd_per_mtok,
        )
        self.calls: list[tuple[UUID, int]] = []
        self.failures: dict[tuple[UUID, int], PageFailure] = {}
        self.crash_on: dict[tuple[UUID, int], BaseException] = {}
        self.usage_multiplier = Decimal(1)
        self.on_page: Callable[[DocumentTask, int], None] | None = None
        self._failing_once: set[tuple[UUID, int]] = set()

    def fail(
        self, document_id: UUID, page: int, failure: PageFailure, *, once: bool = False
    ) -> None:
        self.failures[(document_id, page)] = failure
        if once:
            self._failing_once.add((document_id, page))

    def read_page(self, task: DocumentTask, page: int) -> PageUsage:
        key = (task.document_id, page)
        self.calls.append(key)
        if self.on_page is not None:
            self.on_page(task, page)
        crash = self.crash_on.get(key)
        if crash is not None:
            raise crash
        failure = self.failures.get(key)
        if failure is not None:
            if key in self._failing_once:
                self._failing_once.discard(key)
                del self.failures[key]
            raise failure
        tokens_in = int(self._settings.processing_input_tokens_per_page * self.usage_multiplier)
        tokens_out = int(self._settings.processing_output_tokens_per_page * self.usage_multiplier)
        return PageUsage(tokens_in, tokens_out, self.pricing.cost(tokens_in, tokens_out))


@dataclass
class StubStep:
    """Reads every selected page through the provider and keeps nothing: no records, no
    candidates, no label. It proves the run/step seam and the state machine, not extraction."""

    name: str = STUB_STEP
    max_pages_per_document: int | None = None
    seen: list[UUID] = field(default_factory=list)

    def run_document(
        self, task: DocumentTask, provider: PageProvider, checkpoint: Checkpoint
    ) -> None:
        self.seen.append(task.document_id)
        for page in task.pages:
            checkpoint(page, provider.read_page(task, page))

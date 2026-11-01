"""Processing-run DTOs: estimate, separate confirmation, state, cancel and retry (TASK-054).

A processing run is persistent and project-scoped. It is created by an *estimate* (nothing is
spent, nothing is queued) and only starts after an explicit, separate *confirm*. Labels are hints
carried along for the later label-driven step (TASK-055); they are never a precondition and never
evidence. A stub-provider run produces no engineering data: it only exercises the run/step seam.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import ContractModel, UtcDatetime
from .imports import DocumentCategory, ExtractionState

MAX_PROCESSING_DOCUMENTS = 200


class ProcessingRoute(StrEnum):
    """OCR is deferred (PROCESSING_FLOW D8); every run uses the model route."""

    MODEL = "model"


class ProcessingProvider(StrEnum):
    STUB = "stub"
    """Deterministic, offline, never spends. The only provider wired in this increment."""


class ProcessingRunStatus(StrEnum):
    ESTIMATED = "estimated"
    """Created by an estimate; nothing queued, nothing spent. Needs an explicit confirm."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    """Every document was processed."""
    PARTIAL = "partial"
    """Some documents were processed, others failed or were cancelled (retryable)."""
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    """The worker stopped mid-run. Never shown as processed; retry needs a new confirm."""


class ProcessingDocumentState(StrEnum):
    ESTIMATED = "estimated"
    PENDING = "pending"
    RUNNING = "running"
    PROCESSED = "processed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class ProcessingFailureCode(StrEnum):
    PROVIDER_ERROR = "provider_error"
    PROVIDER_REFUSED = "provider_refused"
    PROVIDER_TRUNCATED = "provider_truncated"
    BUDGET_STOP = "budget_stop"
    CONFIRMED_ESTIMATE_EXCEEDED = "confirmed_estimate_exceeded"
    DOCUMENT_UNAVAILABLE = "document_unavailable"
    PAGE_COUNT_CHANGED = "page_count_changed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class ProcessingPageRange(ContractModel):
    """1-based inclusive page range; both ends are required together."""

    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> ProcessingPageRange:
        if self.page_end < self.page_start:
            raise ValueError("page_end must not precede page_start")
        return self


class ProcessingDocumentSelection(ContractModel):
    document_id: UUID
    pages: ProcessingPageRange | None = Field(
        default=None,
        description="Explicit range; required when the document has more than 500 pages.",
    )


class ProcessingEstimateRequest(ContractModel):
    documents: list[ProcessingDocumentSelection] = Field(
        min_length=1, max_length=MAX_PROCESSING_DOCUMENTS
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9._:-]+$",
        description="Replays return the same run; a different selection under it is a conflict.",
    )


class ProcessingConfirmRequest(ContractModel):
    estimated_usd: Decimal = Field(
        ge=0, description="Echo of the estimate being confirmed; a stale value is rejected."
    )


class ProcessingEstimate(ContractModel):
    pages: int = Field(ge=0)
    route: ProcessingRoute
    provider: ProcessingProvider
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    estimated_usd: Decimal = Field(ge=0)
    pricing_source: str = Field(
        description="Where the rates come from; 'stub_illustrative' is never an owner rate card."
    )
    total_cap_usd: Decimal = Field(description="Aggregate live-spend cap (PROCESSING_FLOW D7).")
    remaining_budget_usd: Decimal = Field(
        ge=0,
        description="Cap minus ledger spend and minus other confirmed, unfinished estimates.",
    )
    fits_budget: bool
    confirmable: bool = Field(
        description="True while the run is in the estimated state and the estimate fits the budget."
    )


class ProcessingRunDocument(ContractModel):
    document_id: UUID
    source_revision_id: UUID
    original_filename: str
    ordinal: int = Field(ge=0)
    state: ProcessingDocumentState
    page_count: int = Field(ge=0, description="Pages in the whole document.")
    pages: ProcessingPageRange = Field(description="Pages this run reads.")
    pages_done: int = Field(ge=0)
    label_hints: list[DocumentCategory] = Field(
        default_factory=list, description="User labels at estimate time; hints, not evidence."
    )
    estimated_usd: Decimal = Field(ge=0)
    actual_usd: Decimal = Field(ge=0)
    failure_code: ProcessingFailureCode | None = None
    failure_message: str | None = None
    retryable: bool = False
    finished_at: UtcDatetime | None = None


class ProcessingRun(ContractModel):
    run_id: UUID
    project_id: UUID
    status: ProcessingRunStatus
    step: str = Field(description="Step that processes each document; 'stub' produces no data.")
    cancel_requested: bool = False
    retry_of_run_id: UUID | None = None
    estimate: ProcessingEstimate
    confirmed_usd: Decimal | None = None
    actual_usd: Decimal = Field(ge=0)
    attempt_no: int = Field(ge=0)
    error_code: ProcessingFailureCode | None = None
    error_message: str | None = None
    documents: list[ProcessingRunDocument]
    created_at: UtcDatetime
    confirmed_at: UtcDatetime | None = None
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None


class ProcessingRunSummary(ContractModel):
    run_id: UUID
    status: ProcessingRunStatus
    provider: ProcessingProvider
    document_count: int = Field(ge=0)
    processed_count: int = Field(ge=0)
    estimated_usd: Decimal = Field(ge=0)
    actual_usd: Decimal = Field(ge=0)
    created_at: UtcDatetime
    finished_at: UtcDatetime | None = None


class ProcessingRunPage(ContractModel):
    items: list[ProcessingRunSummary]


class DocumentProcessingStatus(StrEnum):
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    PROCESSED = "processed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class DocumentProcessingState(ContractModel):
    """Honest per-document view: what the native pipeline did and what processing can do now."""

    document_id: UUID
    original_filename: str
    page_count: int | None = Field(
        default=None, ge=0, description="Null when the file is not a readable PDF."
    )
    native_state: ExtractionState
    no_native_parser: bool = Field(
        description="True when no native profile matched; model processing is available."
    )
    state_text: str = Field(
        description="Plain-language state, e.g. 'no native parser; model processing available, "
        "not started'."
    )
    processable: bool = Field(description="True when a processing run can be estimated now.")
    not_processable_reason: str | None = None
    over_page_cap: bool = Field(
        default=False, description="True when a page range is required (more than 500 pages)."
    )
    user_labels: list[DocumentCategory] = Field(default_factory=list)
    processing_status: DocumentProcessingStatus
    last_run_id: UUID | None = None
    retryable: bool = False


class DocumentProcessingStateList(ContractModel):
    project_id: UUID
    source_revision_id: UUID | None = None
    items: list[DocumentProcessingState]

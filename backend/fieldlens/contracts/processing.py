"""Processing-run DTOs: estimate, separate confirmation, state, cancel and retry (TASK-054).

A processing run is persistent and project-scoped. It is created by an *estimate* (nothing is
spent, nothing is queued) and only starts after an explicit, separate *confirm*. Labels are hints
carried along for the later label-driven step (TASK-055); they are never a precondition and never
evidence. A stub-provider run produces no engineering data: it only exercises the run/step seam.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal
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
    """Deterministic, offline, never spends. The default; a stub run produces no data."""
    META = "meta"
    """Live Meta model step. Selected only by explicit configuration; spend goes to the ledger."""


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
    PROVIDER_MALFORMED = "provider_malformed"
    """Output was not the closed JSON schema (retryable; no partial rows are stored)."""
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
    force: bool = Field(
        default=False,
        description="True bypasses the stored-result cache: the provider is called again and a "
        "NEW result is stored (earlier results stay as history). The estimate is the full price "
        "either way and never assumes a cache hit; it is part of the confirmed run. False reuses "
        "the stored result of an unchanged document with zero provider calls.",
    )


class ProcessingConfirmRequest(ContractModel):
    estimated_usd: Decimal = Field(
        ge=0,
        le=1_000_000,
        max_digits=14,
        decimal_places=6,
        allow_inf_nan=False,
        description="Echo of the estimate being confirmed; a stale value is rejected.",
    )


class ProcessingEstimate(ContractModel):
    pages: int = Field(ge=0)
    route: ProcessingRoute
    provider: ProcessingProvider
    model: str | None = Field(
        default=None,
        description="Model that will run ('stub' for the stub provider); null on runs created "
        "before the model was recorded.",
    )
    spends_money: bool = Field(
        default=False, description="True when confirming this run can spend provider budget."
    )
    force: bool = Field(
        default=False, description="The run bypasses the cache (a deliberate fresh read)."
    )
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
    cache_hit: bool = Field(
        default=False,
        description="True when the stored model result for this document, page window and "
        "prompt/schema version was reused: zero provider calls, zero spend.",
    )
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


class IdentitySubjectKind(StrEnum):
    WELL = "well"
    WELLBORE = "wellbore"


class IdentityResolution(StrEnum):
    LINKED = "linked"
    """The normalized name equals an existing wellbore key exactly."""
    UNRESOLVED = "unresolved"
    """No exact key match (a near miss stays here); left for merge review."""


class ModelReadWarningCode(StrEnum):
    NO_WELLBORE_IDENTITY = "no_wellbore_identity"
    """Non-blocking: 'no wellbore identity found'; the document keeps its category and tags."""
    IDENTITY_QUOTE_NOT_FOUND = "identity_quote_not_found"
    """A proposed identity was dropped: its quote was not in the page text the model read."""
    IDENTITY_INVALID = "identity_invalid"
    """A proposed identity was dropped: unknown kind, page not read, or name not in the quote."""
    NO_TEXT_LAYER = "no_text_layer"
    """The pages read had no text layer; nothing was sent to the model (OCR is not available)."""


class ModelReadWarning(ContractModel):
    code: ModelReadWarningCode
    message: str
    count: int = Field(default=1, ge=1)


class DocumentIdentityProposal(ContractModel):
    """One wellbore/well identity the model read. A proposal, never an accepted fact."""

    proposal_id: UUID
    subject_kind: IdentitySubjectKind
    name_as_written: str
    normalized_key: str | None = Field(
        default=None, description="Canonical bore key when the name parses; null otherwise."
    )
    page: int = Field(ge=1, description="1-based page of the document the quote is on.")
    quote: str = Field(description="Verbatim text from that page (checked server-side).")
    status: Literal["model_proposal"] = "model_proposal"
    label: str = "Model-read, unverified"
    resolution: IdentityResolution
    wellbore_id: UUID | None = None
    wellbore_key: str | None = None


class DocumentModelRead(ContractModel):
    """What the model step recorded for one document (suggestion, never the user's label)."""

    document_id: UUID
    run_id: UUID = Field(description="Run that produced this result (a cache hit reuses it).")
    category: DocumentCategory = Field(
        description="Suggested category; 'general_report' with unclassified=true on fallback."
    )
    unclassified: bool
    tags: list[str]
    identities: list[DocumentIdentityProposal]
    warnings: list[ModelReadWarning]
    pages: ProcessingPageRange = Field(description="Page window the model was given.")
    pages_read: int = Field(ge=0)
    provider: ProcessingProvider
    model_revision: str
    prompt_version: str
    schema_version: str
    extraction_method: Literal["model_classification"] = "model_classification"
    label: str = "Model-read, unverified"
    created_at: UtcDatetime


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
    model_read: DocumentModelRead | None = Field(
        default=None,
        description="Latest model-read result for this document; null until a model run stored "
        "one. A user label always wins over model_read.category.",
    )


class ProviderStatus(StrEnum):
    STUB = "stub"
    """The stub is active (the default): no model is called, nothing is extracted, nothing spent."""
    LIVE = "live"
    """The live provider is active and fully configured."""
    PROVIDER_MISCONFIGURED = "provider_misconfigured"
    """The live provider was requested but items are missing; the app runs on the stub and
    estimate/confirm/retry requests are refused with a 409 ``provider_misconfigured``."""


class ProcessingProviderInfo(ContractModel):
    """Which provider processing uses and why. Item names only: never a secret or any value."""

    requested: ProcessingProvider = Field(description="The processing provider as requested.")
    active: ProcessingProvider = Field(description="Provider that would run now.")
    model: str = Field(description="Model name that would run; 'stub' for the stub provider.")
    status: ProviderStatus
    missing: list[str] = Field(
        default_factory=list,
        description="Names of the missing settings when status is provider_misconfigured.",
    )
    spends_money: bool
    message: str


class DocumentProcessingStateList(ContractModel):
    project_id: UUID
    source_revision_id: UUID | None = None
    items: list[DocumentProcessingState]
    provider_info: ProcessingProviderInfo


MODEL_REPLY_MAX_BYTES = 8192


class ModelReplyRaw(ContractModel):
    """The provider's text as stored: untrusted data, plain text only, never HTML."""

    text: str
    truncated: bool = Field(description="True when the stored text is cut at max_bytes.")
    max_bytes: int = MODEL_REPLY_MAX_BYTES


class ModelRunEntry(ContractModel):
    """One processing run of one document, for the outcome history (newest first)."""

    run_id: UUID
    state: ProcessingDocumentState
    provider: ProcessingProvider
    model: str | None = None
    forced: bool = Field(description="The run bypassed the cache (a deliberate fresh read).")
    created_at: UtcDatetime
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    pages: ProcessingPageRange
    pages_read: int = Field(ge=0)
    input_tokens: int | None = None
    output_tokens: int | None = None
    usd_actual: Decimal = Field(ge=0)
    cache_hit: bool
    failure_code: ProcessingFailureCode | None = None
    failure_message: str | None = None
    warnings: list[ModelReadWarning] = Field(default_factory=list)
    message: str | None = Field(
        default=None,
        description="Set for a stub run: that no model was called and nothing was extracted.",
    )


class DocumentModelOutcome(ContractModel):
    """Run history plus the current stored model read of one document."""

    document_id: UUID
    runs: list[ModelRunEntry] = Field(description="Newest first; at most 50.")
    current: DocumentModelRead | None = Field(
        default=None, description="The latest stored result by time (null until one exists)."
    )
    raw_reply: ModelReplyRaw | None = Field(
        default=None, description="Bounded raw reply of the current result, when recorded."
    )

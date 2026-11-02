"""Per-wellbore reconstruction run DTOs (TASK-068, RECONSTRUCTION_RUN.md RR-1..RR-5).

A reconstruction run belongs to one ready wellbore and has four stage rows: S1 gather and S4 assemble
are deterministic over stored exposure and gate data; S2 extract and S3 identify are agent stages
that report ``not_available`` (with a stable reason code) until their agent step exists. A run with
any unavailable stage is ``partial``, never ``succeeded``. An *estimate* spends nothing and queues
nothing; only a separate confirm queues the runs. The draft summary lists coverage, unresolved items
and conflicts with source references only: it carries no engineering value without a source, no
publication and no 3D claim. Costs are labelled stub planning rates; no live model call exists.
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .base import ContractModel, FiniteJsonValue, UtcDatetime

MAX_RECONSTRUCTION_WELLBORES = 200


class ReconstructionStageName(StrEnum):
    GATHER = "gather"
    """S1: deterministic; revalidates the start gate for the wellbore."""
    EXTRACT = "extract"
    """S2: agent, label-driven document extraction (TASK-055); pages capped at 500."""
    IDENTIFY = "identify"
    """S3: agent plus deterministic identity merge proposals; proposed only, never accepted."""
    ASSEMBLE = "assemble"
    """S4: deterministic draft summary; no publication."""


class ReconstructionStageKind(StrEnum):
    DETERMINISTIC = "deterministic"
    AGENT = "agent"


class ReconstructionStageState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    NOT_AVAILABLE = "not_available"
    """No implementation exists for this stage yet; nothing ran and nothing was produced."""
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    SKIPPED = "skipped"
    """Not started because an earlier stage failed or the run was cancelled."""


class ReconstructionRunStatus(StrEnum):
    ESTIMATED = "estimated"
    """Created by an estimate; nothing queued, nothing spent."""
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    """Every stage ran and succeeded."""
    PARTIAL = "partial"
    """No stage failed but at least one stage is not_available; the output is a draft."""
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    """The worker stopped mid-run. Never shown as succeeded; retry needs a new confirm."""


class ReconstructionStage(ContractModel):
    stage: ReconstructionStageName
    ordinal: int = Field(ge=1, le=4, description="S1..S4.")
    kind: ReconstructionStageKind
    state: ReconstructionStageState
    reason_code: str | None = Field(
        default=None,
        description="Stable code for not_available/skipped, e.g. agent_step_not_implemented.",
    )
    message: str | None = None
    counts: dict[str, int] = Field(default_factory=dict, description="Exact stage counters.")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    actual_usd: Decimal = Field(default=Decimal(0), ge=0)
    error_code: str | None = None
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None


class ReconstructionEvidenceRef(ContractModel):
    """A source reference: document plus the stored locator. Never a value."""

    document_id: UUID
    filename: str | None = None
    record_kind: str | None = None
    locator: dict[str, FiniteJsonValue]


class ReconstructionCoverage(ContractModel):
    category: str
    present: bool
    record_count: int = Field(ge=0)
    conflicting_record_count: int = Field(ge=0)
    accepted_candidate_count: int = Field(ge=0)
    open_candidate_count: int = Field(ge=0)
    gap_reasons: list[str]
    evidence: list[ReconstructionEvidenceRef] = Field(
        description="Bounded source references; empty only when present is false."
    )
    evidence_truncated: bool = False


class ReconstructionUnresolved(ContractModel):
    kind: Literal[
        "unresolved_identity",
        "pending_merge_proposal",
        "warning",
        "unlocated_surface",
        "open_candidates",
    ]
    code: str
    message: str
    scope: Literal["wellbore", "project"] = "wellbore"
    count: int | None = Field(default=None, ge=0)
    reference_id: UUID | None = Field(
        default=None, description="E.g. the merge proposal id the user must review."
    )
    evidence: list[ReconstructionEvidenceRef] = Field(default_factory=list)


class ReconstructionConflict(ContractModel):
    category: str
    code: str
    severity: str
    message: str
    evidence: list[ReconstructionEvidenceRef]


class ReconstructionSummary(ContractModel):
    """Draft from S4. States what ran, what did not, and what remains unresolved."""

    wellbore_id: UUID
    wellbore_name: str
    draft: Literal[True] = True
    published: Literal[False] = False
    scene_3d: Literal["not_generated"] = "not_generated"
    stages_succeeded: list[ReconstructionStageName]
    stages_not_available: list[ReconstructionStageName]
    stages_failed: list[ReconstructionStageName]
    coverage: list[ReconstructionCoverage]
    unresolved: list[ReconstructionUnresolved]
    conflicts: list[ReconstructionConflict]
    actual_usd: Decimal = Field(ge=0)
    note: str


class ReconstructionRun(ContractModel):
    run_id: UUID
    project_id: UUID
    estimate_id: UUID
    well_id: UUID
    wellbore_id: UUID
    wellbore_name: str
    status: ReconstructionRunStatus
    source_revision: str = Field(
        description="Digest of the wellbore's record groups; a changed source is a new revision."
    )
    retry_of_run_id: UUID | None = None
    stages: list[ReconstructionStage] = Field(description="Always S1..S4, in order.")
    provider: Literal["stub"] = "stub"
    pricing_source: str
    estimated_usd: Decimal = Field(ge=0)
    confirmed_usd: Decimal | None = None
    actual_usd: Decimal = Field(ge=0)
    cancel_requested: bool = False
    retryable: bool = Field(
        description="True for failed, cancelled and interrupted runs; a retry is a new estimate."
    )
    error_code: str | None = None
    error_message: str | None = None
    summary: ReconstructionSummary | None = None
    created_at: UtcDatetime
    confirmed_at: UtcDatetime | None = None
    started_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None


class ReconstructionRunPage(ContractModel):
    items: list[ReconstructionRun]
    total: int = Field(ge=0)


class ReconstructionEstimateRequest(ContractModel):
    wellbore_ids: list[UUID] | None = Field(default=None, max_length=MAX_RECONSTRUCTION_WELLBORES)
    all_ready: bool = Field(
        default=False, description="Every wellbore of the project that passes the start gate."
    )

    @model_validator(mode="after")
    def _one_selection(self) -> ReconstructionEstimateRequest:
        if self.all_ready == (self.wellbore_ids is not None):
            raise ValueError("send either wellbore_ids or all_ready=true")
        if self.wellbore_ids is not None:
            if not self.wellbore_ids:
                raise ValueError("wellbore_ids must not be empty")
            if len(set(self.wellbore_ids)) != len(self.wellbore_ids):
                raise ValueError("a wellbore can be selected once")
        return self


class ReconstructionConfirmRequest(ContractModel):
    estimated_usd: Decimal = Field(
        description="Echo of the estimate's total; a mismatch is a conflict and queues nothing."
    )


class ReconstructionStageEstimate(ContractModel):
    stage: ReconstructionStageName
    kind: ReconstructionStageKind
    availability: Literal["will_run", "not_available"]
    reason_code: str | None = None
    estimated_usd: Decimal = Field(
        ge=0,
        description="Stub planning rate reserved against the cap; spent only if the stage runs.",
    )
    page_cap: int | None = Field(
        default=None, description="S2 only: the page cap that will bound its scope (500)."
    )


class ReconstructionEstimateItem(ContractModel):
    wellbore_id: UUID
    wellbore_name: str
    already_active: bool = Field(
        description="True: this wellbore and source revision already has a queued or running run; "
        "run_id is that run and nothing new is estimated for it."
    )
    run_id: UUID
    run_status: ReconstructionRunStatus
    source_revision: str
    stages: list[ReconstructionStageEstimate]
    estimated_usd: Decimal = Field(ge=0)


class ReconstructionEstimate(ContractModel):
    estimate_id: UUID | None = Field(
        default=None, description="None when every selected wellbore already has an active run."
    )
    project_id: UUID
    items: list[ReconstructionEstimateItem] = Field(description="The per-wellbore split.")
    total_estimated_usd: Decimal = Field(ge=0)
    provider: Literal["stub"] = "stub"
    pricing_source: str
    pricing_label: str
    live_calls: Literal[False] = False
    total_cap_usd: Decimal
    remaining_budget_usd: Decimal
    fits_budget: bool
    confirmable: bool
    confirmed: bool = False

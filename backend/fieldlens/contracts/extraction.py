"""Extraction (native source profile) DTOs for source inspection (TASK-009, IN-2/IN-6).

Records are source observations with attribute-level evidence. Nothing here is an accepted
claim: values keep their original text, unit and reference, and ``validation_state`` stays
``unreviewed`` unless a profile proved the value invalid or conflicting."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from .base import ContractModel, UtcDatetime
from .context import PageInfo, SourceEventTime
from .evidence import Coverage, EvidenceLink, ValidationState
from .quality import QualityIssue


class ExtractionStatus(StrEnum):
    """Run outcome. Only ``succeeded``/``partial`` hold records; ``interrupted`` never counts."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    UNSUPPORTED = "unsupported"


class UnitStatus(StrEnum):
    STATED = "stated"
    NOT_APPLICABLE = "not_applicable"
    MISSING = "missing"


class ExtractedAttribute(ContractModel):
    key: str = Field(min_length=1)
    original_text: str | None = None
    number: float | None = None
    text: str | None = None
    unit: str | None = None
    unit_status: UnitStatus
    reference: str | None = None
    unknown_reason: str | None = None
    normalized_number: float | None = None
    normalized_unit: str | None = None
    validation_state: ValidationState
    evidence: EvidenceLink


class ExtractedRecord(ContractModel):
    record_id: UUID
    ordinal: int = Field(ge=0)
    kind: str = Field(min_length=1)
    subject: dict[str, str | None]
    effective_time: SourceEventTime | None = None
    report_time: SourceEventTime | None = None
    validation_state: ValidationState
    evidence: EvidenceLink
    attributes: list[ExtractedAttribute]


class ExtractedRecordPage(ContractModel):
    items: list[ExtractedRecord]
    page: PageInfo
    total: int = Field(ge=0)


class ExtractionError(ContractModel):
    code: str
    message: str
    process: str | None = None
    """Writing process (host, pid, lane, root id) for ``source_missing`` failures."""


class WellboreIdentity(ContractModel):
    """A wellbore label exactly as a source wrote it, with the parent well key kept separate.

    ``well_key`` is only a grouping hint derived from the label; it never merges wellbores."""

    wellbore_label: str
    well_key: str | None = None
    record_kinds: list[str] = Field(default_factory=list)


class ExtractionReport(ContractModel):
    """Profile, parse status, coverage and data-quality findings for one document."""

    project_id: UUID
    document_id: UUID
    source_revision_id: UUID
    run_id: UUID | None = None
    status: ExtractionStatus | None = Field(
        default=None, description="Null when no extraction run exists yet."
    )
    profile_name: str | None = None
    profile_version: str | None = None
    method: str | None = None
    content_sha256: str | None = None
    stale: bool = Field(
        default=False, description="True when the profile version changed since this run."
    )
    attempt_no: int = Field(default=0, ge=0)
    coverage: Coverage | None = None
    record_counts: dict[str, int] = Field(default_factory=dict)
    wellbores: list[str] = Field(
        default_factory=list, description="Wellbore labels as written; never collapsed."
    )
    wellbore_identities: list[WellboreIdentity] = Field(default_factory=list)
    coverage_notes: list[str] = Field(
        default_factory=list,
        description="What the extraction does not provide (explicit gaps), per wellbore.",
    )
    issues: list[QualityIssue] = Field(default_factory=list)
    error: ExtractionError | None = None
    queued_at: UtcDatetime | None = None
    finished_at: UtcDatetime | None = None
    detail: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RequeueOutcome(StrEnum):
    QUEUED = "queued"
    UNCHANGED = "unchanged"


class ExtractionRequeue(ContractModel):
    outcome: RequeueOutcome
    report: ExtractionReport

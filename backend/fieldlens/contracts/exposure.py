"""Per-wellbore, per-category data exposure and the deterministic start gate (TASK-056, PF-6/PF-8).

Read-only views over records already stored for one project: nothing here is a new fact. Every
group and attribute carries the source locator and its own validation state; model proposals are
listed apart from source records and are only ``is_accepted_fact`` when a validator accepted them.
Planned and as-built trajectories are never merged: each trajectory group names its survey status.

The gate (PROCESSING_FLOW D4/D5) is a pure function of the stored rows: a validated trajectory for
at least one well+wellbore is the only blocker; a missing surface location is a warning and an
``unlocated`` flag (the local display origin itself belongs to TASK-058)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import ContractModel, FiniteJsonValue

ExposureCategoryName = Literal[
    "trajectory",
    "surface_location",
    "logs",
    "production",
    "equipment_completion",
    "perforations",
    "other",
]
SurveyStatus = Literal["planned", "as_built", "unstated", "conflicting", "not_applicable"]
FindingKind = Literal["conflict", "gap", "finding"]


class ExposureAttribute(ContractModel):
    key: str
    original_text: str | None = None
    number: float | None = None
    unit: str | None = None
    reference: str | None = None
    unknown_reason: str | None = None
    validation_state: str
    locator: dict[str, FiniteJsonValue] = Field(
        description="Attribute-level source locator (page/table/cell/line/column as stored), "
        "with the document id."
    )


class ExposureRecord(ContractModel):
    record_id: UUID
    ordinal: int = Field(ge=0)
    kind: str
    validation_state: str
    locator: dict[str, FiniteJsonValue]
    attributes: list[ExposureAttribute]
    attributes_truncated: bool = False


class ExposureGroup(ContractModel):
    """Records of one kind from one document run (bounded sample; counts are exact)."""

    document_id: UUID
    run_id: UUID
    filename: str
    profile_name: str | None = None
    kind: str
    evidence_class: Literal["source_record"] = "source_record"
    record_count: int = Field(ge=0)
    validation_counts: dict[str, int]
    survey_status: SurveyStatus | None = Field(
        default=None,
        description="Trajectory groups only: the survey status the source states. 'unstated' "
        "means the profile looked for it and the source does not say; 'not_applicable' means "
        "the format has no such statement.",
    )
    sample: list[ExposureRecord]
    sample_truncated: bool = Field(description="True when record_count exceeds the sample.")


class ExposureProposal(ContractModel):
    """A model-proposed candidate attached to the wellbore. Never a source record."""

    candidate_id: UUID
    document_id: UUID
    state: str
    validation_state: str
    evidence_class: str
    label: str
    attribute_kind: str | None = None
    locator: dict[str, FiniteJsonValue]
    is_accepted_fact: bool = Field(
        description="True only for state 'accepted' with validation 'valid'; everything else "
        "is an open or rejected proposal and must not be shown as a fact."
    )


class ExposureFinding(ContractModel):
    issue_id: UUID
    code: str
    severity: str
    kind: FindingKind
    message: str
    run_id: UUID
    document_id: UUID
    scope: Literal["record", "document"] = Field(
        description="'record': the issue names records linked to this wellbore; 'document': the "
        "issue names none and applies to the document run as a whole."
    )
    attribute_keys: list[str]
    blocked_operations: list[str]
    locators: list[dict[str, FiniteJsonValue]]


class CategoryExposure(ContractModel):
    category: ExposureCategoryName
    present: bool = Field(description="False: no record or proposal; an explicit gap.")
    record_count: int = Field(ge=0)
    conflicting_record_count: int = Field(ge=0)
    groups: list[ExposureGroup]
    proposals: list[ExposureProposal]
    proposal_total: int = Field(ge=0)
    accepted_proposal_count: int = Field(ge=0)
    conflicts: list[ExposureFinding]
    gaps: list[ExposureFinding]
    findings: list[ExposureFinding]
    findings_total: int = Field(
        ge=0, description="Exact count of conflicts + gaps + findings before the per-list cap."
    )
    findings_truncated: bool = Field(
        description="True when findings_total exceeds the entries returned in the three lists."
    )
    proposals_truncated: bool = Field(
        description="True when proposal_total exceeds the entries returned in proposals; "
        "proposal_total and accepted_proposal_count are exact counts."
    )
    gap_reasons: list[str] = Field(
        description="Machine-readable codes, e.g. NO_RECORDS, NO_VALIDATED_TRAJECTORY."
    )


class GateReason(ContractModel):
    code: str
    message: str
    wellbore_id: UUID | None = Field(
        default=None, description="Set when the reason concerns one wellbore."
    )


class TrajectorySetCheck(ContractModel):
    """Deterministic validity of one trajectory station set (one document run)."""

    document_id: UUID
    run_id: UUID
    filename: str
    survey_status: SurveyStatus
    station_count: int = Field(ge=0)
    usable_station_count: int = Field(ge=0)
    validated: bool
    reasons: list[GateReason] = Field(description="Why the set is not validated; empty if it is.")


class WellboreGate(ContractModel):
    well_id: UUID
    wellbore_id: UUID
    wellbore_name: str
    trajectory_validated: bool
    trajectory_sets: list[TrajectorySetCheck]
    unmet: list[GateReason] = Field(description="Why this wellbore does not satisfy the gate.")
    location_state: Literal["located", "unlocated"]
    unlocated: bool = Field(
        description="True when no sourced surface location exists (warning only; display origin "
        "is TASK-058)."
    )
    warnings: list[GateReason]


class GateCondition(ContractModel):
    code: str
    met: bool
    message: str


class StartGate(ContractModel):
    project_id: UUID
    gate_version: str
    can_start: bool
    conditions: list[GateCondition]
    unmet: list[GateReason] = Field(description="Exactly the unmet conditions, for the UI.")
    warnings: list[GateReason]
    qualifying_wellbore_ids: list[UUID]
    wellbores: list[WellboreGate]


class WellboreExposure(ContractModel):
    project_id: UUID
    well_id: UUID
    wellbore_id: UUID
    wellbore_name: str
    categories: list[CategoryExposure] = Field(description="Always all categories, fixed order.")
    gate: WellboreGate


class WellExposure(ContractModel):
    well_id: UUID
    name: str
    wellbores: list[WellboreExposure]


class ProjectExposure(ContractModel):
    project_id: UUID
    resolver_version: str
    resolved_current: bool
    unresolved_record_count: int = Field(ge=0)
    wells: list[WellExposure]
    gate: StartGate

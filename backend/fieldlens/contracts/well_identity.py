"""Resolved well/wellbore identity read contracts (TASK-046, DC-4..DC-6).

Identities are derived deterministically from the structured record subjects of one project
(rule: ``fieldlens.identity.labels``). They are source-derived names, not engineering truth: a
``parent_wellbore_id`` is a naming-based link (``F-11 B`` -> ``F-11``), not a verified drilling
relationship, and a record is linked only when its labels resolve unambiguously."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import ContractModel, FiniteJsonValue
from .exposure import WellboreExposure


class IdentityKindCount(ContractModel):
    kind: str
    records: int = Field(ge=0)


class ResolvedWellbore(ContractModel):
    wellbore_id: UUID
    well_id: UUID
    name: str = Field(description="Canonical name, e.g. '15/9-F-11 B'.")
    suffix: str | None = Field(default=None, description="None for the well's base wellbore.")
    parent_wellbore_id: UUID | None = None
    parent_basis: Literal["name_suffix"] | None = Field(
        default=None, description="Why the parent link exists: the suffix of the base name."
    )
    record_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    record_counts: list[IdentityKindCount] = Field(default_factory=list)


class ResolvedWell(ContractModel):
    well_id: UUID
    name: str = Field(description="Canonical block-qualified name, e.g. '15/9-F-11'.")
    record_count: int = Field(ge=0)
    document_count: int = Field(ge=0)
    wellbores: list[ResolvedWellbore]


class UnresolvedIdentityGroup(ContractModel):
    reason: Literal["not_a_well", "unqualified_label", "ambiguous"]
    detail: str
    labels: list[str] = Field(description="Distinct source labels (bounded).")
    record_count: int = Field(ge=0)
    document_count: int = Field(ge=0)


class IdentityListing(ContractModel):
    project_id: UUID
    resolver_version: str
    wells: list[ResolvedWell]
    linked_record_count: int = Field(ge=0)
    unresolved_record_count: int = Field(ge=0)
    unresolved: list[UnresolvedIdentityGroup]
    resolved_current: bool = Field(
        description="True when the stored rows match what the current extraction output "
        "resolves to (false: run POST resolve)."
    )


class IdentityResolveOutcome(ContractModel):
    wells: int = Field(ge=0)
    wellbores: int = Field(ge=0)
    linked_records: int = Field(ge=0)
    unresolved_records: int = Field(ge=0)
    identity_findings: int = Field(ge=0, description="IDENTITY_MISMATCH findings written.")
    range_findings: int = Field(ge=0, description="SUSPICIOUS_VALUE depth-range findings.")


class WellboreEvidenceDocument(ContractModel):
    document_id: UUID
    run_id: UUID
    filename: str
    profile_name: str | None = None
    profile_version: str | None = None
    record_count: int = Field(ge=0)
    record_counts: list[IdentityKindCount]
    first_record_ordinal: int = Field(ge=0)
    first_record_locator: dict[str, FiniteJsonValue]


class WellboreEvidence(ContractModel):
    project_id: UUID
    wellbore: ResolvedWellbore
    documents: list[WellboreEvidenceDocument]
    exposure: WellboreExposure = Field(
        description="Records of this wellbore grouped per category with locators, validation "
        "state, gaps/conflicts and its start-gate verdict (TASK-056)."
    )

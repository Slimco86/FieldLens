"""Shared QualityIssue contract (see docs/specs/DATA_QUALITY.md)."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, model_validator

from .base import ContractModel, UtcDatetime
from .context import EvidenceContext, SourceContext
from .evidence import Coverage, EvidenceLink


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class BlockedOperation(StrEnum):
    CLAIM_ACCEPTANCE = "claim_acceptance"
    PLACEMENT = "placement"
    PHYSICAL_GEOMETRY = "physical_geometry"
    CALCULATION = "calculation"
    TEMPORAL_STATE = "temporal_state"


class IssueCode(StrEnum):
    """Registered codes. New producer codes require a shared-contract change."""

    MISSING_EQUIPMENT_DIMENSIONS = "MISSING_EQUIPMENT_DIMENSIONS"
    UNKNOWN_PLACEMENT = "UNKNOWN_PLACEMENT"
    REFERENCE_CONFLICT = "REFERENCE_CONFLICT"
    INTERVAL_CONFLICT = "INTERVAL_CONFLICT"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    DIMENSION_CONFLICT = "DIMENSION_CONFLICT"
    TEMPORAL_AMBIGUITY = "TEMPORAL_AMBIGUITY"
    HISTORY_INCOMPLETE = "HISTORY_INCOMPLETE"
    EXTRACTION_PARTIAL = "EXTRACTION_PARTIAL"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    GENERIC_REPRESENTATION = "GENERIC_REPRESENTATION"
    # TASK-009 native profiles
    MISSING_REFERENCE = "MISSING_REFERENCE"
    MISSING_UNIT = "MISSING_UNIT"
    SUSPICIOUS_VALUE = "SUSPICIOUS_VALUE"
    UNKNOWN_CODE = "UNKNOWN_CODE"
    ASSEMBLY_TYPE_MISMATCH = "ASSEMBLY_TYPE_MISMATCH"


class QualityIssue(ContractModel):
    """Severity is independent of validation state, evidence class and blocking."""

    issue_id: UUID
    context: EvidenceContext
    code: IssueCode
    severity: IssueSeverity
    message: str = Field(min_length=1)
    record_ids: list[UUID] = Field(default_factory=list)
    claim_ids: list[UUID] = Field(default_factory=list)
    entity_ids: list[UUID] = Field(default_factory=list)
    attribute_keys: list[str] = Field(default_factory=list)
    evidence_links: list[EvidenceLink] = Field(default_factory=list)
    coverage: Coverage | None = None
    blocked_operations: list[BlockedOperation] = Field(default_factory=list)
    producer_name: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)
    producer_key: str = Field(min_length=1, description="Revision-local idempotency key.")
    created_at: UtcDatetime
    predecessor_issue_id: UUID | None = None

    @model_validator(mode="after")
    def _scoped(self) -> QualityIssue:
        if len(set(self.blocked_operations)) != len(self.blocked_operations):
            raise ValueError("blocked_operations must be unique")
        ctx = self.context.root
        if isinstance(ctx, SourceContext):
            if self.claim_ids:
                raise ValueError("a source-context issue cannot reference accepted claims")
            for link in self.evidence_links:
                rev = link.source_revision_id
                if rev is not None and rev != ctx.source_revision_id:
                    raise ValueError("evidence link is outside the issue's source revision")
        if self.predecessor_issue_id == self.issue_id:
            raise ValueError("an issue cannot supersede itself")
        return self

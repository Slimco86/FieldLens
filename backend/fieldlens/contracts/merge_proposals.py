"""Identity-merge proposal contracts (TASK-057, PF-7; spec: docs/specs/MERGE_PROPOSALS.md).

A proposal says that source names denote an already identified wellbore. It is a *proposal*: the
model suggested it, deterministic guards and server-side quote checks validated it, and only a user
decision changes identity. ``blocked`` proposals failed a deterministic guard and cannot be
accepted."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import MAX_PAGE_LIMIT, ContractModel, UtcDatetime


class MergeProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    REVERTED = "reverted"
    BLOCKED = "blocked"
    """Failed a deterministic guard; can only be rejected."""


class MergeGuardResult(ContractModel):
    code: str = Field(description="g1_scope .. g7_evidence.")
    passed: bool
    detail: str = Field(description="Short, non-sensitive explanation.")


class MergeEvidenceQuote(ContractModel):
    document_id: UUID
    content_sha256: str = Field(description="Hash of the document when the quote was verified.")
    quote: str = Field(
        description="Verbatim text found in the document by the server, or for `survey_match` "
        "the server-composed statement of the deterministic survey comparison."
    )
    evidence_kind: Literal["quote", "survey_match"] = Field(
        default="quote",
        description="`quote`: verbatim passage naming both spellings. `survey_match`: both "
        "names' surveys are identical (station count, MD range, md/incl/azi hash).",
    )


class MergeProposalMember(ContractModel):
    role: Literal["target", "member"]
    kind: Literal["wellbore", "label"]
    name: str
    key: str = Field(description="Wellbore key or normalized label (the durable merge key).")
    wellbore_id: UUID | None = None
    evidence: list[MergeEvidenceQuote] = Field(default_factory=list)


class MergeProposal(ContractModel):
    proposal_id: UUID
    project_id: UUID
    run_id: UUID
    status: MergeProposalStatus
    target: MergeProposalMember
    members: list[MergeProposalMember]
    guard_results: list[MergeGuardResult]
    acceptable: bool = Field(
        description="True only for a pending proposal whose guards all passed when created."
    )
    rationale: str
    dataset_fingerprint: str
    dataset_current: bool = Field(
        description="False when the project's identity inputs changed since the proposal."
    )
    decided_by: str | None = None
    decided_at: UtcDatetime | None = None
    decision_note: str | None = None
    created_at: UtcDatetime


class MergeProposalPage(ContractModel):
    items: list[MergeProposal]
    total: int = Field(ge=0)


class MergeProposalQuery(ContractModel):
    status: MergeProposalStatus | None = None
    limit: int = Field(default=50, ge=1, le=MAX_PAGE_LIMIT)


class MergeDecisionRequest(ContractModel):
    decided_by: str = Field(default="user", min_length=1, max_length=80)
    note: str | None = Field(default=None, max_length=500)


class MergeRunCall(ContractModel):
    index: int = Field(ge=0)
    outcome: Literal["ok", "failed"]
    reason: str | None = Field(default=None, description="Stable failure code.")
    blocks: int = Field(ge=0)
    attempts: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0, decimal_places=6)


class MergeProposalRun(ContractModel):
    run_id: UUID
    project_id: UUID
    state: Literal["succeeded", "partial", "failed", "no_candidates"]
    reason: str | None = None
    model_id: str
    prompt_version: str
    guard_version: str
    dataset_fingerprint: str
    blocks: int = Field(ge=0)
    deferred_blocks: int = Field(ge=0)
    proposals_created: int = Field(ge=0)
    proposals_dropped: int = Field(ge=0)
    drop_reasons: dict[str, int]
    calls: list[MergeRunCall]
    provider_calls: int = Field(ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0, decimal_places=6)
    created_at: UtcDatetime
    finished_at: UtcDatetime | None = None


class MergeProposalRunPage(ContractModel):
    items: list[MergeProposalRun]


class MergeRunRequest(ContractModel):
    confirm: bool = Field(
        description="Must be true: the run spends model budget after the estimate was shown."
    )


class MergeProposalEstimate(ContractModel):
    blocks: int = Field(ge=0, description="Blocks that would be sent to the model.")
    deferred_blocks: int = Field(ge=0, description="Blocks beyond the per-run bound.")
    calls: int = Field(ge=0)
    max_reserved_usd_per_call: Decimal = Field(ge=0, decimal_places=6)
    upper_bound_usd: Decimal = Field(ge=0, decimal_places=6)
    dataset_fingerprint: str
    provider_configured: bool

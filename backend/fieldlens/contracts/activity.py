"""Agent activity log DTOs (AX-10, TASK-038): display and audit only.

The log records what a bounded agent work unit did (question, ordered steps, tool-call and
candidate summaries, validator outcomes, usage, stop reason). It never stores hidden reasoning
and is never a source of engineering facts: candidates are proposals whose validation lives
elsewhere. Strings may be truncated or redacted; ``truncated`` says so explicitly."""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from .base import ContractModel, FiniteJsonValue, UtcDatetime
from .context import PageInfo, PageParams
from .evidence import EvidenceLink


class AgentUnitState(StrEnum):
    """Only ``succeeded`` is a success; everything else is visibly not successful."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


class AgentStepKind(StrEnum):
    TOOL_CALL = "tool_call"
    CANDIDATE = "candidate"
    VALIDATOR = "validator"
    MODEL_TURN = "model_turn"
    LIFECYCLE = "lifecycle"
    NOTE = "note"


class AgentStepOutcome(StrEnum):
    OK = "ok"
    REFUSED = "refused"
    ERROR = "error"
    PASSED = "passed"
    FAILED = "failed"
    FLAGGED = "flagged"


class AgentUsage(ContractModel):
    """Accumulated provider usage for the unit; cost is an estimate in USD."""

    input_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal = Field(ge=0, decimal_places=6)


class AgentStep(ContractModel):
    step_id: UUID
    step_no: int = Field(ge=1, description="Gapless order within the unit, starting at 1.")
    kind: AgentStepKind
    outcome: AgentStepOutcome | None = None
    tool_name: str | None = None
    summary: str = Field(description="Bounded, redacted summary; never hidden reasoning.")
    detail: dict[str, FiniteJsonValue] = Field(
        default_factory=dict, description="Bounded, redacted structured summary."
    )
    evidence: list[EvidenceLink] = Field(
        default_factory=list, description="Source locations the step cites."
    )
    truncated: bool = Field(description="True when any text or payload was shortened or dropped.")
    created_at: UtcDatetime


class AgentUnitSummary(ContractModel):
    unit_id: UUID
    project_id: UUID
    source_revision_id: UUID
    unit_key: str
    question: str
    state: AgentUnitState
    stop_reason: str | None = Field(default=None, description="Set for every state except running.")
    stop_detail: str | None = None
    attempt_count: int = Field(ge=1)
    step_count: int = Field(ge=0)
    tool_call_count: int = Field(ge=0)
    candidate_count: int = Field(ge=0)
    usage: AgentUsage
    created_at: UtcDatetime
    updated_at: UtcDatetime
    finished_at: UtcDatetime | None = None


class AgentUnitDetail(ContractModel):
    unit: AgentUnitSummary
    steps: list[AgentStep]


class AgentUnitPage(ContractModel):
    items: list[AgentUnitSummary]
    page: PageInfo


class AgentUnitQuery(PageParams):
    """Listing filters; the project comes from the path."""

    state: AgentUnitState | None = None
    source_revision_id: UUID | None = None

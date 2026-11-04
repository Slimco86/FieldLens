"""Project assistant chat DTOs (TASK-094, FL-027; spec EXPLORE_ENRICHMENT sections 3 AV-*, 4.4).

DTO-only freeze. An answer is a list of typed blocks grounded in this turn's tool results:

* ``text`` carries citation markers, ``value`` binds a number+unit to a tool result, ``chart`` is a
  declarative request the server materializes into a :class:`ChartSpec` (the model never supplies points),
  ``link`` is a validated :class:`AppLink`, ``gap`` states unavailable data or a refusal;
* every link target is a closed, typed variant (no free-form URLs, paths or scene scripts);
* usage (tokens, steps, tool calls, time, cost) is reported only. There is no spend-ceiling field
  (owner decision D4); step/time/tool-call bounds guard runaway loops and are reported as limits.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, RootModel, field_validator, model_validator

from .base import ContractModel, UtcDatetime
from .charts import ChartKey, ChartSpec, ChartWindow
from .evidence import EvidenceLink, Locator, PdfLocator

MAX_MESSAGE_CHARS = 4000
MAX_BLOCKS = 40
MAX_CITATIONS = 100
MAX_LABEL_CHARS = 200


class ChatRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUSED = "refused"
    """The provider or policy refused; shown as a refusal, never as an answer."""
    TRUNCATED = "truncated"
    """Output was cut off (length or step/time bound); blocks are partial and labeled."""


TERMINAL_STATES = frozenset(
    {
        ChatRunState.COMPLETED,
        ChatRunState.FAILED,
        ChatRunState.CANCELLED,
        ChatRunState.REFUSED,
        ChatRunState.TRUNCATED,
    }
)


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ExploreView(StrEnum):
    SCENE = "3d"
    CHARTS = "charts"
    SPLIT = "split"


class AnswerVerification(StrEnum):
    VERIFIED = "verified"
    PARTIALLY_VERIFIED = "partially_verified"
    """Invalid blocks were dropped or free-text numbers are unverified."""
    UNVERIFIED = "unverified"


class GapReason(StrEnum):
    NO_DATA = "no_data"
    OUT_OF_SCOPE = "out_of_scope"
    REFUSED = "refused"
    UNAVAILABLE = "unavailable"
    DRAFT_ONLY = "draft_only"
    """Only draft/unpublished proposals exist; they are labeled as such."""


class ChatFailureCode(StrEnum):
    PROVIDER_OUTAGE = "provider_outage"
    PROVIDER_REFUSAL = "provider_refusal"
    MALFORMED_OUTPUT = "malformed_output"
    TRUNCATED = "truncated"
    STEP_LIMIT = "step_limit"
    TIME_LIMIT = "time_limit"
    TOOL_CALL_LIMIT = "tool_call_limit"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    """The worker restarted while the turn was running."""
    INTERNAL = "internal"


class DroppedBlockReason(StrEnum):
    UNKNOWN_CITATION = "unknown_citation"
    UNKNOWN_TOOL_RESULT = "unknown_tool_result"
    UNKNOWN_TARGET = "unknown_target"
    OUT_OF_PROJECT = "out_of_project"
    INVALID_LINK = "invalid_link"
    INVALID_CHART = "invalid_chart"
    UNVERIFIED_NUMBER = "unverified_number"


# --- AppLink ----------------------------------------------------------------------------


class SourceLinkTarget(ContractModel):
    """Opens the source viewer at a page/locator."""

    kind: Literal["source"] = "source"
    document_id: UUID
    page: int | None = Field(default=None, ge=1)
    locator: Locator | None = None

    @model_validator(mode="after")
    def _where(self) -> SourceLinkTarget:
        if self.page is None and self.locator is None:
            raise ValueError("a source link needs a page or a locator")
        if self.locator is not None:
            source = self.locator.root
            document_id = getattr(source, "document_id", None)
            if document_id is not None and document_id != self.document_id:
                raise ValueError("locator document_id must match the link document_id")
            if isinstance(source, PdfLocator) and self.page not in (None, source.page):
                raise ValueError("page must match the PDF locator page")
        return self


class ElementLinkTarget(ContractModel):
    kind: Literal["element"] = "element"
    element_id: UUID
    wellbore_id: UUID | None = None


class WellboreLinkTarget(ContractModel):
    kind: Literal["wellbore"] = "wellbore"
    wellbore_id: UUID


class FormationLinkTarget(ContractModel):
    kind: Literal["formation"] = "formation"
    surface_key: str = Field(min_length=1, max_length=256)
    wellbore_id: UUID | None = None
    pick_id: UUID | None = None


class ChartLinkTarget(ContractModel):
    """Opens the Charts tab on a chart and window."""

    kind: Literal["chart"] = "chart"
    chart_key: ChartKey
    wellbore_id: UUID | None = Field(default=None, description="Null selects the field chart set.")
    window: ChartWindow | None = None


class AppLinkTarget(
    RootModel[
        Annotated[
            SourceLinkTarget
            | ElementLinkTarget
            | WellboreLinkTarget
            | FormationLinkTarget
            | ChartLinkTarget,
            Field(discriminator="kind"),
        ]
    ]
):
    """Closed target variants keyed by ``kind``."""


class AppLink(ContractModel):
    """A typed in-app deep link. Targets are validated against this turn's tool results and the project."""

    label: str = Field(min_length=1, max_length=MAX_LABEL_CHARS)
    target: AppLinkTarget
    tool_call_id: UUID | None = Field(
        default=None, description="Tool call whose result introduced the target."
    )

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("link label must not be blank")
        return value


# --- Citations and blocks ---------------------------------------------------------------


class Citation(ContractModel):
    marker: str = Field(pattern=r"^\[[0-9]{1,3}\]$", description="For example '[1]'.")
    tool_call_id: UUID
    evidence: EvidenceLink | None = None
    record_id: UUID | None = None
    claim_id: UUID | None = None
    label: str | None = Field(default=None, max_length=MAX_LABEL_CHARS)
    draft: bool = Field(default=False, description="Cites a draft/unpublished proposal.")


class TextBlock(ContractModel):
    kind: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS * 4)
    citation_markers: list[str] = Field(default_factory=list, max_length=MAX_CITATIONS)
    unverified_numbers: list[str] = Field(
        default_factory=list, description="Free-text numbers absent from tool results (flagged)."
    )


class ValueBlock(ContractModel):
    """A number bound to a tool result; the value comes from the tool, never from the model."""

    kind: Literal["value"] = "value"
    label: str = Field(min_length=1, max_length=MAX_LABEL_CHARS)
    value: float | None = None
    unit: str | None = Field(default=None, max_length=32)
    reference: str | None = Field(default=None, description="Datum or index reference, as stated.")
    tool_call_id: UUID
    result_path: str = Field(
        min_length=1, max_length=256, description="Pointer into the tool result."
    )
    citation_markers: list[str] = Field(default_factory=list, max_length=MAX_CITATIONS)
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def _known(self) -> ValueBlock:
        if self.value is None and not self.unknown_reason:
            raise ValueError("a value block without a value needs unknown_reason")
        if self.value is not None and self.unit is None:
            raise ValueError("a known value requires its unit")
        return self


class ChartRequest(ContractModel):
    """Declarative request the model may emit: which chart, over which tool-result series."""

    chart_key: ChartKey
    title: str | None = Field(default=None, max_length=256)
    wellbore_id: UUID | None = None
    window: ChartWindow | None = None
    series_refs: list[str] = Field(
        default_factory=list,
        max_length=60,
        description="Series keys present in this turn's tool results; no points are accepted.",
    )
    tool_call_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ChartBlock(ContractModel):
    kind: Literal["chart"] = "chart"
    request: ChartRequest
    spec: ChartSpec | None = Field(
        default=None,
        description="Server-materialized chart; null until materialized or when it failed.",
    )
    open_in_charts: AppLink | None = None
    citation_markers: list[str] = Field(default_factory=list, max_length=MAX_CITATIONS)


class LinkBlock(ContractModel):
    kind: Literal["link"] = "link"
    link: AppLink


class GapBlock(ContractModel):
    """Unavailable data or a refusal, stated rather than invented."""

    kind: Literal["gap"] = "gap"
    reason: GapReason
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class AnswerBlock(
    RootModel[
        Annotated[
            TextBlock | ValueBlock | ChartBlock | LinkBlock | GapBlock,
            Field(discriminator="kind"),
        ]
    ]
):
    """Closed answer block variants keyed by ``kind``."""


class DroppedBlock(ContractModel):
    index: int = Field(ge=0)
    kind: str | None = None
    reason: DroppedBlockReason
    detail: str | None = None


class ChatAnswer(ContractModel):
    blocks: list[AnswerBlock] = Field(default_factory=list, max_length=MAX_BLOCKS)
    citations: list[Citation] = Field(default_factory=list, max_length=MAX_CITATIONS)
    verification: AnswerVerification
    dropped_blocks: list[DroppedBlock] = Field(default_factory=list)


# --- Turns, conversations, usage --------------------------------------------------------


class ChatContext(ContractModel):
    """UI selection sent with a turn. It narrows context and never widens project scope (AV-1)."""

    wellbore_id: UUID | None = None
    as_of: date | None = None
    view: ExploreView | None = None
    selected_surface_key: str | None = Field(default=None, max_length=256)
    selected_element_id: UUID | None = None
    chart_key: ChartKey | None = None


class ChatFailure(ContractModel):
    code: ChatFailureCode
    message: str = Field(min_length=1)
    retryable: bool = False


class ChatUsage(ContractModel):
    """Reported usage only; no ceiling is enforced on spend (D4)."""

    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    steps: int = Field(default=0, ge=0)
    tool_calls: int = Field(default=0, ge=0)
    elapsed_ms: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0, description="Ledger cost, informational.")
    model: str | None = None
    max_steps: int | None = Field(default=None, ge=1, description="Runaway-loop bound in force.")
    max_tool_calls: int | None = Field(default=None, ge=1)
    max_seconds: float | None = Field(default=None, gt=0)


class ChatToolCallSummary(ContractModel):
    tool_call_id: UUID
    tool_name: str = Field(min_length=1, max_length=64)
    ok: bool
    error: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class ChatMessage(ContractModel):
    message_id: UUID
    conversation_id: UUID
    turn_id: UUID
    role: ChatRole
    text: str | None = Field(default=None, max_length=MAX_MESSAGE_CHARS)
    answer: ChatAnswer | None = Field(default=None, description="Assistant messages only.")
    created_at: UtcDatetime

    @model_validator(mode="after")
    def _by_role(self) -> ChatMessage:
        if self.role is ChatRole.USER and (not self.text or self.answer is not None):
            raise ValueError("a user message has text and no answer")
        if self.role is ChatRole.ASSISTANT and self.text is not None:
            raise ValueError("an assistant message carries an answer, not free text")
        return self


class ChatTurn(ContractModel):
    turn_id: UUID
    conversation_id: UUID
    project_id: UUID
    state: ChatRunState
    user_message: ChatMessage
    assistant_message: ChatMessage | None = None
    context: ChatContext = Field(default_factory=ChatContext)
    failure: ChatFailure | None = None
    usage: ChatUsage = Field(default_factory=ChatUsage)
    tool_calls: list[ChatToolCallSummary] = Field(default_factory=list, max_length=100)
    created_at: UtcDatetime
    started_at: UtcDatetime | None = None
    completed_at: UtcDatetime | None = None

    @model_validator(mode="after")
    def _state(self) -> ChatTurn:
        if self.state in {ChatRunState.FAILED, ChatRunState.CANCELLED} and self.failure is None:
            raise ValueError("failed or cancelled turns carry a failure")
        if self.state in {ChatRunState.QUEUED, ChatRunState.RUNNING} and (
            self.completed_at is not None or self.assistant_message is not None
        ):
            raise ValueError("an in-flight turn has no completion or answer")
        if self.state in TERMINAL_STATES and self.completed_at is None:
            raise ValueError("a terminal turn has completed_at")
        if self.state is ChatRunState.COMPLETED and self.assistant_message is None:
            raise ValueError("a completed turn has an assistant message")
        return self


class Conversation(ContractModel):
    conversation_id: UUID
    project_id: UUID
    title: str | None = Field(default=None, max_length=256)
    turn_count: int = Field(default=0, ge=0)
    created_at: UtcDatetime
    updated_at: UtcDatetime


class ConversationList(ContractModel):
    items: list[Conversation] = Field(max_length=200)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    next_offset: int | None = None


class ConversationDetail(ContractModel):
    conversation: Conversation
    turns: list[ChatTurn] = Field(default_factory=list, max_length=500)


class CreateConversationRequest(ContractModel):
    title: str | None = Field(default=None, min_length=1, max_length=256)


class CreateTurnRequest(ContractModel):
    """Submits a user message; the server queues a persisted job the UI polls."""

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    context: ChatContext = Field(default_factory=ChatContext)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("message")
    @classmethod
    def _message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value

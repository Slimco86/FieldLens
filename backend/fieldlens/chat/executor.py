"""Execute one chat turn: bounded tool loop, answer validation, explicit outcome states.

Every end state is explicit and honest: refusal, truncation, malformed output, step/time/tool-call
limits, cancellation and provider outage each map to a typed state/failure. A turn only completes
with an answer that survived validation; nothing is ever reported as success otherwise.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal

from fieldlens.assistant.errors import (
    AssistantError,
    BudgetExceeded,
    ProviderAuthError,
    ProviderMalformed,
    ProviderRefusal,
    ProviderTruncated,
    ProviderUnavailable,
    RequestCancelled,
    RequestLimitExceeded,
    ReservationStateError,
)
from fieldlens.assistant.messages import Message, TextPart
from fieldlens.assistant.provider import CancelToken
from fieldlens.assistant.runner import WorkUnit
from fieldlens.chat.answer import AnswerValidator, MalformedAnswer, parse_model_output
from fieldlens.chat.evidence_pool import TurnEvidence
from fieldlens.chat.prompt import build_messages
from fieldlens.chat.repository import ClaimedTurn
from fieldlens.chat.runtime import ChatRuntime
from fieldlens.chat.tools import DbProjectScope, ProjectScope, ToolRunner, tool_specs
from fieldlens.contracts.chat import (
    ChatAnswer,
    ChatFailure,
    ChatFailureCode,
    ChatRunState,
    ChatToolCallSummary,
    ChatUsage,
)

logger = logging.getLogger(__name__)

REPAIR_PROMPT = (
    "Your previous reply was not a valid answer object. Reply again with ONLY the JSON object "
    '{"blocks":[...]} as specified, using the tool results already returned.'
)


@dataclass
class TurnOutcome:
    state: ChatRunState
    answer: ChatAnswer | None = None
    failure: ChatFailure | None = None
    usage: ChatUsage = field(default_factory=ChatUsage)
    tool_calls: list[ChatToolCallSummary] = field(default_factory=list)


def failure_for(exc: BaseException) -> tuple[ChatRunState, ChatFailure]:
    """Typed mapping of a harness/provider error to an explicit turn state."""
    if isinstance(exc, RequestCancelled):
        return ChatRunState.CANCELLED, ChatFailure(
            code=ChatFailureCode.CANCELLED, message="The turn was cancelled.", retryable=True
        )
    if isinstance(exc, ProviderRefusal):
        return ChatRunState.REFUSED, ChatFailure(
            code=ChatFailureCode.PROVIDER_REFUSAL,
            message="The model declined to answer this request.",
        )
    if isinstance(exc, ProviderTruncated):
        return ChatRunState.TRUNCATED, ChatFailure(
            code=ChatFailureCode.TRUNCATED,
            message="The model output was cut off before it finished; no answer was produced.",
            retryable=True,
        )
    if isinstance(exc, RequestLimitExceeded):
        code, text = {
            "deadline": (ChatFailureCode.TIME_LIMIT, "The turn exceeded its time limit."),
            "attempts": (ChatFailureCode.STEP_LIMIT, "The turn exceeded its step limit."),
            "tool_rounds": (ChatFailureCode.STEP_LIMIT, "The turn exceeded its tool-round limit."),
            "tool_calls": (
                ChatFailureCode.TOOL_CALL_LIMIT,
                "The turn exceeded its tool-call limit.",
            ),
        }.get(exc.limit, (ChatFailureCode.STEP_LIMIT, "The turn exceeded a safety bound."))
        return ChatRunState.FAILED, ChatFailure(code=code, message=text, retryable=True)
    if isinstance(exc, ProviderMalformed):
        return ChatRunState.FAILED, ChatFailure(
            code=ChatFailureCode.MALFORMED_OUTPUT,
            message="The model returned output the server could not accept.",
            retryable=True,
        )
    if isinstance(exc, ProviderAuthError):
        return ChatRunState.FAILED, ChatFailure(
            code=ChatFailureCode.PROVIDER_OUTAGE,
            message="The model provider rejected the credentials.",
        )
    if isinstance(exc, AssistantError):
        return ChatRunState.FAILED, ChatFailure(
            code=ChatFailureCode.PROVIDER_OUTAGE,
            message="The model provider is unavailable.",
            retryable=True,
        )
    return ChatRunState.FAILED, ChatFailure(
        code=ChatFailureCode.INTERNAL, message="The turn failed unexpectedly.", retryable=True
    )


def _open_unit(
    rt: ChatRuntime, claim: ClaimedTurn, cancel: CancelToken, runner: ToolRunner
) -> WorkUnit:
    """Open a work unit, rotating ledger periods instead of ever blocking on money (D4)."""
    assert rt.provider is not None and rt.pricing is not None and rt.pricing_id is not None
    limits = rt.limits.request_limits()
    last: Exception | None = None
    for attempt in range(3):
        period = rt.periods.acquire(limits.max_reserved_usd)
        unit = WorkUnit(
            provider=rt.provider,
            ledger=rt.ledger,
            period_id=period,
            pricing_id=rt.pricing_id,
            pricing=rt.pricing,
            model=rt.model,
            request_key=f"chat-{claim.turn_id}-{attempt}",
            work_unit="chat_turn",
            limits=limits,
            cancel=cancel,
            tools=tool_specs(),
        )
        try:
            return unit.__enter__()
        except (BudgetExceeded, ProviderUnavailable, ReservationStateError) as exc:
            last = exc
            rt.periods.rotate()
    raise ProviderUnavailable("no ledger period accepted the usage reservation") from last


def _usage(rt: ChatRuntime, unit: WorkUnit | None, started: float) -> ChatUsage:
    usage = ChatUsage(
        elapsed_ms=int((time.monotonic() - started) * 1000),
        model=rt.model,
        max_steps=rt.limits.max_steps,
        max_tool_calls=rt.limits.max_tool_calls,
        max_seconds=rt.limits.deadline_s,
    )
    if unit is None:
        return usage
    try:
        closed = unit.close()
        tokens_in, tokens_out = unit.token_usage()
        cost: Decimal | None = closed.committed_usd if closed is not None else None
        return usage.model_copy(
            update={
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "steps": unit.attempts,
                "tool_calls": unit.tool_calls,
                "cost_usd": float(cost) if cost is not None else None,
            }
        )
    except Exception:  # noqa: BLE001 - usage is informational; never fail the turn on it
        logger.warning("chat usage could not be read")
        return usage


def execute_turn(
    rt: ChatRuntime,
    claim: ClaimedTurn,
    cancel: CancelToken,
    *,
    scope: ProjectScope | None = None,
) -> TurnOutcome:
    started = time.monotonic()
    if not rt.live:
        return TurnOutcome(
            ChatRunState.FAILED,
            failure=ChatFailure(
                code=ChatFailureCode.PROVIDER_OUTAGE,
                message=rt.unavailable_reason or "no model is configured",
            ),
            usage=_usage(rt, None, started),
        )
    evidence = TurnEvidence()
    runner = ToolRunner(
        project_id=claim.project_id,
        factory=rt.factory,
        retrieval=rt.retrieval,
        series=rt.series,
        context=claim.context,
        evidence=evidence,
    )
    unit: WorkUnit | None = None
    try:
        unit = _open_unit(rt, claim, cancel, runner)
        response, history = unit.run_tool_loop(
            build_messages(claim), runner.execute, max_rounds=rt.limits.max_steps
        )
        validator_scope = scope or DbProjectScope(rt.factory, claim.project_id)

        def validate(text: str) -> ChatAnswer:
            return AnswerValidator(
                project_id=claim.project_id,
                evidence=evidence,
                scope=validator_scope,
                series=rt.series,
                context=claim.context,
                tool_calls_made=unit.tool_calls if unit else 0,
            ).validate(parse_model_output(text))

        try:
            answer = validate(response.text())
        except MalformedAnswer:
            repair: list[Message] = [
                *history,
                Message(role="user", parts=(TextPart(text=REPAIR_PROMPT),)),
            ]
            second = unit.step(repair)
            try:
                answer = validate(second.text())
            except MalformedAnswer:
                return TurnOutcome(
                    ChatRunState.FAILED,
                    failure=ChatFailure(
                        code=ChatFailureCode.MALFORMED_OUTPUT,
                        message="The model did not return a valid typed answer.",
                        retryable=True,
                    ),
                    usage=_usage(rt, unit, started),
                    tool_calls=runner.summaries,
                )
        return TurnOutcome(
            ChatRunState.COMPLETED,
            answer=answer,
            usage=_usage(rt, unit, started),
            tool_calls=runner.summaries,
        )
    except Exception as exc:  # noqa: BLE001 - mapped to an explicit typed state below
        if not isinstance(exc, AssistantError):
            logger.exception("chat turn %s failed", claim.turn_id)
        state, failure = failure_for(exc)
        return TurnOutcome(
            state,
            failure=failure,
            usage=_usage(rt, unit, started),
            tool_calls=runner.summaries,
        )
    finally:
        if unit is not None:
            unit.close()

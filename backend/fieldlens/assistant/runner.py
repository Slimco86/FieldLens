"""Bounded work unit: one reservation, <= N provider attempts, bounded tool loop, cancellation.

``WorkUnit`` is the only path that dispatches a provider call. Before each dispatch it checks
cancellation, the deadline, the attempt bound, the tool-call bound and that (billed + estimated
liability + this attempt's upper bound) fits the reservation. The attempt row is persisted before
the call, so a crash or timeout retains liability. 429/5xx are retried at most once per step;
401/403, refusal, truncation and malformed output are never retried automatically.
Prompts, tool arguments and results are never logged here.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from types import TracebackType
from typing import Self
from uuid import UUID

from fieldlens.config import Settings

from .budget import BudgetLedger, Reservation, usd
from .errors import (
    AssistantError,
    ProviderMalformed,
    ProviderRefusal,
    ProviderTimeout,
    ProviderTruncated,
    ProviderUnavailable,
    RequestCancelled,
    RequestLimitExceeded,
)
from .messages import (
    Message,
    ProviderRequest,
    ProviderResponse,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    ToolSpec,
    validate_tool_arguments,
)
from .provider import (
    CancelToken,
    Pricing,
    Provider,
    actual_cost_usd,
    attempt_upper_bound_usd,
)

logger = logging.getLogger(__name__)
DEFAULT_BACKOFF_S = 0.5


@dataclass(frozen=True)
class RequestLimits:
    """MI-5 bounds for one work unit. Defaults are the approved values; tool calls is tunable."""

    max_attempts: int = 4
    max_tool_calls: int = 6
    deadline_s: float = 90.0
    max_output_tokens: int = 4096
    max_reserved_usd: Decimal = Decimal("0.50")
    image_token_bound: int = 8192
    retry_backoff_s: float = DEFAULT_BACKOFF_S

    @classmethod
    def from_settings(cls, settings: Settings) -> RequestLimits:
        return cls(
            max_attempts=settings.provider_max_attempts,
            max_tool_calls=settings.provider_max_tool_calls,
            deadline_s=settings.provider_deadline_s,
            max_output_tokens=settings.provider_max_output_tokens,
            max_reserved_usd=settings.provider_max_reserved_usd,
            image_token_bound=settings.provider_image_token_bound,
        )


ToolExecutor = Callable[[ToolCallPart], str]


class WorkUnit:
    def __init__(
        self,
        *,
        provider: Provider,
        ledger: BudgetLedger,
        period_id: UUID,
        pricing_id: UUID,
        pricing: Pricing,
        model: str,
        request_key: str,
        work_unit: str,
        limits: RequestLimits,
        cancel: CancelToken | None = None,
        tools: Sequence[ToolSpec] = (),
        unattended: bool = False,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if pricing.model != model:
            raise ProviderUnavailable("pricing revision does not cover the requested model")
        self._provider = provider
        self._ledger = ledger
        self._period_id = period_id
        self._pricing_id = pricing_id
        self._pricing = pricing
        self._model = model
        self._request_key = request_key
        self._work_unit = work_unit
        self.limits = limits
        self.cancel = cancel or CancelToken()
        self._tools = {t.name: t for t in tools}
        self._unattended = unattended
        self._clock = clock
        self._started = 0.0
        self.reservation: Reservation | None = None
        self.attempts = 0
        self.tool_calls = 0
        self.closed: Reservation | None = None

    # -- lifecycle --------------------------------------------------------------------------
    def __enter__(self) -> Self:
        self.cancel.raise_if_cancelled()
        self._started = self._clock()
        self.reservation = self._ledger.reserve(
            self._period_id,
            self._request_key,
            self.limits.max_reserved_usd,
            self._pricing_id,
            work_unit=self._work_unit,
            unattended=self._unattended,
        )
        # Re-entering an open reservation resumes its persisted counters.
        self.attempts = self.reservation.attempts_dispatched
        self.tool_calls = self.reservation.tool_calls_used
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> Reservation | None:
        """Settle from attempt records (releases if nothing was dispatched). Idempotent."""
        if self.reservation is not None and self.closed is None:
            self.closed = self._ledger.settle(self.reservation.reservation_id)
        return self.closed

    # -- bounds -----------------------------------------------------------------------------
    def _remaining_s(self) -> float:
        return self.limits.deadline_s - (self._clock() - self._started)

    def _guard(self, request: ProviderRequest) -> Decimal:
        assert self.reservation is not None
        self.cancel.raise_if_cancelled()
        if self._remaining_s() <= 0:
            raise RequestLimitExceeded("deadline")
        if self.attempts >= self.limits.max_attempts:
            raise RequestLimitExceeded("attempts")
        bound = attempt_upper_bound_usd(request, self._pricing, self.limits.image_token_bound)
        spent = self._ledger.spent_so_far(self.reservation.reservation_id)
        if spent + bound > self.reservation.reserved_usd:
            raise RequestLimitExceeded("reserved_cost")
        return bound

    # -- one provider step (with at most one retry) -------------------------------------------
    def step(self, messages: Sequence[Message]) -> ProviderResponse:
        if self.reservation is None:
            raise ReservationNotOpen("work unit is not open")
        request = ProviderRequest(
            model=self._model,
            messages=tuple(messages),
            tools=tuple(self._tools.values()),
            max_output_tokens=self.limits.max_output_tokens,
        )
        retry_of: int | None = None
        retried = False
        while True:
            bound = self._guard(request)
            rid = self.reservation.reservation_id
            number = self._ledger.begin_attempt(
                rid,
                provider=self._provider.name,
                model=self._model,
                estimated_usd=bound,
                retry_of=retry_of,
            )
            self.attempts += 1
            began = self._clock()
            try:
                response = self._provider.complete(
                    request, timeout_s=max(self._remaining_s(), 0.001), cancel=self.cancel
                )
            except AssistantError as exc:
                # A cancel after dispatch may already be billed: unknown, never zero.
                unknown = exc.chargeable or isinstance(exc, RequestCancelled)
                if isinstance(exc, ProviderTimeout):
                    status = "timeout"
                else:
                    status = "unknown" if isinstance(exc, RequestCancelled) else "failed"
                self._ledger.finish_attempt(
                    rid,
                    number,
                    status=status,
                    billed_usd=None if unknown else Decimal("0"),
                    error_code=exc.code,
                    elapsed_ms=int((self._clock() - began) * 1000),
                )
                if exc.retryable and not retried and self._can_retry(exc):
                    retried, retry_of = True, number
                    continue
                raise
            except BaseException:
                # Unexpected failure: keep the estimate as liability; never report as zero.
                self._ledger.finish_attempt(
                    rid,
                    number,
                    status="unknown",
                    billed_usd=None,
                    error_code="unexpected",
                    elapsed_ms=int((self._clock() - began) * 1000),
                )
                raise
            return self._accept(response, rid, number, int((self._clock() - began) * 1000))

    def _can_retry(self, exc: AssistantError) -> bool:
        wait = getattr(exc, "retry_after_s", None)
        wait = self.limits.retry_backoff_s if wait is None else float(wait)
        if self.attempts >= self.limits.max_attempts or self._remaining_s() <= wait:
            return False
        return not self.cancel.wait(wait) and not self.cancel.cancelled

    def _accept(
        self, response: ProviderResponse, rid: UUID, number: int, elapsed_ms: int
    ) -> ProviderResponse:
        usage = response.usage
        billed = actual_cost_usd(usage, self._pricing)
        status = {"completed": "completed", "refusal": "refused", "truncated": "truncated"}[
            response.status
        ]
        self._ledger.finish_attempt(
            rid,
            number,
            status=status,
            billed_usd=billed,  # None (usage unavailable) stays estimated liability, not zero
            provider_request_id=response.provider_request_id,
            input_tokens=usage.input_tokens if usage else None,
            cached_input_tokens=usage.cached_input_tokens if usage else None,
            output_tokens=usage.output_tokens if usage else None,
            web_search_queries=usage.web_search_queries if usage else None,
            elapsed_ms=elapsed_ms,
        )
        self.cancel.raise_if_cancelled()  # a late cancel discards the answer; usage is recorded
        if response.status == "refusal":
            raise ProviderRefusal("provider refused the request")
        if response.status == "truncated":
            raise ProviderTruncated("provider output was truncated")
        self._validate(response)
        return response

    def _validate(self, response: ProviderResponse) -> None:
        if not response.parts:
            raise ProviderMalformed("provider returned no content")
        for call in response.tool_calls():
            spec = self._tools.get(call.name)
            if spec is None:
                raise ProviderMalformed("provider called a tool that is not allowlisted")
            if validate_tool_arguments(spec, call.arguments) is not None:
                raise ProviderMalformed("provider tool call arguments are invalid")

    # -- bounded tool loop ------------------------------------------------------------------
    def run_tool_loop(
        self,
        messages: Sequence[Message],
        executor: ToolExecutor,
        *,
        max_rounds: int | None = None,
    ) -> tuple[ProviderResponse, list[Message]]:
        """Alternate provider steps and read-only tool execution until a tool-free answer.

        Tool calls beyond ``max_tool_calls`` are not executed (``RequestLimitExceeded``). Tool
        failures are returned to the model as error results with a fixed message.
        """
        history = list(messages)
        rounds = 0
        while True:
            response = self.step(history)
            calls = response.tool_calls()
            history.append(Message(role="assistant", parts=response.parts))
            if not calls:
                return response, history
            rounds += 1
            if max_rounds is not None and rounds > max_rounds:
                raise RequestLimitExceeded("tool_rounds")
            if self.tool_calls + len(calls) > self.limits.max_tool_calls:
                raise RequestLimitExceeded("tool_calls")
            results: list[ToolResultPart] = []
            for call in calls:
                self.cancel.raise_if_cancelled()
                self.tool_calls += 1
                assert self.reservation is not None
                # Persist before executing so a crash/cancel mid-round cannot undercount.
                self._ledger.add_tool_calls(self.reservation.reservation_id, 1)
                try:
                    results.append(ToolResultPart(call_id=call.call_id, content=executor(call)))
                except RequestCancelled:
                    raise
                except Exception:  # noqa: BLE001 - tool detail is not forwarded to the model
                    logger.warning("tool %s failed", call.name)
                    results.append(
                        ToolResultPart(call_id=call.call_id, content="tool failed", is_error=True)
                    )
            history.append(Message(role="tool", parts=tuple(results)))


class ReservationNotOpen(AssistantError):
    code = "reservation_not_open"
    chargeable = False


def text_message(role: str, text: str) -> Message:
    return Message(role=role, parts=(TextPart(text=text),))


__all__ = ["RequestLimits", "WorkUnit", "text_message", "usd"]

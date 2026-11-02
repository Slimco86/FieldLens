"""The model-assisted step for PDFs without a native profile (TASK-055).

For each document it reads the text of at most ``max_pages_per_document`` first pages, asks the
model (one bounded, tool-less call through the budget ledger) for a category, tags and wellbore
identities with page + quote, validates the answer server-side and stores it in one transaction.
It never throws for *content* (an unknown category or no identity is a stored, honest result); it
raises typed, retryable :class:`PageFailure` for refusal / truncation / malformed output / provider
errors, and :class:`RunStop` for cancel or budget, in which case no rows are written.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.errors import (
    AssistantError,
    BudgetExceeded,
    ProviderMalformed,
    ProviderRefusal,
    ProviderRejected,
    ProviderTruncated,
    RequestCancelled,
    RequestLimitExceeded,
)
from fieldlens.assistant.messages import Effort
from fieldlens.assistant.provider import Pricing as ModelPricing
from fieldlens.assistant.provider import Provider
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.candidates.pages import PageText
from fieldlens.contracts.processing import ProcessingFailureCode
from fieldlens.persistence.session import session_scope
from fieldlens.processing import identity_read as ir
from fieldlens.processing import identity_store as store
from fieldlens.processing import tables as t
from fieldlens.processing.steps import (
    Checkpoint,
    DocumentTask,
    PageFailure,
    PageProvider,
    PageUsage,
    RunStop,
    quantize,
)

log = logging.getLogger(__name__)
pr, prd = t.processing_run, t.processing_run_document
MODEL_STEP = "model_classification"
ZERO = Decimal("0")

PageTextSource = Callable[[str, int], PageText]


@dataclass(frozen=True)
class ModelStepConfig:
    period_id: UUID
    pricing_id: UUID
    pricing: ModelPricing
    model: str
    max_pages: int = 5
    limits: RequestLimits = field(
        default_factory=lambda: RequestLimits(
            max_attempts=2,
            max_tool_calls=0,
            deadline_s=90.0,
            max_output_tokens=1200,
            max_reserved_usd=Decimal("0.25"),
        )
    )
    effort: Effort | None = "low"


@dataclass(frozen=True)
class FailureMapping:
    code: ProcessingFailureCode
    message: str


def map_failure(exc: BaseException) -> FailureMapping | RunStop:
    """Typed processing failure for a provider/validation error (all retryable)."""
    if isinstance(exc, ProviderRefusal):
        return FailureMapping(ProcessingFailureCode.PROVIDER_REFUSED, "the model refused")
    if isinstance(exc, ProviderRejected):  # unknown model / endpoint: a provider error
        return FailureMapping(ProcessingFailureCode.PROVIDER_ERROR, "provider rejected the request")
    if isinstance(exc, ProviderTruncated):
        return FailureMapping(ProcessingFailureCode.PROVIDER_TRUNCATED, "the output was truncated")
    if isinstance(exc, ProviderMalformed | ir.OutputError):
        return FailureMapping(
            ProcessingFailureCode.PROVIDER_MALFORMED, "the output was not the expected JSON"
        )
    if isinstance(exc, RequestCancelled):
        return RunStop(ProcessingFailureCode.CANCELLED, "cancelled by the user")
    if isinstance(exc, BudgetExceeded) or (
        isinstance(exc, RequestLimitExceeded) and exc.limit == "reserved_cost"
    ):
        return RunStop(ProcessingFailureCode.BUDGET_STOP, "the budget does not cover this call")
    if isinstance(exc, AssistantError):
        return FailureMapping(ProcessingFailureCode.PROVIDER_ERROR, f"provider error: {exc.code}")
    return FailureMapping(ProcessingFailureCode.PROVIDER_ERROR, "provider error")


class ModelClassificationStep:
    """``ProcessingStep`` that classifies and reads wellbore identity (no tools, no web)."""

    name = MODEL_STEP

    def __init__(
        self,
        factory: sessionmaker[Session],
        ledger: BudgetLedger,
        provider: Provider,
        config: ModelStepConfig,
        page_text: PageTextSource,
    ) -> None:
        self._factory = factory
        self._ledger = ledger
        self._provider = provider
        self._config = config
        self._page_text = page_text

    @property
    def max_pages_per_document(self) -> int:
        return self._config.max_pages

    # -- one document -----------------------------------------------------------------------
    def run_document(
        self, task: DocumentTask, provider: PageProvider, checkpoint: Checkpoint
    ) -> None:
        pages = list(task.pages)
        if len(pages) > self._config.max_pages:
            raise PageFailure(
                ProcessingFailureCode.PROVIDER_ERROR,
                "the page window exceeds the model page bound",
                retryable=False,
            )
        with session_scope(self._factory) as s:
            cached = store.find_cached(
                s, task.project_id, task.document_id, task.page_start, task.page_end
            )
            if cached is not None:
                s.execute(
                    update(prd)
                    .where(prd.c.run_id == task.run_id, prd.c.document_id == task.document_id)
                    .values(cache_hit=True)
                )
        if cached is not None:
            self._charge(pages, ZERO, checkpoint)  # zero provider calls, zero spend
            return

        texts = self._read_pages(task, pages)
        usable = {n: p.text for n, p in texts.items() if p.has_text_layer and p.text.strip()}
        if not usable:
            self._persist(task, provider, ir.no_text_outcome(), None, None, ZERO)
            self._charge(pages, ZERO, checkpoint)
            return

        remaining = self._remaining_confirmed(task)
        if remaining <= ZERO:
            raise RunStop(ProcessingFailureCode.BUDGET_STOP, "the confirmed estimate is used up")
        limits = self._limits(remaining)
        unit = WorkUnit(
            provider=self._provider,
            ledger=self._ledger,
            period_id=self._config.period_id,
            pricing_id=self._config.pricing_id,
            pricing=self._config.pricing,
            model=self._config.model,
            request_key=f"doc-identity:{task.run_id}:{task.document_id}",
            work_unit=f"doc-identity:{task.document_id}"[:120],
            limits=limits,
            effort=self._config.effort,
        )
        response = None
        failure: BaseException | None = None
        try:
            self._raise_if_cancelled(task)
            with unit:
                response = unit.step(ir.build_messages(usable))
        except RunStop:
            raise
        except AssistantError as exc:
            failure = exc
        cost = unit.closed.committed_usd if unit.closed is not None else ZERO
        cost = quantize(Decimal(cost))

        outcome: ir.ModelOutcome | None = None
        if failure is None and response is not None:
            try:
                outcome = ir.validate(ir.parse_output(response.text()), usable)
            except ir.OutputError as exc:
                failure = exc
        if failure is not None or outcome is None or response is None:
            assert failure is not None
            mapped = map_failure(failure)
            self._charge(pages, cost, checkpoint)  # a billed failure is still real spend
            if isinstance(mapped, RunStop):
                raise mapped
            raise PageFailure(mapped.code, mapped.message, retryable=True)

        usage = response.usage
        self._persist(
            task,
            provider,
            outcome,
            usage.input_tokens if usage else None,
            usage.output_tokens if usage else None,
            cost,
        )
        self._charge(pages, cost, checkpoint)

    # -- helpers ----------------------------------------------------------------------------
    def _read_pages(self, task: DocumentTask, pages: list[int]) -> dict[int, PageText]:
        out: dict[int, PageText] = {}
        for n in pages:
            try:
                out[n] = self._page_text(task.storage_key, n)
            except Exception as exc:  # unreadable stored PDF: typed, retryable, no rows
                raise PageFailure(
                    ProcessingFailureCode.DOCUMENT_UNAVAILABLE, "the stored PDF could not be read"
                ) from exc
        return out

    def _limits(self, remaining: Decimal) -> RequestLimits:
        base = self._config.limits
        cap = min(base.max_reserved_usd, remaining)
        return RequestLimits(
            max_attempts=base.max_attempts,
            max_tool_calls=0,
            deadline_s=base.deadline_s,
            max_output_tokens=base.max_output_tokens,
            max_reserved_usd=cap,
            image_token_bound=base.image_token_bound,
            retry_backoff_s=base.retry_backoff_s,
            default_effort=base.default_effort,
        )

    def _remaining_confirmed(self, task: DocumentTask) -> Decimal:
        with session_scope(self._factory) as s:
            row = s.execute(
                select(pr.c.confirmed_usd, pr.c.actual_usd).where(
                    pr.c.project_id == task.project_id, pr.c.run_id == task.run_id
                )
            ).one()
        return Decimal(row.confirmed_usd or 0) - Decimal(row.actual_usd)

    def _raise_if_cancelled(self, task: DocumentTask) -> None:
        with session_scope(self._factory) as s:
            cancelled = s.execute(
                select(pr.c.cancel_requested).where(
                    pr.c.project_id == task.project_id, pr.c.run_id == task.run_id
                )
            ).scalar_one()
        if cancelled:
            raise RunStop(ProcessingFailureCode.CANCELLED, "cancelled by the user")

    def _persist(
        self,
        task: DocumentTask,
        provider: PageProvider,
        outcome: ir.ModelOutcome,
        input_tokens: int | None,
        output_tokens: int | None,
        cost: Decimal,
    ) -> None:
        with session_scope(self._factory) as s:
            store.store_result(
                s,
                project_id=task.project_id,
                document_id=task.document_id,
                source_revision_id=task.source_revision_id,
                run_id=task.run_id,
                page_start=task.page_start,
                page_end=task.page_end,
                provider=provider.name,
                model_revision=self._config.model,
                outcome=outcome,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
            )

    @staticmethod
    def _charge(pages: list[int], cost: Decimal, checkpoint: Checkpoint) -> None:
        """Report every page of the window; the spend is split across them and sums to ``cost``."""
        n = len(pages)
        share = quantize(cost / n) if n else ZERO
        spent = ZERO
        for index, page in enumerate(pages):
            part = cost - spent if index == n - 1 else share
            spent += part
            checkpoint(page, PageUsage(0, 0, quantize(part)))

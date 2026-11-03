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
from fieldlens.assistant.messages import Effort, ProviderRequest
from fieldlens.assistant.provider import Pricing as ModelPricing
from fieldlens.assistant.provider import Provider, attempt_upper_bound_usd, estimate_input_tokens
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.candidates.pages import PageText
from fieldlens.contracts.processing import ProcessingFailureCode
from fieldlens.persistence.session import session_scope
from fieldlens.processing import identity_read as ir
from fieldlens.processing import identity_store as store
from fieldlens.processing import tables as t
from fieldlens.processing.live_budget import failure_text
from fieldlens.processing.steps import (
    Checkpoint,
    ChunkPlan,
    DocumentPlan,
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
    """DEPRECATED (TASK-075): unused; the user chooses the pages."""
    pages_per_call: int = 10
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
        reason = getattr(exc, "reason", None)  # ProviderUnavailable: a short, secret-free reason
        return FailureMapping(
            ProcessingFailureCode.PROVIDER_ERROR,
            failure_text(exc.code, reason if isinstance(reason, str) else None),
        )
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
    def max_pages_per_document(self) -> int | None:
        return None  # TASK-075: the user chooses the pages; large selections run in chunks

    @property
    def model_name(self) -> str:
        return self._config.model

    # -- plan (estimate and run share it, so the bound of a call == its estimate) ------------
    def _chunks(self, start: int, end: int) -> list[list[int]]:
        pages = list(range(start, end + 1))
        size = self._config.pages_per_call
        return [pages[i : i + size] for i in range(0, len(pages), size)]

    def _request(self, usable: dict[int, str]) -> ProviderRequest:
        return ProviderRequest(
            model=self._config.model,
            messages=tuple(ir.build_messages(usable)),
            tools=(),
            max_output_tokens=self._config.limits.max_output_tokens,
            effort=self._config.effort,
        )

    def _chunk_plan(
        self, pages: list[int], texts: dict[int, PageText]
    ) -> tuple[ChunkPlan, dict[int, str]]:
        usable = {
            n: texts[n].text for n in pages if texts[n].has_text_layer and texts[n].text.strip()
        }
        missing = tuple(n for n in pages if n not in usable)
        if not usable:
            return ChunkPlan(tuple(pages), missing, 0, 0, ZERO), usable
        request = self._request(usable)
        limits = self._config.limits
        return (
            ChunkPlan(
                tuple(pages),
                missing,
                estimate_input_tokens(request, limits.image_token_bound),
                request.max_output_tokens,
                attempt_upper_bound_usd(request, self._config.pricing, limits.image_token_bound),
            ),
            usable,
        )

    def plan_document(self, storage_key: str, start: int, end: int) -> DocumentPlan:
        """Read the selected pages locally and bound every call exactly as the runner will."""
        texts = {n: self._page_text(storage_key, n) for n in range(start, end + 1)}
        chunks = tuple(self._chunk_plan(c, texts)[0] for c in self._chunks(start, end))
        pricing = self._config.pricing
        return DocumentPlan(chunks, pricing.input_usd_per_mtok, pricing.output_usd_per_mtok)

    # -- one document -----------------------------------------------------------------------
    def run_document(
        self, task: DocumentTask, provider: PageProvider, checkpoint: Checkpoint
    ) -> None:
        pages = list(task.pages)
        with session_scope(self._factory) as s:
            forced = bool(
                s.execute(
                    select(pr.c.force_refresh).where(
                        pr.c.project_id == task.project_id, pr.c.run_id == task.run_id
                    )
                ).scalar_one()
            )
            cached = (
                None
                if forced  # a confirmed forced run always reads again; the estimate is full price
                else store.find_cached(
                    s, task.project_id, task.document_id, task.page_start, task.page_end
                )
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
        planned = [self._chunk_plan(c, texts) for c in self._chunks(task.page_start, task.page_end)]
        all_usable = {n: text for _, usable in planned for n, text in usable.items()}
        if not all_usable:
            self._persist(task, provider, ir.no_text_outcome(), None, None, ZERO)
            self._charge(pages, ZERO, checkpoint)
            return

        outcomes: list[ir.ModelOutcome] = []
        replies: list[str] = []
        in_tok = out_tok = 0
        total_cost = ZERO
        calls = sum(1 for plan, _ in planned if plan.calls)
        called = 0
        for plan, usable in planned:
            chunk_pages = list(plan.pages)
            if not usable:
                self._charge(chunk_pages, ZERO, checkpoint)  # no text layer: no call, no spend
                continue
            called += 1
            label = (
                f"chunk {called} of {calls} (pages {plan.pages[0]}-{plan.pages[-1]}): "
                if calls > 1
                else ""
            )
            unit = WorkUnit(
                provider=self._provider,
                ledger=self._ledger,
                period_id=self._config.period_id,
                pricing_id=self._config.pricing_id,
                pricing=self._config.pricing,
                model=self._config.model,
                request_key=f"doc-identity:{task.run_id}:{task.document_id}"
                + (f":{called}" if calls > 1 else ""),
                work_unit=(
                    f"doc-identity:{task.document_id}" + (f":{called}" if calls > 1 else "")
                )[:120],
                limits=self._limits(plan.bound_usd),
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
            cost = quantize(Decimal(unit.closed.committed_usd if unit.closed else ZERO))

            outcome: ir.ModelOutcome | None = None
            reply_text: str | None = None
            if failure is None and response is not None:
                try:
                    reply_text = response.text()
                    outcome = ir.validate(ir.parse_output(reply_text), usable)
                except ir.OutputError as exc:
                    failure = exc
            if failure is not None or outcome is None or response is None:
                assert failure is not None
                mapped = map_failure(failure)
                self._charge(chunk_pages, cost, checkpoint)  # a billed failure is real spend
                if isinstance(mapped, RunStop):
                    raise mapped
                raise PageFailure(mapped.code, label + mapped.message, retryable=True)
            outcomes.append(outcome)
            if reply_text is not None:
                replies.append(
                    f"--- {label.rstrip(': ')} ---\n{reply_text}" if label else reply_text
                )
            usage = response.usage
            in_tok += (usage.input_tokens if usage else None) or 0
            out_tok += (usage.output_tokens if usage else None) or 0
            total_cost += cost
            self._charge(chunk_pages, cost, checkpoint)

        merged = ir.with_partial_no_text_warning(
            ir.merge_outcomes(outcomes),
            sum(len(plan.no_text_pages) for plan, _ in planned),
            len(pages),
        )
        self._persist(
            task,
            provider,
            merged,
            in_tok or None,
            out_tok or None,
            quantize(total_cost),
            "\n\n".join(replies) if replies else None,
        )

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

    def _limits(self, reserved: Decimal) -> RequestLimits:
        """Reservation of one call == its pre-flight bound x ``max_attempts`` (retry headroom).

        The confirmed estimate stays the sum of single-call bounds; a transient retry can add at
        most one more bound per call (spec section 8). Spend is still booked from attempts."""
        base = self._config.limits
        return RequestLimits(
            max_attempts=base.max_attempts,
            max_tool_calls=0,
            deadline_s=base.deadline_s,
            max_output_tokens=base.max_output_tokens,
            max_reserved_usd=quantize(reserved * base.max_attempts),
            image_token_bound=base.image_token_bound,
            retry_backoff_s=base.retry_backoff_s,
            default_effort=base.default_effort,
        )

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
        reply_text: str | None = None,
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
                raw_reply=reply_text,
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

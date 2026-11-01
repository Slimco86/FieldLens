"""Processing-run service: estimate, separate confirm, cancel, retry and read models (TASK-054).

Nothing here spends: an estimate only reads page counts; ``confirm`` queues a run for the runner,
which (this increment) uses the stub provider. Every statement is project-qualified.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldlens.assistant.tables import spend_reservation
from fieldlens.candidates.pages import PageError, PageRenderer
from fieldlens.config import Settings
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.imports import DocumentCategory, ExtractionState
from fieldlens.contracts.processing import (
    DocumentProcessingState,
    DocumentProcessingStateList,
    DocumentProcessingStatus,
    ProcessingDocumentSelection,
    ProcessingDocumentState,
    ProcessingEstimate,
    ProcessingFailureCode,
    ProcessingPageRange,
    ProcessingProvider,
    ProcessingRoute,
    ProcessingRun,
    ProcessingRunDocument,
    ProcessingRunPage,
    ProcessingRunStatus,
    ProcessingRunSummary,
)
from fieldlens.evidence.storage import BlobStore
from fieldlens.persistence import models as m
from fieldlens.processing import tables as t
from fieldlens.processing.steps import Pricing, quantize

pr, prd = t.processing_run, t.processing_run_document
ZERO = Decimal("0")
ACTIVE_RUN = ("queued", "running")
RETRYABLE_DOCUMENT_STATES = ("failed", "cancelled", "interrupted")
RETRYABLE_RUN_STATUSES = ("failed", "partial", "cancelled", "interrupted")
_BUDGET_LOCK_KEY = "fieldlens.processing.budget"


def _not_found(what: str) -> ContractError:
    return ContractError(ErrorCode.NOT_FOUND, f"{what} not found", 404)


def _conflict(message: str, reason: str, **details: Any) -> ContractError:
    return ContractError(ErrorCode.CONFLICT, message, 409, {"reason": reason, **details})


def _refused(message: str, refusals: list[dict[str, Any]]) -> ContractError:
    return ContractError(ErrorCode.VALIDATION_ERROR, message, 422, {"refusals": refusals})


@dataclass(frozen=True)
class DocInfo:
    document_id: UUID
    original_filename: str
    storage_key: str
    format_family: str
    storage_state: str | None
    extraction_state: str | None
    user_labels: tuple[str, ...]
    source_revision_id: UUID | None


class PageCounter:
    """Page counts of immutable stored PDFs (CPU/IO in pdfium), memoized by storage key."""

    def __init__(self, store: BlobStore, limit: int = 512) -> None:
        self._renderer = PageRenderer(store, concurrency=2)
        self._cache: OrderedDict[str, int] = OrderedDict()
        self._lock = threading.Lock()
        self._limit = limit

    def count(self, storage_key: str) -> int:
        with self._lock:
            if storage_key in self._cache:
                self._cache.move_to_end(storage_key)
                return self._cache[storage_key]
        value = self._renderer.page_count(storage_key)
        with self._lock:
            self._cache[storage_key] = value
            while len(self._cache) > self._limit:
                self._cache.popitem(last=False)
        return value

    def fresh(self, storage_key: str) -> int:
        """Uncached count (run time re-check)."""
        return self._renderer.page_count(storage_key)


# -- budget -----------------------------------------------------------------------------------
def lock_budget(session: Session) -> None:
    """Serialize budget-affecting writes across projects (the USD 5 cap is aggregate)."""
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": _BUDGET_LOCK_KEY})


def remaining_budget(session: Session, settings: Settings) -> Decimal:
    """Total cap minus recorded ledger spend minus confirmed-but-unfinished run estimates."""
    ledger = session.execute(
        select(func.coalesce(func.sum(spend_reservation.c.committed_usd), 0))
    ).scalar_one()
    held = session.execute(
        select(func.coalesce(func.sum(pr.c.confirmed_usd), 0)).where(pr.c.status.in_(ACTIVE_RUN))
    ).scalar_one()
    return max(quantize(settings.processing_total_cap_usd - Decimal(ledger) - Decimal(held)), ZERO)


# -- documents --------------------------------------------------------------------------------
def load_documents(session: Session, project_id: UUID, ids: Sequence[UUID]) -> dict[UUID, DocInfo]:
    if not ids:
        return {}
    sd, dp, dc = m.source_document, m.document_processing, m.document_classification
    rows = session.execute(
        select(
            sd.c.document_id,
            sd.c.original_filename,
            sd.c.storage_key,
            sd.c.format_family,
            dp.c.storage_state,
            dp.c.extraction_state,
            dc.c.user_categories,
        )
        .select_from(
            sd.outerjoin(
                dp, (dp.c.project_id == sd.c.project_id) & (dp.c.document_id == sd.c.document_id)
            ).outerjoin(
                dc, (dc.c.project_id == sd.c.project_id) & (dc.c.document_id == sd.c.document_id)
            )
        )
        .where(sd.c.project_id == project_id, sd.c.document_id.in_(list(ids)))
    ).all()
    out: dict[UUID, DocInfo] = {}
    for r in rows:
        revision = session.execute(
            select(m.source_revision_document.c.source_revision_id)
            .join(
                m.source_revision,
                m.source_revision.c.source_revision_id
                == m.source_revision_document.c.source_revision_id,
            )
            .where(
                m.source_revision_document.c.project_id == project_id,
                m.source_revision_document.c.document_id == r.document_id,
            )
            .order_by(
                m.source_revision.c.created_at.desc(),
                m.source_revision_document.c.source_revision_id.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        out[r.document_id] = DocInfo(
            r.document_id,
            r.original_filename,
            r.storage_key,
            r.format_family,
            r.storage_state,
            r.extraction_state,
            tuple(r.user_categories or ()),
            revision,
        )
    return out


def _active_documents(session: Session, project_id: UUID, ids: Sequence[UUID]) -> set[UUID]:
    rows = session.execute(
        select(prd.c.document_id).where(
            prd.c.project_id == project_id,
            prd.c.document_id.in_(list(ids)),
            prd.c.state.in_(("pending", "running")),
        )
    ).all()
    return {r.document_id for r in rows}


def _fingerprint(selection: Sequence[tuple[UUID, int, int]]) -> str:
    canonical = json.dumps(sorted((str(d), a, b) for d, a, b in selection), separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


# -- estimate ---------------------------------------------------------------------------------
def create_estimate(
    session: Session,
    settings: Settings,
    counter: PageCounter,
    pricing: Pricing,
    provider: str,
    step: str,
    project_id: UUID,
    selections: Sequence[ProcessingDocumentSelection],
    idempotency_key: str | None,
    retry_of: UUID | None = None,
) -> ProcessingRun:
    if (
        session.execute(
            select(m.project.c.project_id).where(m.project.c.project_id == project_id)
        ).first()
        is None
    ):
        raise _not_found("project")
    ids = [s.document_id for s in selections]
    refusals: list[dict[str, Any]] = []
    if len(set(ids)) != len(ids):
        raise _refused("a document can be selected once", [{"reason": "duplicate_document"}])
    docs = load_documents(session, project_id, ids)
    cap = settings.processing_max_pages
    planned: list[tuple[DocInfo, int, int, int]] = []
    for sel in selections:
        doc = docs.get(sel.document_id)
        base = {"document_id": str(sel.document_id)}
        if doc is None:
            refusals.append({**base, "reason": "unknown_document"})
            continue
        if doc.format_family != "pdf":
            refusals.append({**base, "reason": "not_a_pdf", "format": doc.format_family})
            continue
        if doc.storage_state != "stored":
            refusals.append({**base, "reason": "not_stored", "storage_state": doc.storage_state})
            continue
        try:
            pages = counter.count(doc.storage_key)
        except PageError as exc:
            refusals.append({**base, "reason": "unreadable_pdf", "code": exc.code})
            continue
        if sel.pages is None:
            if pages > cap:
                refusals.append(
                    {
                        **base,
                        "reason": "page_cap_exceeded",
                        "page_count": pages,
                        "max_pages": cap,
                        "hint": f"choose a page range of at most {cap} pages",
                    }
                )
                continue
            start, end = 1, pages
        else:
            start, end = sel.pages.page_start, sel.pages.page_end
            if end > pages:
                refusals.append(
                    {**base, "reason": "invalid_page_range", "page_count": pages, "max_pages": cap}
                )
                continue
            if end - start + 1 > cap:
                refusals.append(
                    {**base, "reason": "range_exceeds_cap", "page_count": pages, "max_pages": cap}
                )
                continue
        if pages == 0:
            refusals.append({**base, "reason": "empty_pdf", "page_count": 0})
            continue
        planned.append((doc, pages, start, end))
    if refusals:
        raise _refused(
            "some documents cannot be processed as selected; nothing was estimated", refusals
        )

    fingerprint = _fingerprint([(d.document_id, a, b) for d, _, a, b in planned])
    lock_budget(session)
    if idempotency_key is not None:
        prior = session.execute(
            select(pr.c.run_id, pr.c.request_fingerprint).where(
                pr.c.project_id == project_id, pr.c.idempotency_key == idempotency_key
            )
        ).first()
        if prior is not None:
            if prior.request_fingerprint != fingerprint:
                raise _conflict(
                    "idempotency key was used for a different selection", "idempotency_conflict"
                )
            return get_run(session, settings, project_id, prior.run_id)
    busy = _active_documents(session, project_id, ids)
    if busy:
        raise _conflict(
            "a selected document is already queued or running",
            "document_already_processing",
            document_ids=sorted(str(d) for d in busy),
        )

    in_tok = settings.processing_input_tokens_per_page
    out_tok = settings.processing_output_tokens_per_page
    per_page = pricing.cost(in_tok, out_tok)
    total_pages = sum(e - s + 1 for _, _, s, e in planned)
    estimated = quantize(per_page * total_pages)
    remaining = remaining_budget(session, settings)
    run_id: UUID = session.execute(
        insert(pr)
        .values(
            project_id=project_id,
            status="estimated",
            step=step,
            provider=provider,
            route=ProcessingRoute.MODEL.value,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            retry_of_run_id=retry_of,
            estimated_pages=total_pages,
            estimated_input_tokens=in_tok * total_pages,
            estimated_output_tokens=out_tok * total_pages,
            estimated_usd=estimated,
            pricing_source=pricing.source,
            total_cap_usd=settings.processing_total_cap_usd,
            remaining_budget_usd=remaining,
        )
        .returning(pr.c.run_id)
    ).scalar_one()
    for ordinal, (doc, pages, start, end) in enumerate(planned):
        revision = doc.source_revision_id
        if revision is None:
            raise _not_found("document revision")
        session.execute(
            insert(prd).values(
                run_id=run_id,
                document_id=doc.document_id,
                project_id=project_id,
                source_revision_id=revision,
                ordinal=ordinal,
                state="estimated",
                page_count=pages,
                page_start=start,
                page_end=end,
                label_hints=list(doc.user_labels),
                estimated_usd=quantize(per_page * (end - start + 1)),
            )
        )
    return get_run(session, settings, project_id, run_id)


# -- confirm / cancel / retry -----------------------------------------------------------------
def _lock_run(session: Session, project_id: UUID, run_id: UUID) -> Any:
    row = session.execute(
        select(pr).where(pr.c.project_id == project_id, pr.c.run_id == run_id).with_for_update()
    ).first()
    if row is None:
        raise _not_found("processing run")
    return row


def confirm_run(
    session: Session,
    settings: Settings,
    project_id: UUID,
    run_id: UUID,
    estimated_usd: Decimal,
) -> ProcessingRun:
    try:
        if not estimated_usd.is_finite() or not Decimal(0) <= estimated_usd <= Decimal(1_000_000):
            raise InvalidOperation
        echoed = quantize(estimated_usd)
    except InvalidOperation:
        raise _conflict(
            "the confirmed amount is not a valid estimate", "estimate_mismatch"
        ) from None
    lock_budget(session)
    run = _lock_run(session, project_id, run_id)
    if run.status != "estimated":
        if run.confirmed_usd is not None and run.confirmed_usd == echoed:
            return get_run(session, settings, project_id, run_id)  # idempotent replay
        raise _conflict(
            f"run is {run.status}; only an estimated run can be confirmed", "not_estimated"
        )
    if echoed != run.estimated_usd:
        raise _conflict(
            "the confirmed amount does not match the estimate",
            "estimate_mismatch",
            estimated_usd=str(run.estimated_usd),
        )
    remaining = remaining_budget(session, settings)
    if run.estimated_usd > remaining:
        raise _conflict(
            "the estimate exceeds the remaining budget",
            "budget_exceeded",
            estimated_usd=str(run.estimated_usd),
            remaining_budget_usd=str(remaining),
        )
    ids = [
        r.document_id
        for r in session.execute(
            select(prd.c.document_id).where(prd.c.project_id == project_id, prd.c.run_id == run_id)
        )
    ]
    docs = load_documents(session, project_id, ids)
    gone = [str(d) for d in ids if d not in docs or docs[d].storage_state != "stored"]
    if gone:
        raise _conflict("a document is no longer stored", "document_unavailable", document_ids=gone)
    try:
        with session.begin_nested():
            session.execute(
                update(prd)
                .where(prd.c.project_id == project_id, prd.c.run_id == run_id)
                .values(state="pending")
            )
    except IntegrityError as exc:
        raise _conflict(
            "a selected document is already queued or running", "document_already_processing"
        ) from exc
    session.execute(
        update(pr)
        .where(pr.c.run_id == run_id)
        .values(status="queued", confirmed_usd=run.estimated_usd, confirmed_at=func.now())
    )
    return get_run(session, settings, project_id, run_id)


def cancel_run(
    session: Session, settings: Settings, project_id: UUID, run_id: UUID
) -> ProcessingRun:
    run = _lock_run(session, project_id, run_id)
    if run.status == "cancelled" or (run.status == "running" and run.cancel_requested):
        return get_run(session, settings, project_id, run_id)
    if run.status in ("estimated", "queued"):
        started = run.status == "queued"
        session.execute(
            update(prd)
            .where(
                prd.c.project_id == project_id,
                prd.c.run_id == run_id,
                prd.c.state.in_(("estimated", "pending")),
            )
            .values(
                state="cancelled",
                failure_code=ProcessingFailureCode.CANCELLED.value,
                failure_message="cancelled before it started",
                retryable=started,
                finished_at=func.now(),
            )
        )
        session.execute(
            update(pr)
            .where(pr.c.run_id == run_id)
            .values(
                status="cancelled",
                cancel_requested=True,
                error_code=ProcessingFailureCode.CANCELLED.value,
                error_message="cancelled by the user",
                finished_at=func.now(),
            )
        )
    elif run.status == "running":
        session.execute(update(pr).where(pr.c.run_id == run_id).values(cancel_requested=True))
    else:
        raise _conflict(f"run is already {run.status}", "not_cancellable")
    return get_run(session, settings, project_id, run_id)


def retry_run(
    session: Session,
    settings: Settings,
    counter: PageCounter,
    pricing: Pricing,
    provider: str,
    step: str,
    project_id: UUID,
    run_id: UUID,
) -> ProcessingRun:
    """A retry is a *new estimate* for the retryable documents; it spends only after confirm."""
    run = _lock_run(session, project_id, run_id)
    if run.status not in RETRYABLE_RUN_STATUSES:
        raise _conflict(f"run is {run.status}; nothing to retry", "not_retryable")
    rows = session.execute(
        select(prd.c.document_id, prd.c.page_start, prd.c.page_end)
        .where(
            prd.c.project_id == project_id,
            prd.c.run_id == run_id,
            prd.c.state.in_(RETRYABLE_DOCUMENT_STATES),
            prd.c.retryable.is_(True),
        )
        .order_by(prd.c.ordinal)
    ).all()
    if not rows:
        raise _conflict("no retryable documents in this run", "nothing_to_retry")
    selections = [
        ProcessingDocumentSelection(
            document_id=r.document_id,
            pages=ProcessingPageRange(page_start=r.page_start, page_end=r.page_end),
        )
        for r in rows
    ]
    return create_estimate(
        session, settings, counter, pricing, provider, step, project_id, selections, None, run_id
    )


# -- read models ------------------------------------------------------------------------------
def _estimate_dto(session: Session, settings: Settings, run: Any) -> ProcessingEstimate:
    live = run.status == "estimated"
    remaining = remaining_budget(session, settings) if live else run.remaining_budget_usd
    fits = run.estimated_usd <= remaining
    return ProcessingEstimate(
        pages=run.estimated_pages,
        route=ProcessingRoute(run.route),
        provider=ProcessingProvider(run.provider),
        estimated_input_tokens=run.estimated_input_tokens,
        estimated_output_tokens=run.estimated_output_tokens,
        estimated_usd=run.estimated_usd,
        pricing_source=run.pricing_source,
        total_cap_usd=run.total_cap_usd,
        remaining_budget_usd=remaining,
        fits_budget=fits,
        confirmable=live and fits,
    )


def get_run(session: Session, settings: Settings, project_id: UUID, run_id: UUID) -> ProcessingRun:
    run = session.execute(
        select(pr).where(pr.c.project_id == project_id, pr.c.run_id == run_id)
    ).first()
    if run is None:
        raise _not_found("processing run")
    docs = session.execute(
        select(prd, m.source_document.c.original_filename)
        .join(
            m.source_document,
            (m.source_document.c.project_id == prd.c.project_id)
            & (m.source_document.c.document_id == prd.c.document_id),
        )
        .where(prd.c.project_id == project_id, prd.c.run_id == run_id)
        .order_by(prd.c.ordinal)
    ).all()
    return ProcessingRun(
        run_id=run.run_id,
        project_id=run.project_id,
        status=ProcessingRunStatus(run.status),
        step=run.step,
        cancel_requested=run.cancel_requested,
        retry_of_run_id=run.retry_of_run_id,
        estimate=_estimate_dto(session, settings, run),
        confirmed_usd=run.confirmed_usd,
        actual_usd=run.actual_usd,
        attempt_no=run.attempt_no,
        error_code=ProcessingFailureCode(run.error_code) if run.error_code else None,
        error_message=run.error_message,
        documents=[
            ProcessingRunDocument(
                document_id=d.document_id,
                source_revision_id=d.source_revision_id,
                original_filename=d.original_filename,
                ordinal=d.ordinal,
                state=ProcessingDocumentState(d.state),
                page_count=d.page_count,
                pages=ProcessingPageRange(page_start=d.page_start, page_end=d.page_end),
                pages_done=d.pages_done,
                label_hints=[DocumentCategory(c) for c in d.label_hints],
                estimated_usd=d.estimated_usd,
                actual_usd=d.actual_usd,
                failure_code=ProcessingFailureCode(d.failure_code) if d.failure_code else None,
                failure_message=d.failure_message,
                retryable=d.retryable,
                finished_at=d.finished_at,
            )
            for d in docs
        ],
        created_at=run.created_at,
        confirmed_at=run.confirmed_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def list_runs(session: Session, project_id: UUID, limit: int) -> ProcessingRunPage:
    if (
        session.execute(
            select(m.project.c.project_id).where(m.project.c.project_id == project_id)
        ).first()
        is None
    ):
        raise _not_found("project")
    processed = (
        select(func.count())
        .select_from(prd)
        .where(prd.c.run_id == pr.c.run_id, prd.c.state == "processed")
        .scalar_subquery()
    )
    total = (
        select(func.count()).select_from(prd).where(prd.c.run_id == pr.c.run_id).scalar_subquery()
    )
    rows = session.execute(
        select(pr, processed.label("processed_count"), total.label("document_count"))
        .where(pr.c.project_id == project_id)
        .order_by(pr.c.created_at.desc(), pr.c.run_id.desc())
        .limit(limit)
    ).all()
    return ProcessingRunPage(
        items=[
            ProcessingRunSummary(
                run_id=r.run_id,
                status=ProcessingRunStatus(r.status),
                provider=ProcessingProvider(r.provider),
                document_count=r.document_count,
                processed_count=r.processed_count,
                estimated_usd=r.estimated_usd,
                actual_usd=r.actual_usd,
                created_at=r.created_at,
                finished_at=r.finished_at,
            )
            for r in rows
        ]
    )


_STATUS_OF_STATE = {
    "estimated": DocumentProcessingStatus.NOT_STARTED,
    "pending": DocumentProcessingStatus.QUEUED,
    "running": DocumentProcessingStatus.RUNNING,
    "processed": DocumentProcessingStatus.PROCESSED,
    "failed": DocumentProcessingStatus.FAILED,
    "cancelled": DocumentProcessingStatus.CANCELLED,
    "interrupted": DocumentProcessingStatus.INTERRUPTED,
}


def _state_text(
    native: str,
    status: DocumentProcessingStatus,
    no_parser: bool,
    provider: str | None,
    failure: str | None,
) -> str:
    if status is DocumentProcessingStatus.NOT_STARTED:
        if no_parser:
            return "no native parser; model processing available, not started"
        return (
            f"native parsing: {native.replace('_', ' ')}; model processing available, not started"
        )
    if status is DocumentProcessingStatus.QUEUED:
        return "model processing confirmed and queued"
    if status is DocumentProcessingStatus.RUNNING:
        return "model processing running"
    if status is DocumentProcessingStatus.PROCESSED:
        if provider == "stub":
            return "stub processing finished; no data was extracted"
        return "model processing finished"
    if status is DocumentProcessingStatus.FAILED:
        return f"model processing failed ({failure or 'error'}); retry needs a new estimate"
    if status is DocumentProcessingStatus.CANCELLED:
        return "model processing cancelled; retry needs a new estimate"
    return "model processing interrupted, not completed; retry needs a new estimate"


def document_states(
    session: Session, settings: Settings, counter: PageCounter, project_id: UUID
) -> DocumentProcessingStateList:
    latest = session.execute(
        select(m.project.c.latest_source_revision_id).where(m.project.c.project_id == project_id)
    ).one_or_none()
    if latest is None:
        raise _not_found("project")
    revision_id: UUID | None = latest[0]
    if revision_id is None:
        return DocumentProcessingStateList(project_id=project_id, source_revision_id=None, items=[])
    ids = [
        r.document_id
        for r in session.execute(
            select(m.source_revision_document.c.document_id).where(
                m.source_revision_document.c.project_id == project_id,
                m.source_revision_document.c.source_revision_id == revision_id,
            )
        )
    ]
    docs = load_documents(session, project_id, ids)
    last: dict[UUID, Any] = {}
    for r in session.execute(
        select(
            prd.c.document_id,
            prd.c.run_id,
            prd.c.state,
            prd.c.failure_code,
            prd.c.retryable,
            pr.c.provider,
        )
        .join(pr, (pr.c.project_id == prd.c.project_id) & (pr.c.run_id == prd.c.run_id))
        .where(prd.c.project_id == project_id, prd.c.document_id.in_(ids))
        .order_by(pr.c.created_at.asc(), pr.c.run_id.asc())
    ):
        last[r.document_id] = r  # newest wins
    items: list[DocumentProcessingState] = []
    for doc in sorted(docs.values(), key=lambda d: (d.original_filename, str(d.document_id))):
        native = doc.extraction_state or ExtractionState.PENDING_EXTRACTION.value
        pages: int | None = None
        reason: str | None = None
        if doc.format_family != "pdf":
            reason = "not_a_pdf"
        elif doc.storage_state != "stored":
            reason = "not_stored"
        else:
            try:
                pages = counter.count(doc.storage_key)
            except PageError:
                reason = "unreadable_pdf"
        if pages == 0:
            reason = "empty_pdf"
        entry = last.get(doc.document_id)
        status = (
            _STATUS_OF_STATE[entry.state]
            if entry is not None
            else DocumentProcessingStatus.NOT_STARTED
        )
        no_parser = native == ExtractionState.UNSUPPORTED.value
        processable = reason is None and status not in (
            DocumentProcessingStatus.QUEUED,
            DocumentProcessingStatus.RUNNING,
        )
        items.append(
            DocumentProcessingState(
                document_id=doc.document_id,
                original_filename=doc.original_filename,
                page_count=pages,
                native_state=ExtractionState(native),
                no_native_parser=no_parser,
                state_text=(
                    f"not processable: {reason.replace('_', ' ')}"
                    if reason
                    else _state_text(
                        native,
                        status,
                        no_parser,
                        entry.provider if entry else None,
                        entry.failure_code if entry else None,
                    )
                ),
                processable=processable,
                not_processable_reason=reason,
                over_page_cap=pages is not None and pages > settings.processing_max_pages,
                user_labels=[DocumentCategory(c) for c in doc.user_labels],
                processing_status=status,
                last_run_id=entry.run_id if entry else None,
                retryable=bool(entry and entry.retryable),
            )
        )
    return DocumentProcessingStateList(
        project_id=project_id, source_revision_id=revision_id, items=items
    )

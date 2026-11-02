"""Source-inspection extraction routes (read report/records; idempotent re-queue)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.context import PageParams
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.extraction import (
    ExtractedRecordPage,
    ExtractionReport,
    ExtractionRequeue,
    RequeueOutcome,
)
from fieldlens.evidence.storage import BlobStore, VerifyOutcome
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from . import views
from .runner import requeue_document


class RecordQuery(PageParams):
    kind: str | None = Field(default=None, max_length=48)


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _db(request: Request, fn: Any) -> Any:
    factory = request.app.state.session_factory
    if factory is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    try:
        with session_scope(factory) as session:
            return fn(session)
    except OperationalError as exc:
        raise ContractError(
            ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503
        ) from exc


def build_extraction_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/documents/{document_id}/extraction",
        tags=["extraction"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=ExtractionReport)
    def get_report(project_id: UUID, document_id: UUID, request: Request) -> ExtractionReport:
        out: ExtractionReport = _db(request, lambda s: views.report(s, project_id, document_id))
        return out

    @router.get("/records", response_model=ExtractedRecordPage)
    def get_records(
        project_id: UUID,
        document_id: UUID,
        request: Request,
        params: Annotated[RecordQuery, Query()],
    ) -> ExtractedRecordPage:
        page: ExtractedRecordPage = _db(
            request,
            lambda s: views.records(
                s, project_id, document_id, params.kind, params.limit, params.cursor
            ),
        )
        return page

    @router.post(
        "",
        response_model=ExtractionRequeue,
        dependencies=[Depends(_guard_mutation)],
    )
    def requeue(
        project_id: UUID,
        document_id: UUID,
        request: Request,
        retry: Annotated[
            bool, Query(description="Explicit retry of a failed/unsupported run")
        ] = False,
    ) -> ExtractionRequeue:
        store: BlobStore = request.app.state.blob_store
        unreadable: list[str] = []

        def work(session: Any) -> ExtractionRequeue:
            views.require_document(session, project_id, document_id)
            if retry or _storage_state(session, project_id, document_id) != "stored":
                reason = _reverify_original(session, store, project_id, document_id)
                if reason is not None:
                    unreadable.append(reason)
                    return ExtractionRequeue(
                        outcome=RequeueOutcome.UNCHANGED,
                        report=views.report(session, project_id, document_id),
                    )
            queued = requeue_document(session, project_id, document_id, retry=retry)
            session.flush()
            return ExtractionRequeue(
                outcome=RequeueOutcome.QUEUED if queued else RequeueOutcome.UNCHANGED,
                report=views.report(session, project_id, document_id),
            )

        out: ExtractionRequeue = _db(request, work)  # commits the corrected storage state
        if unreadable:
            raise ContractError(
                ErrorCode.CONFLICT,
                "The stored original of this file is not readable "
                f"({unreadable[0]}); re-upload this file to extract it again.",
                409,
                {"reason": "source_unreadable", "check": unreadable[0], "recovery": "re-upload"},
            )
        return out

    return router


def _storage_state(session: Any, project_id: UUID, document_id: UUID) -> str | None:
    state = session.execute(
        select(m.document_processing.c.storage_state).where(
            m.document_processing.c.project_id == project_id,
            m.document_processing.c.document_id == document_id,
        )
    ).scalar_one_or_none()
    return None if state is None else str(state)


def _reverify_original(
    session: Any, store: BlobStore, project_id: UUID, document_id: UUID
) -> str | None:
    """Re-read the stored original and make the storage state match reality: restore ``stored``
    when the bytes verify again, otherwise record ``quarantined``. Returns the failed check
    (e.g. ``missing``) or None when the bytes verify."""
    doc = session.execute(
        select(
            m.source_document.c.storage_key,
            m.source_document.c.sha256,
            m.source_document.c.size_bytes,
        ).where(
            m.source_document.c.project_id == project_id,
            m.source_document.c.document_id == document_id,
        )
    ).one()
    result = store.verify(doc.storage_key, doc.sha256, doc.size_bytes)
    ok = result.outcome is VerifyOutcome.OK
    session.execute(
        update(m.document_processing)
        .where(
            m.document_processing.c.project_id == project_id,
            m.document_processing.c.document_id == document_id,
            m.document_processing.c.storage_state != "pending_verification",
        )
        .values(
            storage_state="stored" if ok else "quarantined",
            detail=None if ok else f"verification_{result.outcome.value}",
            updated_at=func.now(),
        )
    )
    return None if ok else result.outcome.value

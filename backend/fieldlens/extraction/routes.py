"""Source-inspection extraction routes (read report/records; idempotent re-queue)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
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
from fieldlens.persistence.session import session_scope

from . import views
from .runner import requeue_document


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
        params: Annotated[PageParams, Query()],
        kind: Annotated[str | None, Query(max_length=48)] = None,
    ) -> ExtractedRecordPage:
        page: ExtractedRecordPage = _db(
            request,
            lambda s: views.records(s, project_id, document_id, kind, params.limit, params.cursor),
        )
        return page

    @router.post(
        "",
        response_model=ExtractionRequeue,
        dependencies=[Depends(_guard_mutation)],
    )
    def requeue(project_id: UUID, document_id: UUID, request: Request) -> ExtractionRequeue:
        def work(session: Any) -> ExtractionRequeue:
            views.require_document(session, project_id, document_id)
            queued = requeue_document(session, project_id, document_id)
            session.flush()
            return ExtractionRequeue(
                outcome=RequeueOutcome.QUEUED if queued else RequeueOutcome.UNCHANGED,
                report=views.report(session, project_id, document_id),
            )

        out: ExtractionRequeue = _db(request, work)
        return out

    return router

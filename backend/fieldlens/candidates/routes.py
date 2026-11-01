"""Read-only candidate endpoints (AX-7): state, reason, validator outcome, locator, label."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens.contracts.candidates import CandidateQuery, ExtractionCandidatePage
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.persistence.session import session_scope

from . import repository


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


def build_candidates_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}",
        tags=["extraction-candidates"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("/extraction-candidates", response_model=ExtractionCandidatePage)
    def list_project(
        project_id: UUID, request: Request, params: Annotated[CandidateQuery, Query()]
    ) -> ExtractionCandidatePage:
        out: ExtractionCandidatePage = _db(
            request, lambda s: repository.list_candidates(s, project_id, params)
        )
        return out

    @router.get(
        "/documents/{document_id}/extraction-candidates", response_model=ExtractionCandidatePage
    )
    def list_document(
        project_id: UUID,
        document_id: UUID,
        request: Request,
        params: Annotated[CandidateQuery, Query()],
    ) -> ExtractionCandidatePage:
        def work(s: Any) -> ExtractionCandidatePage:
            repository.document_in_project(s, project_id, document_id)
            return repository.list_candidates(s, project_id, params, document_id=document_id)

        out: ExtractionCandidatePage = _db(request, work)
        return out

    return router

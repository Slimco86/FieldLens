"""Project-scoped, read-only retrieval routes (no mutation guard: nothing is written)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.retrieval import EvidenceSearchQuery, EvidenceSearchResult, SourceCoverage

from .search import RetrievalService


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _service(request: Request) -> RetrievalService:
    service: RetrievalService | None = request.app.state.retrieval
    if service is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    return service


def build_retrieval_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/retrieval",
        tags=["retrieval"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("/search", response_model=EvidenceSearchResult)
    def search_evidence(
        project_id: UUID, request: Request, params: Annotated[EvidenceSearchQuery, Query()]
    ) -> EvidenceSearchResult:
        try:
            return _service(request).search_evidence(
                project_id,
                params.q,
                source_revision_id=params.source_revision_id,
                document_ids=params.document_id or None,
                limit=params.limit,
            )
        except OperationalError as exc:
            raise ContractError(
                ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503
            ) from exc

    @router.get("/coverage", response_model=SourceCoverage)
    def source_coverage(
        project_id: UUID,
        request: Request,
        source_revision_id: Annotated[UUID | None, Query()] = None,
    ) -> SourceCoverage:
        try:
            return _service(request).source_coverage(project_id, source_revision_id)
        except OperationalError as exc:
            raise ContractError(
                ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503
            ) from exc

    return router

"""Project-scoped, read-only series routes (nothing is written; responses are never cached)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.series import (
    SeriesInfo,
    SeriesList,
    SeriesListQuery,
    SeriesWindow,
    SeriesWindowQuery,
)

from .service import SeriesService


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _service(request: Request) -> SeriesService:
    service: SeriesService | None = request.app.state.series
    if service is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    return service


def _unavailable(exc: OperationalError) -> ContractError:
    return ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)


def build_series_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/series",
        tags=["series"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=SeriesList)
    def list_series(
        project_id: UUID, request: Request, params: Annotated[SeriesListQuery, Query()]
    ) -> SeriesList:
        try:
            return _service(request).list_series(
                project_id,
                wellbore_label=params.wellbore_label,
                kind=params.kind,
                mnemonic=params.mnemonic,
                document_id=params.document_id,
                limit=params.limit,
                offset=params.offset,
            )
        except OperationalError as exc:
            raise _unavailable(exc) from exc

    @router.get("/{series_id}", response_model=SeriesInfo)
    def get_series(project_id: UUID, series_id: UUID, request: Request) -> SeriesInfo:
        try:
            return _service(request).get_series(project_id, series_id)
        except OperationalError as exc:
            raise _unavailable(exc) from exc

    @router.get("/{series_id}/window", response_model=SeriesWindow)
    def get_window(
        project_id: UUID,
        series_id: UUID,
        request: Request,
        params: Annotated[SeriesWindowQuery, Query()],
    ) -> SeriesWindow:
        try:
            return _service(request).get_window(
                project_id,
                series_id,
                start=params.from_,
                end=params.to,
                max_points=params.max_points,
                resolution=params.resolution,
            )
        except OperationalError as exc:
            raise _unavailable(exc) from exc

    return router

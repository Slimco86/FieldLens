"""Project-scoped read-only chart routes (TASK-100): one wellbore chart set, one field chart set."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens.contracts.charts import FieldChartSet, WellboreChartSet
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.persistence.session import session_scope

from .service import ChartService

_service = ChartService()


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


def build_charts_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}",
        tags=["charts"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("/wellbores/{wellbore_id}/charts", response_model=WellboreChartSet)
    def wellbore_charts(
        project_id: UUID,
        wellbore_id: UUID,
        request: Request,
        as_of: str | None = Query(default=None),
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = Query(default=None),
    ) -> WellboreChartSet:
        out: WellboreChartSet = _db(
            request,
            lambda s: _service.wellbore_charts(
                s, project_id, wellbore_id, as_of=as_of, from_=from_, to=to
            ),
        )
        return out

    @router.get("/charts/field", response_model=FieldChartSet)
    def field_charts(
        project_id: UUID,
        request: Request,
        as_of: str | None = Query(default=None),
        from_: str | None = Query(default=None, alias="from"),
        to: str | None = Query(default=None),
    ) -> FieldChartSet:
        out: FieldChartSet = _db(
            request,
            lambda s: _service.field_charts(s, project_id, as_of=as_of, from_=from_, to=to),
        )
        return out

    return router

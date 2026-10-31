"""Read-only, project-scoped agent activity log endpoints (AX-10)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens.contracts.activity import AgentUnitDetail, AgentUnitPage, AgentUnitQuery
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.persistence.session import session_scope

from . import views


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


def build_activity_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/agent-units",
        tags=["agent-activity"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=AgentUnitPage)
    def list_units(
        project_id: UUID, request: Request, params: Annotated[AgentUnitQuery, Query()]
    ) -> AgentUnitPage:
        out: AgentUnitPage = _db(request, lambda s: views.list_units(s, project_id, params))
        return out

    @router.get("/{unit_id}", response_model=AgentUnitDetail)
    def get_unit(project_id: UUID, unit_id: UUID, request: Request) -> AgentUnitDetail:
        out: AgentUnitDetail = _db(request, lambda s: views.get_unit(s, project_id, unit_id))
        return out

    return router

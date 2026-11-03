"""Project-scoped read-only wellbore trajectory route (TASK-083)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.trajectory import WellboreTrajectory
from fieldlens.persistence.session import session_scope

from . import service


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


def build_trajectory_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/wellbores/{wellbore_id}/trajectory",
        tags=["trajectory"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=WellboreTrajectory)
    def trajectory(project_id: UUID, wellbore_id: UUID, request: Request) -> WellboreTrajectory:
        out: WellboreTrajectory = _db(
            request, lambda s: service.wellbore_trajectory(s, project_id, wellbore_id)
        )
        return out

    return router

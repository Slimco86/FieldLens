"""Project/wellbore-scoped read-only formation layer routes (TASK-097, FL-024)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens.contracts.context_layers import FormationLayerSet
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.persistence.session import session_scope

from . import formations


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


def build_formations_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}",
        tags=["formations"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("/formations", response_model=FormationLayerSet)
    def project_formations(project_id: UUID, request: Request) -> FormationLayerSet:
        out: FormationLayerSet = _db(
            request, lambda s: formations.formation_layer_set(s, project_id, None)
        )
        return out

    @router.get("/wellbores/{wellbore_id}/formations", response_model=FormationLayerSet)
    def wellbore_formations(
        project_id: UUID, wellbore_id: UUID, request: Request
    ) -> FormationLayerSet:
        out: FormationLayerSet = _db(
            request, lambda s: formations.formation_layer_set(s, project_id, wellbore_id)
        )
        return out

    return router

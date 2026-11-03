"""Project-scoped asset-spec routes: current spec, history, stub generation (no accept step)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.asset_spec import (
    AssetSpecGenerateRequest,
    AssetSpecHistory,
    VisualAssetSpecRecord,
)
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.persistence.session import session_scope

from . import service


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


def build_asset_spec_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/wellbores/{wellbore_id}/asset-spec",
        tags=["asset-spec"],
        responses={
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=VisualAssetSpecRecord)
    def current(project_id: UUID, wellbore_id: UUID, request: Request) -> VisualAssetSpecRecord:
        out: VisualAssetSpecRecord = _db(
            request, lambda s: service.get_current(s, project_id, wellbore_id)
        )
        return out

    @router.get("/history", response_model=AssetSpecHistory)
    def history(project_id: UUID, wellbore_id: UUID, request: Request) -> AssetSpecHistory:
        out: AssetSpecHistory = _db(request, lambda s: service.history(s, project_id, wellbore_id))
        return out

    @router.post(
        "/generate",
        response_model=VisualAssetSpecRecord,
        status_code=201,
        dependencies=[Depends(_guard_mutation)],
    )
    def generate(
        project_id: UUID,
        wellbore_id: UUID,
        body: AssetSpecGenerateRequest,
        request: Request,
    ) -> VisualAssetSpecRecord:
        """Stub designer (no model): builds a spec from the wellbore's equipment candidates;
        becomes the current spec only when valid and non-empty."""
        out: VisualAssetSpecRecord = _db(
            request, lambda s: service.generate_stub(s, project_id, wellbore_id, body)
        )
        return out

    return router

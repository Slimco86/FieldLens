"""Project-scoped reconstruction-run routes: estimate, separate confirm, list, detail, cancel, retry."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.reconstruction import (
    ReconstructionConfirmRequest,
    ReconstructionEstimate,
    ReconstructionEstimateRequest,
    ReconstructionRun,
    ReconstructionRunPage,
)
from fieldlens.persistence.session import session_scope
from fieldlens.reconstruction import service
from fieldlens.reconstruction.runtime import ReconstructionRuntime


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _runtime(request: Request) -> ReconstructionRuntime:
    runtime: ReconstructionRuntime | None = request.app.state.reconstruction
    if runtime is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    return runtime


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


def build_reconstruction_router() -> APIRouter:
    # Sync handlers run in the threadpool: exposure queries stay off the event loop.
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/reconstruction-runs",
        tags=["reconstruction"],
        responses={
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        dependencies=[Depends(_no_store)],
    )

    @router.post(
        "/estimates",
        response_model=ReconstructionEstimate,
        status_code=201,
        dependencies=[Depends(_guard_mutation)],
    )
    def create_estimate(
        project_id: UUID, body: ReconstructionEstimateRequest, request: Request
    ) -> ReconstructionEstimate:
        rt, settings = _runtime(request), request.app.state.settings
        out: ReconstructionEstimate = _db(
            request,
            lambda s: service.create_estimate(s, settings, rt.executors, project_id, body),
        )
        return out

    @router.post(
        "/estimates/{estimate_id}/confirm",
        response_model=ReconstructionRunPage,
        status_code=202,
        dependencies=[Depends(_guard_mutation)],
    )
    def confirm(
        project_id: UUID,
        estimate_id: UUID,
        body: ReconstructionConfirmRequest,
        request: Request,
    ) -> ReconstructionRunPage:
        settings = request.app.state.settings
        out: ReconstructionRunPage = _db(
            request,
            lambda s: service.confirm_estimate(
                s, settings, project_id, estimate_id, body.estimated_usd
            ),
        )
        return out

    @router.get("", response_model=ReconstructionRunPage)
    def list_runs(
        project_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=100)] = 50,
        wellbore_id: UUID | None = None,
    ) -> ReconstructionRunPage:
        out: ReconstructionRunPage = _db(
            request, lambda s: service.list_runs(s, project_id, limit, wellbore_id)
        )
        return out

    @router.get("/{run_id}", response_model=ReconstructionRun)
    def get_run(project_id: UUID, run_id: UUID, request: Request) -> ReconstructionRun:
        out: ReconstructionRun = _db(request, lambda s: service.get_run(s, project_id, run_id))
        return out

    @router.post(
        "/{run_id}/cancel",
        response_model=ReconstructionRun,
        dependencies=[Depends(_guard_mutation)],
    )
    def cancel(project_id: UUID, run_id: UUID, request: Request) -> ReconstructionRun:
        out: ReconstructionRun = _db(request, lambda s: service.cancel_run(s, project_id, run_id))
        return out

    @router.post(
        "/{run_id}/retry",
        response_model=ReconstructionEstimate,
        status_code=201,
        dependencies=[Depends(_guard_mutation)],
    )
    def retry(project_id: UUID, run_id: UUID, request: Request) -> ReconstructionEstimate:
        rt, settings = _runtime(request), request.app.state.settings
        out: ReconstructionEstimate = _db(
            request,
            lambda s: service.retry_run(s, settings, rt.executors, project_id, run_id),
        )
        return out

    return router

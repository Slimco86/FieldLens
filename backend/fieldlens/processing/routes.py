"""Project-scoped processing routes: document state, estimate, confirm, state, cancel, retry."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.processing import (
    DocumentProcessingStateList,
    ProcessingConfirmRequest,
    ProcessingEstimateRequest,
    ProcessingRun,
    ProcessingRunPage,
)
from fieldlens.persistence.session import session_scope
from fieldlens.processing import service
from fieldlens.processing.runtime import ProcessingRuntime


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _runtime(request: Request) -> ProcessingRuntime:
    runtime: ProcessingRuntime | None = request.app.state.processing
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


def build_processing_router() -> APIRouter:
    # Sync handlers run in the threadpool: page counting and DB work stay off the event loop.
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/processing",
        tags=["processing"],
        responses={
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        dependencies=[Depends(_no_store)],
    )

    @router.get("/documents", response_model=DocumentProcessingStateList)
    def document_states(project_id: UUID, request: Request) -> DocumentProcessingStateList:
        rt, settings = _runtime(request), request.app.state.settings
        out: DocumentProcessingStateList = _db(
            request, lambda s: service.document_states(s, settings, rt.counter, project_id)
        )
        return out

    @router.post(
        "/runs/estimates",
        response_model=ProcessingRun,
        status_code=201,
        dependencies=[Depends(_guard_mutation)],
    )
    def create_estimate(
        project_id: UUID, body: ProcessingEstimateRequest, request: Request
    ) -> ProcessingRun:
        rt, settings = _runtime(request), request.app.state.settings
        out: ProcessingRun = _db(
            request,
            lambda s: service.create_estimate(
                s,
                settings,
                rt.counter,
                rt.provider.pricing,
                rt.provider.name,
                rt.step.name,
                project_id,
                body.documents,
                body.idempotency_key,
            ),
        )
        return out

    @router.get("/runs", response_model=ProcessingRunPage)
    def list_runs(
        project_id: UUID, request: Request, limit: Annotated[int, Query(ge=1, le=100)] = 50
    ) -> ProcessingRunPage:
        out: ProcessingRunPage = _db(request, lambda s: service.list_runs(s, project_id, limit))
        return out

    @router.get("/runs/{run_id}", response_model=ProcessingRun)
    def get_run(project_id: UUID, run_id: UUID, request: Request) -> ProcessingRun:
        settings = request.app.state.settings
        out: ProcessingRun = _db(
            request, lambda s: service.get_run(s, settings, project_id, run_id)
        )
        return out

    @router.post(
        "/runs/{run_id}/confirm",
        response_model=ProcessingRun,
        status_code=202,
        dependencies=[Depends(_guard_mutation)],
    )
    def confirm(
        project_id: UUID, run_id: UUID, body: ProcessingConfirmRequest, request: Request
    ) -> ProcessingRun:
        settings = request.app.state.settings
        out: ProcessingRun = _db(
            request,
            lambda s: service.confirm_run(s, settings, project_id, run_id, body.estimated_usd),
        )
        return out

    @router.post(
        "/runs/{run_id}/cancel",
        response_model=ProcessingRun,
        dependencies=[Depends(_guard_mutation)],
    )
    def cancel(project_id: UUID, run_id: UUID, request: Request) -> ProcessingRun:
        settings = request.app.state.settings
        out: ProcessingRun = _db(
            request, lambda s: service.cancel_run(s, settings, project_id, run_id)
        )
        return out

    @router.post(
        "/runs/{run_id}/retry",
        response_model=ProcessingRun,
        status_code=201,
        dependencies=[Depends(_guard_mutation)],
    )
    def retry(project_id: UUID, run_id: UUID, request: Request) -> ProcessingRun:
        rt, settings = _runtime(request), request.app.state.settings
        out: ProcessingRun = _db(
            request,
            lambda s: service.retry_run(
                s,
                settings,
                rt.counter,
                rt.provider.pricing,
                rt.provider.name,
                rt.step.name,
                project_id,
                run_id,
            ),
        )
        return out

    return router

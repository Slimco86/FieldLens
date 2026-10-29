"""Job status and cancellation routes (project-scoped)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.imports import Job
from fieldlens.persistence.session import session_scope

from . import repository as repo

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _db(request: Request, fn: Any) -> Any:
    factory = request.app.state.session_factory
    unavailable = ContractError(
        ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503
    )
    if factory is None:
        raise unavailable
    try:
        with session_scope(factory) as session:
            return fn(session)
    except OperationalError as exc:
        raise unavailable from exc


def build_jobs_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/jobs",
        tags=["jobs"],
        responses=_ERRORS,
        dependencies=[Depends(_no_store)],
    )

    @router.get("/{job_id}", response_model=Job)
    def get_job(project_id: UUID, job_id: UUID, request: Request) -> Job:
        job: Job = _db(request, lambda s: repo.get_job(s, project_id, job_id))
        return job

    @router.post(
        "/{job_id}/cancel",
        status_code=202,
        response_model=Job,
        dependencies=[Depends(_guard_mutation)],
    )
    def cancel_job(project_id: UUID, job_id: UUID, request: Request) -> Job:
        def work(session: Any) -> Job:
            repo.request_cancel(session, project_id, job_id)
            return repo.get_job(session, project_id, job_id)

        job: Job = _db(request, work)
        return job

    return router

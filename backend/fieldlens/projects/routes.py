"""``/api/v1/projects``: reads are open to the local boundary; writes need the session token."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from fieldlens import security
from fieldlens.contracts.context import PageParams
from fieldlens.contracts.errors import ErrorEnvelope
from fieldlens.contracts.identity import Project
from fieldlens.contracts.projects import ProjectCreate, ProjectPage, ProjectUpdate

from .service import ProjectService

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}


def _service(request: Request) -> ProjectService:
    return ProjectService(request.app.state.session_factory)


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


Service = Annotated[ProjectService, Depends(_service)]


def build_projects_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects",
        tags=["projects"],
        responses=_ERRORS,
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=ProjectPage)
    def list_projects(params: Annotated[PageParams, Query()], service: Service) -> ProjectPage:
        return service.list(params)

    @router.post(
        "",
        status_code=201,
        response_model=Project,
        dependencies=[Depends(_guard_mutation)],
    )
    def create_project(body: ProjectCreate, response: Response, service: Service) -> Project:
        created = service.create(body)
        response.headers["Location"] = f"/api/v1/projects/{created.project_id}"
        return created

    @router.get("/{project_id}", response_model=Project)
    def get_project(project_id: UUID, service: Service) -> Project:
        return service.get(project_id)

    @router.patch("/{project_id}", response_model=Project, dependencies=[Depends(_guard_mutation)])
    def update_project(project_id: UUID, body: ProjectUpdate, service: Service) -> Project:
        return service.update(project_id, body)

    return router

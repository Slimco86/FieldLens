"""Project use cases. One transaction per call: a failed write leaves prior values intact."""

from __future__ import annotations

from contextlib import AbstractContextManager
from uuid import UUID

from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.contracts.context import PageInfo, PageParams
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.identity import Project
from fieldlens.contracts.projects import (
    ProjectCreate,
    ProjectDeleteRequest,
    ProjectDeletionPreview,
    ProjectDeletionStatus,
    ProjectPage,
    ProjectUpdate,
)
from fieldlens.persistence.session import session_scope

from . import purge, repository

SessionFactory = sessionmaker[Session] | None


def _unavailable() -> ContractError:
    return ContractError(
        ErrorCode.SERVICE_UNAVAILABLE, "project storage is unavailable; try again", 503
    )


class ProjectService:
    def __init__(self, factory: SessionFactory) -> None:
        self._factory = factory

    def _scope(self) -> AbstractContextManager[Session]:
        if self._factory is None:
            raise _unavailable()
        return session_scope(self._factory)

    def list(self, params: PageParams) -> ProjectPage:
        try:
            with self._scope() as session:
                items, next_cursor = repository.list_page(session, params.limit, params.cursor)
        except OperationalError as exc:
            raise _unavailable() from exc
        return ProjectPage(items=items, page=PageInfo(limit=params.limit, next_cursor=next_cursor))

    def get(self, project_id: UUID) -> Project:
        try:
            with self._scope() as session:
                found = repository.get(session, project_id)
        except OperationalError as exc:
            raise _unavailable() from exc
        if found is None:
            raise _not_found()
        return found

    def create(self, body: ProjectCreate) -> Project:
        try:
            with self._scope() as session:
                return repository.create(session, body.name, body.description)
        except DBAPIError as exc:
            raise _unavailable() from exc

    def update(self, project_id: UUID, body: ProjectUpdate) -> Project:
        values = body.model_dump(exclude_unset=True)
        try:
            with self._scope() as session:
                current = repository.get(session, project_id, for_update=True)
                if current is None:
                    raise _not_found()
                changed = {k: v for k, v in values.items() if getattr(current, k) != v}
                if not changed:
                    return current
                return repository.update_fields(session, project_id, changed)
        except OperationalError as exc:
            raise _unavailable() from exc

    def deletion_preview(self, project_id: UUID) -> ProjectDeletionPreview:
        try:
            with self._scope() as session:
                return purge.preview(session, project_id)
        except OperationalError as exc:
            raise _unavailable() from exc

    def request_deletion(
        self, project_id: UUID, body: ProjectDeleteRequest
    ) -> ProjectDeletionStatus:
        """Phase 1: one transaction; the purge itself runs in the background executor."""
        try:
            with self._scope() as session:
                return purge.request_deletion(session, project_id, body.confirm_name)
        except OperationalError as exc:
            raise _unavailable() from exc


def _not_found() -> ContractError:
    return ContractError(ErrorCode.NOT_FOUND, "project not found", 404)

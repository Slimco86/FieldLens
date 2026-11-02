"""HTTP-boundary guard: a project that is being deleted accepts no mutation (409 project_deleting).

Only ``DELETE /api/v1/projects/{id}`` itself passes (it is the idempotent retry of a failed
deletion). Imports additionally re-check under the project row lock (``lock_project``), which is
what makes the upload-versus-delete race safe; this guard rejects early, before a body is read.
"""

from __future__ import annotations

import re
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.persistence.session import session_scope

from .purge import assert_not_deleting

_PROJECT_PATH = re.compile(r"^/api/v1/projects/([0-9a-fA-F-]{36})(/.*)?$")
_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def target_project(method: str, path: str) -> UUID | None:
    """The project a mutating request addresses, or None when the guard does not apply."""
    if method not in _MUTATING:
        return None
    found = _PROJECT_PATH.match(path)
    if found is None:
        return None
    if method == "DELETE" and not found.group(2):
        return None
    try:
        return UUID(found.group(1))
    except ValueError:
        return None


def check(factory: sessionmaker[Session], project_id: UUID) -> None:
    """Raise ``project_deleting`` (409) when the project is deleting. A database outage is left
    for the route to report as 503."""
    try:
        with session_scope(factory) as session:
            assert_not_deleting(session, project_id)
    except SQLAlchemyError:
        return

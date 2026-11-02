"""Storage verdict writes: a document is ``failed`` only for a genuine, attributed byte problem.

Callers must have passed the storage-root identity check (``StorageRootGuard``) for the process
that reads the bytes; these helpers only write the verdict. Reason codes: ``missing``,
``size_mismatch``, ``hash_mismatch``. ``storage_failed_by`` records the writing process.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.evidence.root_guard import MISMATCH, StorageRootGuard
from fieldlens.evidence.storage import BlobStore, VerifyOutcome, VerifyResult
from fieldlens.persistence import models as m

STORAGE_FAILED_MESSAGE = "Failed: stored copy missing or damaged."
REUPLOAD_MESSAGE = (
    "The stored copy of this file is missing or damaged; re-upload this file to repair it."
)


ROOT_MISMATCH_MESSAGE = (
    "This server's storage folder is not the one this database belongs to, so it will not "
    "read or change stored files. Restart FieldLens with the right storage root."
)


def require_root(request: Any) -> None:
    """API guard: refuse (503 ``storage_root_mismatch``) before touching any stored file."""
    guard: StorageRootGuard | None = request.app.state.root_guard
    if guard is not None and not guard.serves_database(force=True):
        raise root_mismatch_error()


def root_mismatch_error() -> ContractError:
    return ContractError(
        ErrorCode.SERVICE_UNAVAILABLE,
        ROOT_MISMATCH_MESSAGE,
        503,
        {"reason": MISMATCH},
    )


class RootMismatch(Exception):
    """This process's storage root is not the database's root; it must not read or fail files."""


def mark_failed(session: Session, document_id: UUID, reason: str, by: str) -> None:
    session.execute(
        update(m.document_processing)
        .where(
            m.document_processing.c.document_id == document_id,
            m.document_processing.c.storage_state != "pending_verification",
        )
        .values(
            storage_state="failed",
            storage_failure_reason=reason,
            storage_failed_by=by[:300],
            detail=f"verification_{reason}",
            updated_at=func.now(),
        )
    )


def restore_stored(session: Session, document_id: UUID) -> bool:
    """Failed -> stored after the bytes verified. True when a row changed."""
    result = session.execute(
        update(m.document_processing)
        .where(
            m.document_processing.c.document_id == document_id,
            m.document_processing.c.storage_state == "failed",
        )
        .values(
            storage_state="stored",
            storage_failure_reason=None,
            storage_failed_by=None,
            detail=None,
            updated_at=func.now(),
        )
    )
    return bool(getattr(result, "rowcount", 0))


def reverify_document(
    session: Session,
    store: BlobStore,
    guard: StorageRootGuard,
    project_id: UUID,
    document_id: UUID,
    *,
    write_failure: bool = True,
) -> VerifyResult:
    """Re-read the stored original and make the verdict match reality (stored <-> failed).
    Raises ``RootMismatch`` before reading anything when the root identity does not match.
    ``write_failure=False`` leaves an unreadable document's row untouched."""
    if not guard.serves_database(force=True):
        raise RootMismatch(guard.status.reason or "storage root mismatch")
    doc = session.execute(
        select(
            m.source_document.c.storage_key,
            m.source_document.c.sha256,
            m.source_document.c.size_bytes,
        ).where(
            m.source_document.c.project_id == project_id,
            m.source_document.c.document_id == document_id,
        )
    ).one()
    result = store.verify(doc.storage_key, doc.sha256, doc.size_bytes)
    if result.outcome is VerifyOutcome.OK:
        restore_stored(session, document_id)
    elif write_failure:
        mark_failed(session, document_id, result.outcome.value, guard.identity())
    return result


def failure_message(state: str) -> str | None:
    return STORAGE_FAILED_MESSAGE if state == "failed" else None

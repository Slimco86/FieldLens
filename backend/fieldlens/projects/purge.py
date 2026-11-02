"""Project deletion (TASK-071, PW-9): request, cancel in-flight work, then a crash-resumable purge.

Phase 1 (``request_deletion``, one transaction under the project row lock): mark the project
``deleting`` and stop every queued/running unit of work. From then on the HTTP boundary rejects
mutations (409 ``project_deleting``) and ``lock_project`` rejects imports.

Phase 2 (``ProjectPurger``, one background thread): wait for active leases to drain, verify the
storage root, delete ``projects/<id>/`` from disk, then ONE database transaction that sets
``fieldlens.purge_project_id`` (the only way the four immutability guards allow a DELETE, and only
for that project), nulls the circular pointers, deletes every table that has a ``project_id`` in
FK-safe order and finally the project row. Every step is idempotent, so a crash at any point
resumes. The API-spend ledger tables carry no ``project_id`` and are never touched.
"""

from __future__ import annotations

import logging
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.candidates.reconcile import settle_finished_units
from fieldlens.config import Settings
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.identity import ProjectDeletionState
from fieldlens.contracts.projects import ProjectDeletionPreview, ProjectDeletionStatus
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.evidence.storage import BlobStore
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .errors import deleting_error

logger = logging.getLogger(__name__)

DRAIN_TIMEOUT_S = 900.0
_ERROR_MAX = 600

# Children before parents. Self-references (source_revision, wellbore, processing_run,
# reconstruction_run, model_revision) are removed by one DELETE statement, which PostgreSQL checks
# at statement end. The completeness test and ``_uncovered`` fail on any project_id table missing.
PURGE_ORDER: tuple[str, ...] = (
    "agent_step",
    "chunk_embedding",
    "chunk_identifier",
    "extraction_candidate",
    "record_wellbore_link",
    "series_curve",
    "series_axis",
    "extraction_issue",
    "extracted_record",
    "merge_proposal_member",
    "identity_merge",
    "merge_proposal",
    "merge_proposal_run",
    "evidence_chunk",
    "retrieval_index",
    "extraction_run",
    "agent_work_unit",
    "processing_run_document",
    "processing_run",
    "reconstruction_run_stage",
    "reconstruction_run",
    "reconstruction_estimate",
    "document_classification_event",
    "document_classification",
    "document_processing",
    "import_batch",
    "ingest_job_attempt",
    "ingest_job",
    "source_revision_document",
    "wellbore",
    "well",
    "model_revision",
    "source_document",
    "source_revision",
)
# The project row itself is deleted last (after its circular pointers are nulled).


def _now() -> datetime:
    return datetime.now(UTC)


def _not_found() -> ContractError:
    return ContractError(ErrorCode.NOT_FOUND, "project not found", 404)


def assert_not_deleting(session: Session, project_id: UUID) -> None:
    """Raise 409 ``project_deleting`` for a deleting/failed project; unknown ids pass through."""
    state = session.execute(
        select(m.project.c.deletion_state).where(m.project.c.project_id == project_id)
    ).scalar_one_or_none()
    if state is not None and state != ProjectDeletionState.NONE:
        raise deleting_error()


# -- preview -------------------------------------------------------------------------------------


def preview(session: Session, project_id: UUID) -> ProjectDeletionPreview:
    proj = session.execute(
        select(m.project.c.name, m.project.c.deletion_state).where(
            m.project.c.project_id == project_id
        )
    ).one_or_none()
    if proj is None:
        raise _not_found()

    def count(table: str) -> int:
        t = m.metadata.tables[table]
        return int(
            session.execute(
                select(func.count()).select_from(t).where(t.c.project_id == project_id)
            ).scalar_one()
        )

    sd = m.source_document
    stored_bytes = session.execute(
        select(func.coalesce(func.sum(sd.c.size_bytes), 0)).where(sd.c.project_id == project_id)
    ).scalar_one()
    return ProjectDeletionPreview(
        project_id=project_id,
        name=proj.name,
        deletion_state=ProjectDeletionState(proj.deletion_state),
        documents=count("source_document"),
        stored_bytes=int(stored_bytes),
        source_revisions=count("source_revision"),
        wells=count("well"),
        wellbores=count("wellbore"),
        extracted_records=int(
            session.execute(
                select(func.count())
                .select_from(m.extracted_record)
                .where(m.extracted_record.c.project_id == project_id)
            ).scalar_one()
        ),
        evidence_chunks=count("evidence_chunk"),
        processing_runs=count("processing_run"),
        reconstruction_runs=count("reconstruction_run"),
        agent_work_units=count("agent_work_unit"),
        active_jobs=_active_work_count(session, project_id),
    )


def _active_work_count(session: Session, project_id: UUID) -> int:
    total = 0
    for name in ("ingest_job", "extraction_run", "processing_run", "reconstruction_run"):
        t = m.metadata.tables[name]
        total += int(
            session.execute(
                select(func.count())
                .select_from(t)
                .where(t.c.project_id == project_id, t.c.status.in_(("queued", "running")))
            ).scalar_one()
        )
    u = m.agent_work_unit
    total += int(
        session.execute(
            select(func.count())
            .select_from(u)
            .where(u.c.project_id == project_id, u.c.state == "running")
        ).scalar_one()
    )
    return total


# -- phase 1 -------------------------------------------------------------------------------------


def request_deletion(
    session: Session, project_id: UUID, confirm_name: str
) -> ProjectDeletionStatus:
    """Validate the typed name, lock the project, mark it ``deleting`` and stop in-flight work.
    Repeating the request is idempotent (and is the retry of a ``failed`` deletion)."""
    row = session.execute(
        select(m.project.c.name, m.project.c.deletion_state)
        .where(m.project.c.project_id == project_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise _not_found()
    if confirm_name != row.name:
        raise ContractError(
            ErrorCode.VALIDATION_ERROR,
            "confirm_name must equal the project name exactly",
            422,
            {"reason": "confirm_name_mismatch"},
        )
    p = m.project
    values: dict[str, object] = {"updated_at": func.clock_timestamp()}
    if row.deletion_state != ProjectDeletionState.DELETING:
        # first request, or the retry of a failed deletion (which restarts the drain window)
        values.update(
            deletion_state=ProjectDeletionState.DELETING.value,
            deletion_error=None,
            deletion_requested_at=_now(),
        )
    updated = (
        session.execute(
            update(p).where(p.c.project_id == project_id).values(**values).returning(*_STATUS_COLS)
        )
        .mappings()
        .one()
    )
    stop_work(session, project_id)
    return ProjectDeletionStatus.model_validate(dict(updated))


_STATUS_COLS = (
    m.project.c.project_id,
    m.project.c.deletion_state,
    m.project.c.deletion_requested_at,
    m.project.c.deletion_error,
)


def stop_work(session: Session, project_id: UUID) -> None:
    """Cancel queued work and request cancellation of running work (idempotent). Running work
    finishes through its own fenced path and releases its lease; the executor waits for that."""
    now = _now()
    j = m.ingest_job
    session.execute(
        update(j)
        .where(j.c.project_id == project_id, j.c.status == "queued")
        .values(
            status="cancelled",
            cancel_requested=True,
            stage=None,
            finished_at=now,
            updated_at=now,
            error={"code": "project_deleting", "message": "the project is being deleted"},
        )
    )
    session.execute(
        update(j)
        .where(j.c.project_id == project_id, j.c.status == "running")
        .values(cancel_requested=True, updated_at=now)
    )
    for name in ("processing_run", "reconstruction_run"):
        t = m.metadata.tables[name]
        session.execute(
            update(t)
            .where(t.c.project_id == project_id, t.c.status == "queued")
            .values(
                status="cancelled",
                cancel_requested=True,
                finished_at=now,
                lease_owner=None,
                lease_expires_at=None,
            )
        )
        session.execute(
            update(t)
            .where(t.c.project_id == project_id, t.c.status == "running")
            .values(cancel_requested=True)
        )
    # Extraction has no cancel flag: superseding keeps unfinished runs from being claimed or
    # indexed; a run already executing finishes and releases its lease (the drain waits for it).
    er = m.extraction_run
    session.execute(
        update(er)
        .where(
            er.c.project_id == project_id,
            er.c.superseded.is_(False),
            er.c.status.in_(("queued", "running", "interrupted")),
        )
        .values(superseded=True)
    )
    rix = m.metadata.tables["retrieval_index"]
    session.execute(
        update(rix)
        .where(
            rix.c.project_id == project_id,
            rix.c.status.in_(("queued", "interrupted")),
        )
        .values(
            status="failed",
            error={"code": "project_deleting", "message": "the project is being deleted"},
            finished_at=now,
            lease_owner=None,
            lease_expires_at=None,
        )
    )
    u = m.agent_work_unit
    session.execute(
        update(u)
        .where(u.c.project_id == project_id, u.c.state == "running")
        .values(
            state="cancelled",
            stop_reason="project_deleting",
            stop_detail="the project is being deleted",
            finished_at=now,
            updated_at=now,
            fence_counter=u.c.fence_counter + 1,
        )
    )


# -- phase 2 -------------------------------------------------------------------------------------


def active_leases(session: Session, project_id: UUID) -> int:
    """Leases still held (unexpired) for the project by any worker."""
    now = _now()
    total = 0
    a = m.ingest_job_attempt
    total += int(
        session.execute(
            select(func.count())
            .select_from(a)
            .where(
                a.c.project_id == project_id, a.c.status == "running", a.c.lease_expires_at > now
            )
        ).scalar_one()
    )
    for name in ("extraction_run", "processing_run", "reconstruction_run", "retrieval_index"):
        t = m.metadata.tables[name]
        total += int(
            session.execute(
                select(func.count())
                .select_from(t)
                .where(
                    t.c.project_id == project_id,
                    t.c.lease_owner.is_not(None),
                    t.c.lease_expires_at > now,
                )
            ).scalar_one()
        )
    return total


def _project_tables() -> set[str]:
    return {t.name for t in m.metadata.tables.values() if "project_id" in t.c}


def uncovered_tables(extra_known: set[str] | None = None) -> set[str]:
    """Model tables with a ``project_id`` that the purge does not handle (must be empty)."""
    return _project_tables() - set(PURGE_ORDER) - {"project"} - (extra_known or set())


class StorageRootMismatch(RuntimeError):
    pass


class LeaseStillHeld(RuntimeError):
    """A worker took a lease between the drain check and the purge transaction: wait again."""


def purge_database(session: Session, project_id: UUID) -> bool:
    """The one purge transaction. Returns False when the project is already gone (a no-op)."""
    locked = session.execute(
        select(m.project.c.project_id).where(m.project.c.project_id == project_id).with_for_update()
    ).scalar_one_or_none()
    if locked is None:
        return False
    missing = uncovered_tables()
    if missing:
        raise RuntimeError(f"purge does not cover project tables: {sorted(missing)}")
    if active_leases(session, project_id):
        raise LeaseStillHeld("work still holds a lease")
    session.execute(
        text("SELECT set_config('fieldlens.purge_project_id', :pid, true)"),
        {"pid": str(project_id)},
    )
    p = m.project
    session.execute(
        update(p)
        .where(p.c.project_id == project_id)
        .values(latest_source_revision_id=None, active_model_revision_id=None)
    )
    for name in PURGE_ORDER:
        t = m.metadata.tables[name]
        session.execute(delete(t).where(t.c.project_id == project_id))
    session.execute(delete(p).where(p.c.project_id == project_id))
    return True


def delete_project_files(store: BlobStore, project_id: UUID) -> None:
    """Remove ``projects/<id>/`` (blobs and anything else under it). A missing directory is fine;
    a symlink or a path outside ``<root>/projects`` is refused."""
    base = (store.root / "projects").resolve()
    target = store.root / "projects" / str(project_id)
    if target.is_symlink():
        raise OSError("refusing to delete a symlinked project directory")
    if not target.exists():
        return
    if target.resolve().parent != base:
        raise OSError("project directory is outside the storage root")
    _rmtree(target)


def _rmtree(path: Path) -> None:
    def onerror(func: object, p: str, exc: object) -> None:
        raise OSError(f"could not delete {p}")

    shutil.rmtree(path, onerror=onerror)


class ProjectPurger:
    """Background executor: advances one ``deleting`` project per pass."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        store: BlobStore,
        settings: Settings,
        *,
        drain_timeout_s: float = DRAIN_TIMEOUT_S,
    ) -> None:
        self._factory = factory
        self._store = store
        self._settings = settings
        self._drain_timeout = drain_timeout_s
        self._guard = StorageRootGuard(factory, store, recheck_seconds=0.0)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> bool:
        """Advance the oldest ``deleting`` project. True when something was done (or finished)."""
        with session_scope(self._factory) as session:
            row = session.execute(
                select(
                    m.project.c.project_id,
                    m.project.c.deletion_requested_at,
                    m.project.c.deletion_storage_purged_at,
                )
                .where(m.project.c.deletion_state == ProjectDeletionState.DELETING)
                .order_by(m.project.c.deletion_requested_at)
                .limit(1)
            ).one_or_none()
        if row is None:
            return False
        project_id: UUID = row.project_id
        try:
            return self._advance(
                project_id, row.deletion_requested_at, row.deletion_storage_purged_at
            )
        except LeaseStillHeld:
            return False
        except StorageRootMismatch as exc:
            self._fail(project_id, str(exc))
            return True
        except Exception as exc:  # noqa: BLE001 - record, never crash the loop; retry is explicit
            logger.error("project deletion %s failed: %s", project_id, type(exc).__name__)
            self._fail(project_id, f"{type(exc).__name__}: {exc}")
            return True

    def _advance(
        self, project_id: UUID, requested_at: datetime | None, storage_purged_at: datetime | None
    ) -> bool:
        with session_scope(self._factory) as session:
            stop_work(session, project_id)  # stragglers created after phase 1
            leases = active_leases(session, project_id)
        if leases:
            waited = (_now() - (requested_at or _now())).total_seconds()
            if waited > self._drain_timeout:
                raise RuntimeError(f"work did not stop within {int(self._drain_timeout)} seconds")
            return False
        if storage_purged_at is None:
            if not self._guard.serves_database():
                raise StorageRootMismatch(
                    "this process's storage root does not hold the stored originals of this "
                    "database; nothing was deleted"
                )
            delete_project_files(self._store, project_id)
            with session_scope(self._factory) as session:
                session.execute(
                    update(m.project)
                    .where(m.project.c.project_id == project_id)
                    .values(deletion_storage_purged_at=_now())
                )
        settle_finished_units(self._factory, BudgetLedger(self._factory), project_id)
        with session_scope(self._factory) as session:
            gone = not purge_database(session, project_id)
        try:
            delete_project_files(self._store, project_id)  # blobs that raced the first pass
        except OSError:
            logger.warning("project %s directory could not be re-swept", project_id)
        if gone:
            logger.info("project %s was already deleted", project_id)
        return True

    def _fail(self, project_id: UUID, message: str) -> None:
        with session_scope(self._factory) as session:
            session.execute(
                update(m.project)
                .where(
                    m.project.c.project_id == project_id,
                    m.project.c.deletion_state == ProjectDeletionState.DELETING,
                )
                .values(
                    deletion_state=ProjectDeletionState.FAILED.value,
                    deletion_error=message[:_ERROR_MAX],
                )
            )

    # -- thread ---------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="fieldlens-purge", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                handled = self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.error("purge loop error: %s", type(exc).__name__)
                handled = False
            if not handled:
                self._stop.wait(self._settings.job_poll_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None


__all__ = [
    "PURGE_ORDER",
    "ProjectPurger",
    "assert_not_deleting",
    "deleting_error",
    "preview",
    "request_deletion",
    "stop_work",
    "uncovered_tables",
]

"""Storage-root identity: bind a database to exactly one storage root and refuse to work otherwise.

Several backend processes (the main app, lane/worktree servers, a stale old-code server) can share
one database. A process whose storage root is not the one this database's originals live in must
never claim verification/extraction/processing work or write a failure, because it would find every
original "missing". The root therefore has one persisted identity, in two places:

* the single row of ``storage_root_identity`` (database), and
* ``<root>/.fieldlens-root-id`` (storage root).

The guard compares them before any blob-reading worker claims work, before it writes a failure and
before the API accepts uploads or re-verifies originals. A mismatch is reported as
``storage_root_mismatch`` in readiness. ``adopt`` (``scripts/storage_root.py``) is the explicit,
confirmed way to re-bind an intentionally wiped or moved root.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.evidence.storage import BlobStore, VerifyOutcome
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

logger = logging.getLogger(__name__)

MARKER_NAME = ".fieldlens-root-id"
MISMATCH = "storage_root_mismatch"
SAMPLE_SIZE = 8
RECHECK_SECONDS = 5.0
LOG_EVERY_SECONDS = 60.0


@dataclass(frozen=True)
class RootStatus:
    ok: bool
    root_id: UUID | None = None
    reason: str | None = None  # why the root is refused; None when ok


def marker_path(root: Path) -> Path:
    return root / MARKER_NAME


def read_marker(root: Path) -> str | None:
    """The marker text, or None when the file does not exist."""
    try:
        return marker_path(root).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None


def write_marker(root: Path, root_id: UUID, *, replace: bool) -> bool:
    """Create the marker (never overwriting unless ``replace``). Returns False when it exists."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = marker_path(root)
    data = f"{root_id}\n".encode()
    if replace:
        tmp = target.with_name(f"{MARKER_NAME}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        return True
    try:
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except FileExistsError:
        return False
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    return True


def _has_blobs(root: Path) -> bool:
    base = root / "projects"
    if not base.is_dir():
        return False
    return any(p.is_file() for p in base.rglob("*"))


def _db_identity(session: Session) -> str | None:
    value = session.execute(select(m.storage_root_identity.c.root_id)).scalar_one_or_none()
    return None if value is None else str(value)


def _stored_samples(session: Session) -> list[tuple[str, str, int]]:
    """Recent originals (stored or failed) as (key, sha256, size). Failed ones count: their
    bytes are exactly what the heal pass verifies, and a database whose files were all marked
    failed by a stale server has no stored document left to sample."""
    rows = session.execute(
        select(
            m.source_document.c.storage_key,
            m.source_document.c.sha256,
            m.source_document.c.size_bytes,
        )
        .join(
            m.document_processing,
            m.document_processing.c.document_id == m.source_document.c.document_id,
        )
        .where(m.document_processing.c.storage_state.in_(("stored", "failed")))
        .order_by(m.source_document.c.created_at.desc())
        .limit(SAMPLE_SIZE)
    ).all()
    return [(str(r[0]), str(r[1]), int(r[2])) for r in rows]


def _readable_sample(store: BlobStore, samples: list[tuple[str, str, int]]) -> bool:
    """True only when a sampled original verifies (size and SHA-256) under this root."""
    for key, sha, size in samples:
        try:
            if store.verify(key, sha, size).outcome is VerifyOutcome.OK:
                return True
        except (ValueError, OSError):
            continue
    return False


def _bind(session: Session, root_id: UUID) -> str | None:
    """Insert the identity row unless one exists; returns the id the row now holds."""
    session.execute(
        pg_insert(m.storage_root_identity)
        .values(singleton=True, root_id=root_id)
        .on_conflict_do_nothing()
    )
    return _db_identity(session)


def evaluate(factory: sessionmaker[Session], store: BlobStore) -> RootStatus:
    """Compare the marker file with the database row, binding a fresh or legacy root.

    * row + marker equal -> ok; different -> mismatch; row but no marker -> mismatch.
    * no row: bind only when this database has no stored originals yet (fresh install and an
      empty root), or - for databases created before this identity existed - when a recently
      stored original is readable under this root (one-time legacy binding). An empty root
      against a database that holds originals is a mismatch, never a fresh install.
    """
    root = store.root
    marker = read_marker(root)
    with session_scope(factory) as session:
        row = _db_identity(session)
        if row is not None:
            if marker is None:
                return RootStatus(False, UUID(row), "root marker file is missing")
            if marker != row:
                return RootStatus(False, UUID(row), "root marker differs from this database")
            return RootStatus(True, UUID(row))
        has_docs = session.execute(select(m.source_document.c.document_id).limit(1)).first()
        samples = _stored_samples(session) if has_docs else []
        legacy = bool(samples) and _readable_sample(store, samples)
        if has_docs and not legacy:
            return RootStatus(False, None, "root holds none of this database's originals")
        if marker is None:
            if not has_docs and _has_blobs(root):
                return RootStatus(False, None, "root has files but no marker; database is new")
            candidate = uuid4()
        else:
            try:
                candidate = UUID(marker)
            except ValueError:
                return RootStatus(False, None, "root marker file is not valid")
        bound = _bind(session, candidate)
    if bound != str(candidate):
        return RootStatus(
            False, UUID(bound) if bound else None, "database is bound to another root"
        )
    if marker is None and not write_marker(root, candidate, replace=False):
        if read_marker(root) != str(candidate):
            return RootStatus(False, candidate, "root marker was created by another process")
    return RootStatus(True, candidate)


def adopt(factory: sessionmaker[Session], store: BlobStore) -> UUID:
    """Explicitly bind this database and this root to one identity (reusing a valid marker)."""
    existing = read_marker(store.root)
    try:
        root_id = UUID(existing) if existing else uuid4()
    except ValueError:
        root_id = uuid4()
    write_marker(store.root, root_id, replace=True)
    with session_scope(factory) as session:
        if _db_identity(session) is None:
            session.execute(
                insert(m.storage_root_identity).values(
                    singleton=True, root_id=root_id, adopted_at=func.now()
                )
            )
        else:
            session.execute(
                update(m.storage_root_identity).values(root_id=root_id, adopted_at=func.now())
            )
    return root_id


_log_lock = threading.Lock()
_last_logged = float("-inf")


def _may_log(now: float) -> bool:
    """At most one mismatch log per LOG_EVERY_SECONDS for the whole process (every component
    owns a guard, so a per-guard throttle would repeat the line)."""
    global _last_logged
    with _log_lock:
        if now - _last_logged < LOG_EVERY_SECONDS:
            return False
        _last_logged = now
        return True


class StorageRootGuard:
    """``serves_database()`` is True only when this process's root has the database's identity."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        store: BlobStore,
        recheck_seconds: float = RECHECK_SECONDS,
        lane: str = "main",
    ) -> None:
        self._factory = factory
        self._store = store
        self._recheck = recheck_seconds
        self.lane = lane
        self._checked_at = float("-inf")
        self._status = RootStatus(True)

    @property
    def store(self) -> BlobStore:
        return self._store

    @property
    def status(self) -> RootStatus:
        return self._status

    def serves_database(self, *, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self._checked_at < self._recheck:
            return self._status.ok
        self._status = evaluate(self._factory, self._store)
        self._checked_at = now
        if not self._status.ok and _may_log(now):
            logger.error(
                "%s: storage root %s is not this database's root (%s); this process will not "
                "claim, verify or fail any stored file (run `uv run python scripts/storage_root.py "
                "adopt` if the root was intentionally moved or wiped)",
                MISMATCH,
                self._store.root,
                self._status.reason,
            )
        return self._status.ok

    def identity(self) -> str:
        """Who is writing: host, pid, lane and root id (stored on failures for attribution)."""
        root = self._status.root_id
        return (
            f"host={socket.gethostname()} pid={os.getpid()} lane={self.lane} "
            f"root={root if root else 'unbound'}"
        )

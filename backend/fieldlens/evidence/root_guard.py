"""Detect a worker whose storage root is not the one this database's originals live in.

Several backend processes (for example the main app and a lane/worktree started with another
``FIELDLENS_STORAGE_ROOT``) can share one database. Every process runs job and extraction
workers, so a process with the wrong root would claim verification/extraction work, find every
original "missing" and flag healthy documents (``source_missing`` / ``verification_missing``)
although the API process that wrote them can read them. Before claiming work, a worker therefore
checks that at least one recently stored original of the database is readable under its root.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.evidence.storage import BlobStore
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

logger = logging.getLogger(__name__)

SAMPLE_SIZE = 8
RECHECK_SECONDS = 5.0
LOG_EVERY_SECONDS = 60.0


class StorageRootGuard:
    """``serves_database()`` is False only when stored originals exist in the database and none
    of the sampled ones is readable under this process's storage root."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        store: BlobStore,
        recheck_seconds: float = RECHECK_SECONDS,
    ) -> None:
        self._factory = factory
        self._store = store
        self._recheck = recheck_seconds
        self._checked_at = float("-inf")
        self._ok = True
        self._logged_at = float("-inf")

    def serves_database(self) -> bool:
        now = time.monotonic()
        if now - self._checked_at < self._recheck:
            return self._ok
        self._ok = self._probe()
        self._checked_at = now
        if not self._ok and now - self._logged_at >= LOG_EVERY_SECONDS:
            self._logged_at = now
            logger.error(
                "storage root %s holds none of the stored originals of this database; "
                "this process will not claim verification or extraction work "
                "(another process with the right FIELDLENS_STORAGE_ROOT must run it)",
                self._store.root,
            )
        return self._ok

    def _probe(self) -> bool:
        with session_scope(self._factory) as session:
            keys = (
                session.execute(
                    select(m.source_document.c.storage_key)
                    .join(
                        m.document_processing,
                        m.document_processing.c.document_id == m.source_document.c.document_id,
                    )
                    .where(m.document_processing.c.storage_state == "stored")
                    .order_by(m.source_document.c.created_at.desc())
                    .limit(SAMPLE_SIZE)
                )
                .scalars()
                .all()
            )
        if not keys:
            return True  # nothing to compare against yet
        for key in keys:
            try:
                if self._store.path_for(key).is_file():
                    return True
            except ValueError:
                continue
        return False

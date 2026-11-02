"""Startup heal pass: restore Failed documents whose stored bytes verify, queue extraction.

A document is Failed only when bytes are genuinely missing or damaged under the right storage
root. Files written Failed by an old-code process with the wrong root (the 2026-11-02 incident) have
intact bytes; this pass re-verifies them and restores them. Bounded per pass, idempotent (state
changes only after a hash-verified blob exists), skipped entirely while the root identity does not
match.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.evidence.integrity import restore_stored
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.evidence.storage import BlobStore, VerifyOutcome
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .runner import enqueue_missing, requeue_document

logger = logging.getLogger(__name__)

HEAL_LIMIT = 200
_STORAGE_RUN_CODES = ("source_missing", "content_hash_mismatch")


@dataclass(frozen=True)
class HealResult:
    ran: bool
    checked: int = 0
    restored: int = 0
    still_failed: int = 0
    queued: int = 0


def queue_extraction_after_restore(session: Session, project_id: UUID, document_id: UUID) -> bool:
    """Queue a run for a restored document when it has none, or its run failed because the
    original could not be read. Any other outcome (a parse result) is left alone."""
    run = session.execute(
        select(m.extraction_run.c.status, m.extraction_run.c.error).where(
            m.extraction_run.c.document_id == document_id,
            m.extraction_run.c.superseded.is_(False),
        )
    ).first()
    if run is not None:
        code = (run.error or {}).get("code")
        if not (run.status == "failed" and code in _STORAGE_RUN_CODES):
            return False
    queued = requeue_document(session, project_id, document_id, retry=True)
    if queued:
        mark_extraction_pending(session, document_id)
    return queued


def mark_extraction_pending(session: Session, document_id: UUID) -> None:
    session.execute(
        update(m.document_processing)
        .where(
            m.document_processing.c.document_id == document_id,
            m.document_processing.c.extraction_state == "extraction_failed",
        )
        .values(extraction_state="pending_extraction", detail=None, updated_at=func.now())
    )


def heal_pass(
    factory: sessionmaker[Session],
    store: BlobStore,
    guard: StorageRootGuard,
    limit: int = HEAL_LIMIT,
) -> HealResult:
    if not guard.serves_database(force=True):
        return HealResult(ran=False)
    dp, sd = m.document_processing, m.source_document
    with session_scope(factory) as session:
        rows = session.execute(
            select(
                sd.c.project_id, sd.c.document_id, sd.c.storage_key, sd.c.sha256, sd.c.size_bytes
            )
            .join(dp, dp.c.document_id == sd.c.document_id)
            .where(dp.c.storage_state == "failed")
            .order_by(dp.c.updated_at, sd.c.document_id)
            .limit(limit)
        ).all()
    restored = still_failed = queued = 0
    for row in rows:
        result = store.verify(row.storage_key, row.sha256, row.size_bytes)
        if result.outcome is not VerifyOutcome.OK:
            still_failed += 1
            continue
        with session_scope(factory) as session:
            if restore_stored(session, row.document_id):
                restored += 1
                if queue_extraction_after_restore(session, row.project_id, row.document_id):
                    queued += 1
    with session_scope(factory) as session:
        queued += enqueue_missing(session)
    if rows or queued:
        logger.info(
            "storage heal: checked=%d restored=%d still_failed=%d extraction_queued=%d",
            len(rows),
            restored,
            still_failed,
            queued,
        )
    return HealResult(True, len(rows), restored, still_failed, queued)

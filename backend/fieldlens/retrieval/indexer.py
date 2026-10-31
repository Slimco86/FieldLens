"""Index job runner: chunks and embeddings are derived data built by one leased job at a time.

``retrieval_index`` rows are the persistent jobs (``queued -> running -> complete | failed |
interrupted``). Chunk text is written inside ONE transaction that also flips the index to
``complete`` (fenced on lease owner and on the extraction run still being current), so an
interrupted or superseded attempt leaves nothing visible. Embedding jobs insert vectors in
fenced batches of 16 and only report ``complete`` once every chunk has a vector at the active
fingerprint; interrupted work is resumable and never looks complete. Everything runs on the job
worker thread, never on the request loop. Stale derived data (superseded runs, other chunker
versions, other embedding fingerprints) is deleted, never reused."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import case, delete, func, insert, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from . import tables as t
from .chunker import CHUNKER_VERSION, ChunkDraft, RecordIn, chunk_records
from .embedder import BATCH_SIZE, EmbedderProvider, EmbedderUnavailable

logger = logging.getLogger(__name__)
rix = t.retrieval_index
ec = t.evidence_chunk
ADVISORY_LOCK = 0x464C0011
INSERT_BATCH = 200
CLEANUP_INTERVAL_S = 15.0  # stale-data deletion sweep; job discovery runs every poll
_RETRYABLE_EMBEDDER_CODES = ("embedder_unavailable", "model_missing", "model_load_failed")


class FenceLost(Exception):
    """The index job is no longer owned by this attempt."""


class RunGone(Exception):
    """The extraction run (or chunk index) this job derives from is no longer current; the job
    row is deleted instead of lingering ``running`` until its lease lapses."""


@dataclass(frozen=True)
class IndexClaim:
    index_id: UUID
    project_id: UUID
    run_id: UUID
    document_id: UUID
    kind: str
    embedding_fingerprint: str | None
    attempt_no: int
    owner: str


def chunk_id_for(run_id: UUID, ordinal: int) -> UUID:
    return uuid5(run_id, f"{CHUNKER_VERSION}:{ordinal}")


def coverage_status(raw: dict[str, Any] | None) -> str:
    if not raw:
        return "unknown"
    total, inspected = raw.get("total"), raw.get("inspected")
    if total is not None and inspected == total and not raw.get("reasons"):
        return "complete"
    return "partial" if total is not None else "unknown"


# --- sweeps -------------------------------------------------------------------------------


def enqueue_missing(session: Session, provider: EmbedderProvider, *, cleanup: bool = True) -> int:
    """Queue chunk jobs for current runs, embedding jobs for the active fingerprint and delete
    derived data that can no longer be eligible. Returns the number of jobs queued."""
    er = m.extraction_run
    queued = 0
    if cleanup:
        # Stale derived data: superseded runs and any other chunker version (cascades to chunks).
        session.execute(
            delete(rix).where(
                (rix.c.chunker_version != CHUNKER_VERSION)
                | rix.c.run_id.in_(select(er.c.run_id).where(er.c.superseded.is_(True)))
            )
        )
    current_runs = (
        select(er.c.run_id, er.c.project_id, er.c.document_id, er.c.source_revision_id)
        .join(
            m.document_processing,
            m.document_processing.c.document_id == er.c.document_id,
        )
        .where(
            er.c.superseded.is_(False),
            er.c.status.in_(("succeeded", "partial")),
            m.document_processing.c.storage_state == "stored",
            ~select(rix.c.index_id)
            .where(
                rix.c.run_id == er.c.run_id,
                rix.c.kind == "chunks",
                rix.c.chunker_version == CHUNKER_VERSION,
            )
            .exists(),
        )
        .limit(50)
    )
    for row in session.execute(current_runs).all():
        session.execute(
            insert(rix).values(
                project_id=row.project_id,
                run_id=row.run_id,
                document_id=row.document_id,
                source_revision_id=row.source_revision_id,
                kind="chunks",
                chunker_version=CHUNKER_VERSION,
            )
        )
        queued += 1

    status = provider.status()
    if status.spec is None:
        return queued
    spec = status.spec
    fingerprint = spec.fingerprint
    if cleanup:
        # Vectors of any other fingerprint can never be used by a query: remove them.
        session.execute(
            delete(rix).where(
                rix.c.kind == "embeddings", rix.c.embedding_fingerprint != fingerprint
            )
        )
        session.execute(
            delete(t.chunk_embedding).where(
                t.chunk_embedding.c.embedding_fingerprint != fingerprint
            )
        )
    # A job that failed only because the embedder was unavailable is retried once it is back.
    session.execute(
        update(rix)
        .where(
            rix.c.kind == "embeddings",
            rix.c.status == "failed",
            rix.c.error["code"].astext.in_(_RETRYABLE_EMBEDDER_CODES),
        )
        .values(status="queued", attempt_no=0, error=None, finished_at=None)
    )
    chunk_idx = rix.alias("c")
    ready = (
        select(
            chunk_idx.c.project_id,
            chunk_idx.c.run_id,
            chunk_idx.c.document_id,
            chunk_idx.c.source_revision_id,
            chunk_idx.c.chunk_count,
        )
        .where(
            chunk_idx.c.kind == "chunks",
            chunk_idx.c.status == "complete",
            chunk_idx.c.chunker_version == CHUNKER_VERSION,
            ~select(rix.c.index_id)
            .where(
                rix.c.run_id == chunk_idx.c.run_id,
                rix.c.kind == "embeddings",
                rix.c.chunker_version == CHUNKER_VERSION,
                rix.c.embedding_fingerprint == fingerprint,
            )
            .exists(),
        )
        .limit(50)
    )
    for ready_row in session.execute(ready).all():
        session.execute(
            insert(rix).values(
                project_id=ready_row.project_id,
                run_id=ready_row.run_id,
                document_id=ready_row.document_id,
                source_revision_id=ready_row.source_revision_id,
                kind="embeddings",
                chunker_version=CHUNKER_VERSION,
                embedding_fingerprint=fingerprint,
                embedding_spec=spec.public(),
                chunk_count=ready_row.chunk_count,
            )
        )
        queued += 1
    return queued


# --- runner -------------------------------------------------------------------------------


class IndexRunner:
    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: Settings,
        owner: str,
        is_dead_owner: Any,
        provider: EmbedderProvider,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self.owner = owner
        self._is_dead_owner = is_dead_owner
        self.provider = provider
        self._last_cleanup = float("-inf")
        self.cleanup_interval_s = CLEANUP_INTERVAL_S

    def recover_once(self) -> int:
        count = 0
        with session_scope(self._factory) as session:
            rows = session.execute(
                select(rix.c.index_id, rix.c.lease_owner, rix.c.lease_expires_at, rix.c.attempt_no)
                .where(rix.c.status == "running")
                .with_for_update(skip_locked=True)
            ).all()
            now = session.execute(select(func.clock_timestamp())).scalar_one()
            for row in rows:
                lapsed = row.lease_expires_at is None or row.lease_expires_at < now
                dead = row.lease_owner is not None and self._is_dead_owner(row.lease_owner)
                if not (lapsed or dead):
                    continue
                exhausted = row.attempt_no >= self._settings.retrieval_max_attempts
                session.execute(
                    update(rix)
                    .where(rix.c.index_id == row.index_id)
                    .values(
                        status="failed" if exhausted else "interrupted",
                        lease_owner=None,
                        lease_expires_at=None,
                        finished_at=now if exhausted else None,
                        error={"code": "interrupted_too_often", "message": "attempts exhausted"}
                        if exhausted
                        else {"code": "interrupted", "message": "worker stopped mid-index"},
                    )
                )
                count += 1
        return count

    def run_once(self) -> bool:
        self.recover_once()
        now = time.monotonic()
        sweep = now - self._last_cleanup >= self.cleanup_interval_s
        if sweep:
            self._last_cleanup = now
        with session_scope(self._factory) as session:
            enqueue_missing(session, self.provider, cleanup=sweep)
        claim = self._claim()
        if claim is None:
            return False
        self._process(claim)
        return True

    def _claim(self) -> IndexClaim | None:
        with session_scope(self._factory) as session:
            session.execute(select(func.pg_advisory_xact_lock(ADVISORY_LOCK)))
            if session.execute(select(rix.c.index_id).where(rix.c.status == "running")).first():
                return None
            row = session.execute(
                select(rix)
                .where(
                    rix.c.status.in_(("queued", "interrupted")),
                    rix.c.attempt_no < self._settings.retrieval_max_attempts,
                )
                .order_by(
                    case((rix.c.kind == "chunks", 0), else_=1), rix.c.queued_at, rix.c.index_id
                )
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return None
            lease = text("clock_timestamp() + make_interval(secs => :s)").bindparams(
                s=self._settings.job_lease_seconds
            )
            session.execute(
                update(rix)
                .where(rix.c.index_id == row.index_id)
                .values(
                    status="running",
                    attempt_no=row.attempt_no + 1,
                    lease_owner=self.owner,
                    lease_expires_at=lease,
                    started_at=func.clock_timestamp(),
                    error=None,
                )
            )
            return IndexClaim(
                row.index_id,
                row.project_id,
                row.run_id,
                row.document_id,
                row.kind,
                row.embedding_fingerprint,
                row.attempt_no + 1,
                self.owner,
            )

    def _heartbeat(self, claim: IndexClaim) -> bool:
        with session_scope(self._factory) as session:
            lease = text("clock_timestamp() + make_interval(secs => :s)").bindparams(
                s=self._settings.job_lease_seconds
            )
            result = session.execute(
                update(rix)
                .where(
                    rix.c.index_id == claim.index_id,
                    rix.c.status == "running",
                    rix.c.lease_owner == claim.owner,
                )
                .values(lease_expires_at=lease)
            )
            return bool(getattr(result, "rowcount", 0) == 1)

    def _process(self, claim: IndexClaim) -> None:
        done = threading.Event()
        lost = threading.Event()

        def beat() -> None:
            while not done.wait(self._settings.job_heartbeat_seconds):
                try:
                    if not self._heartbeat(claim):
                        lost.set()
                        return
                except Exception:
                    logger.warning("index heartbeat failed for %s", claim.index_id)

        beater = threading.Thread(target=beat, daemon=True, name=f"index-hb-{claim.index_id}")
        beater.start()
        try:
            if claim.kind == "chunks":
                self._build_chunks(claim, lost)
            else:
                self._build_embeddings(claim, lost)
        except FenceLost:
            logger.warning("index job %s lost its fence", claim.index_id)
        except RunGone:
            with session_scope(self._factory) as session:
                session.execute(
                    delete(rix).where(
                        rix.c.index_id == claim.index_id, rix.c.lease_owner == claim.owner
                    )
                )
        except EmbedderUnavailable as exc:
            self._finalize_failed(claim, exc.code, exc.message)
        except Exception as exc:
            logger.error("index job %s crashed: %s", claim.index_id, type(exc).__name__)
            self._finalize_failed(claim, "index_error", type(exc).__name__)
        finally:
            done.set()
            beater.join(timeout=5)

    # -- finalization -----------------------------------------------------------------------
    def _fenced(self, session: Session, claim: IndexClaim, **values: Any) -> None:
        result = session.execute(
            update(rix)
            .where(
                rix.c.index_id == claim.index_id,
                rix.c.status == "running",
                rix.c.lease_owner == claim.owner,
            )
            .values(**values)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise FenceLost("not the owner")

    def _finalize_failed(self, claim: IndexClaim, code: str, message: str) -> None:
        try:
            with session_scope(self._factory) as session:
                self._fenced(
                    session,
                    claim,
                    status="failed",
                    lease_owner=None,
                    lease_expires_at=None,
                    finished_at=func.now(),
                    error={"code": code, "message": message[:300]},
                )
        except FenceLost:
            pass

    # -- chunks -----------------------------------------------------------------------------
    def _build_chunks(self, claim: IndexClaim, lost: threading.Event) -> None:
        er = m.extraction_run
        with session_scope(self._factory) as session:
            run = session.execute(select(er).where(er.c.run_id == claim.run_id)).first()
        if run is None or run.superseded or run.status not in ("succeeded", "partial"):
            raise RunGone("run is no longer current")
        quality_base = {
            "run_status": run.status,
            "coverage_status": coverage_status(run.coverage),
            "profile_name": run.profile_name,
            "profile_version": run.profile_version,
            "method": run.method,
        }
        cap = self._settings.retrieval_max_chunks_per_document
        er_rec = m.extracted_record
        truncated = False
        last_ordinal = -1
        with session_scope(self._factory) as write:
            write.execute(delete(ec).where(ec.c.index_id == claim.index_id))
            reader = self._factory()
            try:
                stream = reader.execute(
                    select(
                        er_rec.c.ordinal,
                        er_rec.c.record_id,
                        er_rec.c.kind,
                        er_rec.c.subject,
                        er_rec.c.locator,
                        er_rec.c.effective_time,
                        er_rec.c.validation_state,
                        er_rec.c.attributes,
                    )
                    .where(er_rec.c.run_id == claim.run_id)
                    .order_by(er_rec.c.ordinal)
                    .execution_options(yield_per=500)
                )
                records = (
                    RecordIn(
                        r.ordinal,
                        r.record_id,
                        r.kind,
                        r.subject,
                        r.locator,
                        r.effective_time,
                        r.validation_state,
                        r.attributes,
                    )
                    for r in stream
                )
                pending: list[ChunkDraft] = []
                count = 0
                for draft in chunk_records(records, run.content_sha256):
                    if lost.is_set():
                        raise FenceLost("lease lost")
                    if count >= cap:
                        truncated = True
                        break
                    pending.append(draft)
                    count += 1
                    last_ordinal = draft.last_record_ordinal
                    if len(pending) >= INSERT_BATCH:
                        self._insert_chunks(write, claim, run, quality_base, pending)
                        pending = []
                if pending:
                    self._insert_chunks(write, claim, run, quality_base, pending)
            finally:
                reader.close()
            current = write.execute(
                select(er.c.run_id).where(
                    er.c.run_id == claim.run_id,
                    er.c.superseded.is_(False),
                    er.c.content_sha256 == run.content_sha256,
                )
            ).first()
            if current is None:
                raise RunGone("run superseded while indexing")
            self._fenced(
                write,
                claim,
                status="complete",
                chunk_count=count,
                truncated=truncated,
                detail={"last_record_ordinal": last_ordinal, "chunk_cap": cap},
                lease_owner=None,
                lease_expires_at=None,
                finished_at=func.now(),
                error=None,
            )

    def _insert_chunks(
        self,
        session: Session,
        claim: IndexClaim,
        run: Any,
        quality_base: dict[str, Any],
        drafts: list[ChunkDraft],
    ) -> None:
        chunk_rows: list[dict[str, Any]] = []
        id_rows: list[dict[str, Any]] = []
        for d in drafts:
            cid = chunk_id_for(claim.run_id, d.ordinal)
            chunk_rows.append(
                {
                    "chunk_id": cid,
                    "project_id": claim.project_id,
                    "index_id": claim.index_id,
                    "run_id": claim.run_id,
                    "document_id": claim.document_id,
                    "source_revision_id": run.source_revision_id,
                    "chunker_version": CHUNKER_VERSION,
                    "ordinal": d.ordinal,
                    "kind": d.kind,
                    "chunk_fingerprint": d.fingerprint,
                    "text": d.text,
                    "search_text": d.search_text,
                    "token_count": d.token_count,
                    "record_ids": d.record_ids,
                    "first_record_ordinal": d.first_record_ordinal,
                    "last_record_ordinal": d.last_record_ordinal,
                    "locators": d.locators,
                    "temporal_coverage": d.temporal_coverage,
                    "extraction_quality": {
                        **quality_base,
                        "validation_states": d.validation_states,
                    },
                }
            )
            id_rows.extend(
                {
                    "chunk_id": cid,
                    "project_id": claim.project_id,
                    "identifier": i.identifier,
                    "canonical": i.canonical,
                    "id_kind": i.id_kind,
                }
                for i in d.identifiers
            )
        session.execute(insert(ec), chunk_rows)
        if id_rows:
            session.execute(insert(t.chunk_identifier), id_rows)

    # -- embeddings -------------------------------------------------------------------------
    def _build_embeddings(self, claim: IndexClaim, lost: threading.Event) -> None:
        embedder = self.provider.get()
        if embedder.spec.fingerprint != claim.embedding_fingerprint:
            raise EmbedderUnavailable("fingerprint_changed", "embedding fingerprint changed")
        with session_scope(self._factory) as session:
            chunks_index = session.execute(
                select(rix.c.index_id, rix.c.chunk_count).where(
                    rix.c.run_id == claim.run_id,
                    rix.c.kind == "chunks",
                    rix.c.chunker_version == CHUNKER_VERSION,
                    rix.c.status == "complete",
                )
            ).first()
        if chunks_index is None:
            raise RunGone("chunk index is not complete")
        fingerprint = embedder.spec.fingerprint
        emb = t.chunk_embedding
        cap = self._settings.retrieval_max_embedded_chunks_per_document
        expected = min(chunks_index.chunk_count, cap)
        capped = chunks_index.chunk_count > cap
        while True:
            if lost.is_set():
                raise FenceLost("lease lost")
            with session_scope(self._factory) as session:
                batch = session.execute(
                    select(ec.c.chunk_id, ec.c.text, ec.c.chunk_fingerprint)
                    .where(
                        ec.c.index_id == chunks_index.index_id,
                        ec.c.ordinal < cap,
                        ~select(emb.c.chunk_id)
                        .where(
                            emb.c.chunk_id == ec.c.chunk_id,
                            emb.c.embedding_fingerprint == fingerprint,
                        )
                        .exists(),
                    )
                    .order_by(ec.c.ordinal)
                    .limit(BATCH_SIZE)
                ).all()
            if not batch:
                break
            vectors = self.provider.embed_documents([b.text for b in batch])
            if len(vectors) != len(batch) or any(
                len(v) != embedder.spec.dimension for v in vectors
            ):
                raise EmbedderUnavailable("embedding_failed", "embedder returned malformed output")
            with session_scope(self._factory) as session:
                self._fenced(session, claim, embedded_count=rix.c.embedded_count + len(batch))
                session.execute(
                    text(
                        "INSERT INTO chunk_embedding (chunk_id, embedding_fingerprint, project_id, "
                        "chunk_fingerprint, dimension, embedding) VALUES (:chunk_id, :fp, :pid, "
                        ":cfp, :dim, CAST(:vec AS vector)) ON CONFLICT DO NOTHING"
                    ),
                    [
                        {
                            "chunk_id": b.chunk_id,
                            "fp": fingerprint,
                            "pid": claim.project_id,
                            "cfp": b.chunk_fingerprint,
                            "dim": embedder.spec.dimension,
                            "vec": vector_literal(v),
                        }
                        for b, v in zip(batch, vectors, strict=True)
                    ],
                )
        with session_scope(self._factory) as session:
            total = session.execute(
                select(func.count())
                .select_from(emb.join(ec, ec.c.chunk_id == emb.c.chunk_id))
                .where(
                    ec.c.index_id == chunks_index.index_id,
                    ec.c.ordinal < cap,
                    emb.c.embedding_fingerprint == fingerprint,
                )
            ).scalar_one()
            if total != expected:
                raise EmbedderUnavailable(
                    "embedding_failed", "vector count differs from expected chunk count"
                )
            self._fenced(
                session,
                claim,
                status="complete",
                embedded_count=total,
                chunk_count=chunks_index.chunk_count,
                truncated=capped,
                detail={"embedding_cap": cap},
                lease_owner=None,
                lease_expires_at=None,
                finished_at=func.now(),
                error=None,
            )


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in vector) + "]"


def invalidate_document_chunks(
    session: Session,
    project_id: UUID,
    document_id: UUID,
    reason: str,
    *,
    source_revision_id: UUID | None = None,
) -> int:
    """Hide a document's chunks from every search at once (source removal/inactivation hook).

    Scoped by project and document, optionally by the revision the extraction was made for.
    The rows stay for audit; retrieval eligibility requires ``invalidated_at IS NULL``. Returns
    the number of chunks invalidated."""
    condition = [
        ec.c.project_id == project_id,
        ec.c.document_id == document_id,
        ec.c.invalidated_at.is_(None),
    ]
    if source_revision_id is not None:
        condition.append(ec.c.source_revision_id == source_revision_id)
    result = session.execute(
        update(ec)
        .where(*condition)
        .values(invalidated_at=func.now(), invalidated_reason=reason[:64])
    )
    return int(getattr(result, "rowcount", 0))


def drop_document_index(session: Session, project_id: UUID, document_id: UUID) -> int:
    """Delete a document's derived index (chunks, identifiers and vectors cascade). A current
    extraction run is re-indexed by the next sweep; use it to rebuild, not to hide."""
    result = session.execute(
        delete(rix).where(rix.c.project_id == project_id, rix.c.document_id == document_id)
    )
    return int(getattr(result, "rowcount", 0))

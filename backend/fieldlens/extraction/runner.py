"""Extraction runner: one leased run at a time on the job-worker thread (never the event loop).

Lifecycle of ``extraction_run``: ``queued -> running -> succeeded | partial | failed |
unsupported``. A run whose owner died or whose lease lapsed becomes ``interrupted`` and is
retried (bounded by ``extraction_max_attempts``, then ``failed``); it is never reported as
successful. Every write after claim is fenced on ``status='running'`` and the lease owner, so
a stale attempt cannot publish. Re-running is idempotent: records of a run are replaced inside
the same transaction that finalizes it, finding ids are ``uuid5(run_id, producer_key)`` and a
profile version bump supersedes the stale run and queues a new one."""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.evidence.storage import BlobStore
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope
from fieldlens.profiles import registry
from fieldlens.profiles.types import (
    EXTRACTION_FAILED,
    UNSUPPORTED_FORMAT,
    ParseContext,
    ProfileError,
    ProfileOutput,
)

logger = logging.getLogger(__name__)
CHUNK = 500
_TERMINAL = ("succeeded", "partial", "failed", "unsupported")


class FenceLost(Exception):
    """The run is no longer owned by this attempt."""


@dataclass(frozen=True)
class RunClaim:
    run_id: UUID
    project_id: UUID
    document_id: UUID
    source_revision_id: UUID
    attempt_no: int
    owner: str


def issue_id(run_id: UUID, producer_key: str) -> UUID:
    return uuid5(run_id, producer_key)


def sha256_file(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


# --- sweeps ---------------------------------------------------------------------------------


def enqueue_missing(session: Session) -> int:
    """Queue a run for every stored document without a current run; supersede stale versions."""
    created = 0
    stale = session.execute(
        select(
            m.extraction_run.c.run_id,
            m.extraction_run.c.profile_name,
            m.extraction_run.c.profile_version,
        ).where(
            m.extraction_run.c.superseded.is_(False),
            m.extraction_run.c.status.in_(_TERMINAL),
            m.extraction_run.c.profile_name.is_not(None),
        )
    ).all()
    for row in stale:
        current = registry.current_version(row.profile_name)
        if current is not None and current != row.profile_version:
            session.execute(
                update(m.extraction_run)
                .where(m.extraction_run.c.run_id == row.run_id)
                .values(superseded=True)
            )
    srd = m.source_revision_document
    docs = session.execute(
        select(
            m.document_processing.c.project_id,
            m.document_processing.c.document_id,
            m.source_document.c.sha256,
        )
        .join(
            m.source_document,
            m.source_document.c.document_id == m.document_processing.c.document_id,
        )
        .where(
            m.document_processing.c.storage_state == "stored",
            ~select(m.extraction_run.c.run_id)
            .where(
                m.extraction_run.c.document_id == m.document_processing.c.document_id,
                m.extraction_run.c.superseded.is_(False),
            )
            .exists(),
        )
        .limit(50)
    ).all()
    for doc in docs:
        revision = session.execute(
            select(srd.c.source_revision_id)
            .join(
                m.source_revision,
                m.source_revision.c.source_revision_id == srd.c.source_revision_id,
            )
            .where(srd.c.document_id == doc.document_id)
            .order_by(m.source_revision.c.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if revision is None:
            continue
        session.execute(
            insert(m.extraction_run).values(
                project_id=doc.project_id,
                document_id=doc.document_id,
                source_revision_id=revision,
                content_sha256=doc.sha256,
                status="queued",
            )
        )
        created += 1
    return created


def requeue_document(session: Session, project_id: UUID, document_id: UUID) -> bool:
    """Re-queue a stale/failed/interrupted/unsupported run (idempotent: a healthy current run is
    left alone). Returns True when a new run was queued."""
    run = session.execute(
        select(m.extraction_run)
        .where(
            m.extraction_run.c.project_id == project_id,
            m.extraction_run.c.document_id == document_id,
            m.extraction_run.c.superseded.is_(False),
        )
        .with_for_update()
    ).first()
    if run is not None:
        current = registry.current_version(run.profile_name) if run.profile_name else None
        stale = current is not None and current != run.profile_version
        if run.status in ("queued", "running") or (
            run.status in ("succeeded", "partial") and not stale
        ):
            return False
        session.execute(
            update(m.extraction_run)
            .where(m.extraction_run.c.run_id == run.run_id)
            .values(superseded=True)
        )
        revision = run.source_revision_id
        sha = run.content_sha256
    else:
        row = session.execute(
            select(m.source_document.c.sha256).where(
                m.source_document.c.project_id == project_id,
                m.source_document.c.document_id == document_id,
            )
        ).first()
        rev = session.execute(
            select(m.source_revision_document.c.source_revision_id)
            .where(m.source_revision_document.c.document_id == document_id)
            .limit(1)
        ).scalar_one_or_none()
        if row is None or rev is None:
            return False
        revision, sha = rev, row.sha256
    session.execute(
        insert(m.extraction_run).values(
            project_id=project_id,
            document_id=document_id,
            source_revision_id=revision,
            content_sha256=sha,
            status="queued",
        )
    )
    return True


# --- runner ---------------------------------------------------------------------------------


class ExtractionRunner:
    def __init__(
        self,
        factory: sessionmaker[Session],
        store: BlobStore,
        settings: Settings,
        owner: str,
        is_dead_owner: Any,
    ) -> None:
        self._factory = factory
        self._store = store
        self._settings = settings
        self.owner = owner
        self._is_dead_owner = is_dead_owner

    def recover_once(self) -> int:
        """Running runs with a lapsed lease or a dead owner become ``interrupted``."""
        count = 0
        with session_scope(self._factory) as session:
            rows = session.execute(
                select(
                    m.extraction_run.c.run_id,
                    m.extraction_run.c.lease_owner,
                    m.extraction_run.c.lease_expires_at,
                    m.extraction_run.c.attempt_no,
                )
                .where(m.extraction_run.c.status == "running")
                .with_for_update(skip_locked=True)
            ).all()
            now = session.execute(select(func.clock_timestamp())).scalar_one()
            for row in rows:
                lapsed = row.lease_expires_at is None or row.lease_expires_at < now
                dead = row.lease_owner is not None and self._is_dead_owner(row.lease_owner)
                if not (lapsed or dead):
                    continue
                exhausted = row.attempt_no >= self._settings.extraction_max_attempts
                session.execute(
                    update(m.extraction_run)
                    .where(m.extraction_run.c.run_id == row.run_id)
                    .values(
                        status="failed" if exhausted else "interrupted",
                        lease_owner=None,
                        lease_expires_at=None,
                        finished_at=now if exhausted else None,
                        error={"code": "interrupted_too_often", "message": "attempts exhausted"}
                        if exhausted
                        else {"code": "interrupted", "message": "worker stopped mid-run"},
                    )
                )
                count += 1
        return count

    def run_once(self) -> bool:
        self.recover_once()
        with session_scope(self._factory) as session:
            enqueue_missing(session)
        claim = self._claim()
        if claim is None:
            return False
        self._process(claim)
        return True

    def _claim(self) -> RunClaim | None:
        with session_scope(self._factory) as session:
            session.execute(select(func.pg_advisory_xact_lock(0x464C0009)))
            if session.execute(
                select(m.extraction_run.c.run_id).where(m.extraction_run.c.status == "running")
            ).first():
                return None
            row = session.execute(
                select(m.extraction_run)
                .where(
                    m.extraction_run.c.superseded.is_(False),
                    m.extraction_run.c.status.in_(("queued", "interrupted")),
                    m.extraction_run.c.attempt_no < self._settings.extraction_max_attempts,
                )
                .order_by(m.extraction_run.c.queued_at, m.extraction_run.c.run_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return None
            lease = text("clock_timestamp() + make_interval(secs => :s)").bindparams(
                s=self._settings.job_lease_seconds
            )
            session.execute(
                update(m.extraction_run)
                .where(m.extraction_run.c.run_id == row.run_id)
                .values(
                    status="running",
                    attempt_no=row.attempt_no + 1,
                    lease_owner=self.owner,
                    lease_expires_at=lease,
                    started_at=func.clock_timestamp(),
                    error=None,
                )
            )
            return RunClaim(
                row.run_id,
                row.project_id,
                row.document_id,
                row.source_revision_id,
                row.attempt_no + 1,
                self.owner,
            )

    def _heartbeat(self, claim: RunClaim) -> bool:
        with session_scope(self._factory) as session:
            lease = text("clock_timestamp() + make_interval(secs => :s)").bindparams(
                s=self._settings.job_lease_seconds
            )
            result = session.execute(
                update(m.extraction_run)
                .where(
                    m.extraction_run.c.run_id == claim.run_id,
                    m.extraction_run.c.status == "running",
                    m.extraction_run.c.lease_owner == claim.owner,
                )
                .values(lease_expires_at=lease)
            )
            return bool(getattr(result, "rowcount", 0) == 1)

    def _process(self, claim: RunClaim) -> None:
        done = threading.Event()
        lost = threading.Event()

        def beat() -> None:
            while not done.wait(self._settings.job_heartbeat_seconds):
                try:
                    if not self._heartbeat(claim):
                        lost.set()
                        return
                except Exception:
                    logger.warning("extraction heartbeat failed for %s", claim.run_id)

        beater = threading.Thread(target=beat, daemon=True, name=f"extract-hb-{claim.run_id}")
        beater.start()
        try:
            self._execute(claim, lost)
        except FenceLost:
            logger.warning("extraction run %s lost its fence", claim.run_id)
        except Exception as exc:
            logger.error("extraction run %s crashed: %s", claim.run_id, type(exc).__name__)
            try:
                self._finalize_failed(claim, "extraction_error", type(exc).__name__)
            except FenceLost:
                pass
        finally:
            done.set()
            beater.join(timeout=5)

    def _execute(self, claim: RunClaim, lost: threading.Event) -> None:
        with session_scope(self._factory) as session:
            doc = session.execute(
                select(
                    m.source_document.c.storage_key,
                    m.source_document.c.sha256,
                    m.source_document.c.format_family,
                    m.source_document.c.original_filename,
                ).where(m.source_document.c.document_id == claim.document_id)
            ).one()
        path = self._store.path_for(doc.storage_key)
        if not path.is_file():
            self._finalize_failed(claim, "source_missing", "stored original is not readable")
            return
        if sha256_file(path) != doc.sha256:
            self._finalize_failed(claim, "content_hash_mismatch", "stored bytes differ from hash")
            return
        profiles = registry.detect(path, doc.format_family, doc.original_filename)
        if not profiles:
            self._finalize_unsupported(claim, doc.format_family)
            return
        profile = profiles[0]
        ctx = ParseContext(
            claim.document_id, claim.source_revision_id, doc.sha256, doc.original_filename
        )
        try:
            output = profile.parse(path, ctx)
        except ProfileError as exc:
            self._finalize_failed(
                claim, exc.code, exc.message, profile.name, profile.version, profile.method
            )
            return
        if lost.is_set():
            raise FenceLost("lease lost")
        self._finalize_ok(claim, profile.name, profile.version, profile.method, output)

    # -- finalization -----------------------------------------------------------------------
    def _fenced(self, session: Session, claim: RunClaim, **values: Any) -> None:
        result = session.execute(
            update(m.extraction_run)
            .where(
                m.extraction_run.c.run_id == claim.run_id,
                m.extraction_run.c.status == "running",
                m.extraction_run.c.lease_owner == claim.owner,
                m.extraction_run.c.superseded.is_(False),
            )
            .values(lease_owner=None, lease_expires_at=None, finished_at=func.now(), **values)
        )
        if getattr(result, "rowcount", 0) != 1:
            raise FenceLost("not the owner")

    def _set_state(self, session: Session, claim: RunClaim, state: str, detail: str | None) -> None:
        session.execute(
            update(m.document_processing)
            .where(m.document_processing.c.document_id == claim.document_id)
            .values(extraction_state=state, detail=detail, updated_at=func.now())
        )

    def _finalize_failed(
        self,
        claim: RunClaim,
        code: str,
        message: str,
        profile: str | None = None,
        version: str | None = None,
        method: str | None = None,
    ) -> None:
        with session_scope(self._factory) as session:
            self._fenced(
                session,
                claim,
                status="failed",
                profile_name=profile,
                profile_version=version,
                method=method,
                error={"code": code, "message": message[:500]},
            )
            pid = claim.project_id
            session.execute(
                delete(m.extraction_issue).where(m.extraction_issue.c.run_id == claim.run_id)
            )
            key = f"{EXTRACTION_FAILED}:{code}"
            session.execute(
                insert(m.extraction_issue).values(
                    issue_id=issue_id(claim.run_id, key),
                    project_id=pid,
                    run_id=claim.run_id,
                    producer_key=key,
                    code=EXTRACTION_FAILED,
                    severity="error",
                    message=f"Extraction failed ({code}): {message[:300]}",
                    blocked_operations=["claim_acceptance", "calculation"],
                )
            )
            self._set_state(session, claim, "extraction_failed", code)

    def _finalize_unsupported(self, claim: RunClaim, family: str) -> None:
        with session_scope(self._factory) as session:
            self._fenced(session, claim, status="unsupported", summary={"format_family": family})
            key = f"{UNSUPPORTED_FORMAT}:{family}"
            session.execute(
                delete(m.extraction_issue).where(m.extraction_issue.c.run_id == claim.run_id)
            )
            session.execute(
                insert(m.extraction_issue).values(
                    issue_id=issue_id(claim.run_id, key),
                    project_id=claim.project_id,
                    run_id=claim.run_id,
                    producer_key=key,
                    code=UNSUPPORTED_FORMAT,
                    severity="info",
                    message="No native profile recognizes this content; nothing was extracted.",
                    blocked_operations=["claim_acceptance"],
                )
            )
            self._set_state(session, claim, "unsupported", "no_matching_profile")

    def _finalize_ok(
        self, claim: RunClaim, name: str, version: str, method: str, out: ProfileOutput
    ) -> None:
        counts: dict[str, int] = {}
        wellbores: set[str] = set()
        for rec in out.records:
            counts[rec.kind] = counts.get(rec.kind, 0) + 1
            label = rec.subject.get("well_key") or rec.subject.get("wellbore_name")
            if isinstance(label, str):
                wellbores.add(label)
        coverage = out.coverage
        partial = out.status == "partial" or not coverage.complete
        status = "failed" if out.status == "failed" else ("partial" if partial else "succeeded")
        with session_scope(self._factory) as session:
            self._fenced(
                session,
                claim,
                status=status,
                profile_name=name,
                profile_version=version,
                method=method,
                coverage={
                    "unit": coverage.unit,
                    "inspected": coverage.inspected,
                    "total": coverage.total,
                    "missing_ranges": coverage.missing_ranges,
                    "reasons": coverage.reasons,
                },
                summary={
                    "record_counts": counts,
                    "wellbores": sorted(wellbores),
                    "detail": {
                        k: v
                        for k, v in out.detail.items()
                        if isinstance(v, str | int | float | bool)
                    },
                },
            )
            session.execute(
                delete(m.extracted_record).where(m.extracted_record.c.run_id == claim.run_id)
            )
            session.execute(
                delete(m.extraction_issue).where(m.extraction_issue.c.run_id == claim.run_id)
            )
            rows = [
                {
                    "project_id": claim.project_id,
                    "run_id": claim.run_id,
                    "document_id": claim.document_id,
                    "ordinal": i,
                    "kind": r.kind,
                    "subject": r.subject,
                    "locator": r.locator,
                    "effective_time": _time(r.effective_time),
                    "report_time": _time(r.report_time),
                    "validation_state": r.validation_state,
                    "attributes": [a.to_json() for a in r.attrs],
                }
                for i, r in enumerate(out.records)
            ]
            for start in range(0, len(rows), CHUNK):
                session.execute(insert(m.extracted_record), rows[start : start + CHUNK])
            seen: set[str] = set()
            issues = []
            findings = list(out.findings)
            if partial:
                from fieldlens.profiles.types import Finding

                findings.append(
                    Finding(
                        code="EXTRACTION_PARTIAL",
                        severity="warning",
                        message="Extraction did not cover the whole source: "
                        + "; ".join(coverage.reasons or ["coverage incomplete"]),
                        key="coverage",
                        blocked=["claim_acceptance"],
                    )
                )
            for f in findings:
                key = f"{name}:{f.code}:{f.key}"
                if key in seen:
                    continue
                seen.add(key)
                issues.append(
                    {
                        "issue_id": issue_id(claim.run_id, key),
                        "project_id": claim.project_id,
                        "run_id": claim.run_id,
                        "producer_key": key[:256],
                        "code": f.code,
                        "severity": f.severity,
                        "message": f.message,
                        "attribute_keys": f.attribute_keys,
                        "record_ordinals": f.record_ordinals[:200],
                        "locators": f.locators[:50],
                        "blocked_operations": f.blocked,
                    }
                )
            for start in range(0, len(issues), CHUNK):
                session.execute(insert(m.extraction_issue), issues[start : start + CHUNK])
            has_issue = any(f.severity != "info" for f in findings)
            state = (
                "extraction_failed"
                if status == "failed"
                else ("extracted_with_issues" if (has_issue or partial) else "extracted")
            )
            self._set_state(session, claim, state, None)


def _time(t: Any) -> dict[str, Any] | None:
    if t is None:
        return None
    return {
        "literal": t.literal,
        "precision": t.precision,
        "timezone": None,
        "earliest_effective": None,
        "latest_effective": None,
        "field": t.field,
    }

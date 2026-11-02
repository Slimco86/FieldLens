"""Job state transitions. Every write after claim is fenced on ``ingest_job.fence_counter`` and
``status='running'``: an attempt that lost its lease can no longer change progress, document
state or publish anything."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import Coverage, CoverageStatus
from fieldlens.contracts.imports import Job, JobAttempt, JobError, JobProgress, JobResult
from fieldlens.persistence import models as m

CLAIM_LOCK_KEY = 0x464C0006  # arbitrary stable advisory-lock key: serializes claim/recover


class FenceLost(Exception):
    """The attempt no longer owns the job (interrupted, cancelled or superseded)."""


@dataclass(frozen=True)
class Claim:
    job_id: UUID
    project_id: UUID
    source_revision_id: UUID
    fence: int
    attempt_no: int


def new_owner() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{os.urandom(4).hex()}"


def _now() -> Any:
    return func.clock_timestamp()


def claim_next(session: Session, owner: str, lease_seconds: float) -> Claim | None:
    session.execute(select(func.pg_advisory_xact_lock(CLAIM_LOCK_KEY)))
    running = session.execute(
        select(m.ingest_job_attempt.c.attempt_id).where(m.ingest_job_attempt.c.status == "running")
    ).first()
    if running is not None:
        return None  # only one heavy stage at a time
    job = (
        session.execute(
            select(m.ingest_job)
            .where(m.ingest_job.c.status == "queued")
            .order_by(m.ingest_job.c.created_at, m.ingest_job.c.job_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        .mappings()
        .first()
    )
    if job is None:
        return None
    fence = job["fence_counter"] + 1
    attempt_no = job["attempt_count"] + 1
    session.execute(
        update(m.ingest_job)
        .where(m.ingest_job.c.job_id == job["job_id"])
        .values(
            status="running",
            fence_counter=fence,
            attempt_count=attempt_no,
            stage="verify_blobs",
            updated_at=_now(),
        )
    )
    session.execute(
        m.ingest_job_attempt.insert().values(
            project_id=job["project_id"],
            job_id=job["job_id"],
            attempt_no=attempt_no,
            status="running",
            stage="verify_blobs",
            fencing_token=fence,
            lease_owner=owner,
            lease_expires_at=_now() + timedelta(seconds=lease_seconds),
            heartbeat_at=_now(),
        )
    )
    return Claim(job["job_id"], job["project_id"], job["source_revision_id"], fence, attempt_no)


def _lock_fenced(session: Session, claim: Claim) -> dict[str, Any]:
    row = (
        session.execute(
            select(m.ingest_job).where(m.ingest_job.c.job_id == claim.job_id).with_for_update()
        )
        .mappings()
        .one()
    )
    if row["fence_counter"] != claim.fence or row["status"] != "running":
        raise FenceLost(f"job {claim.job_id} fence {claim.fence} is no longer current")
    return dict(row)


def heartbeat(session: Session, claim: Claim, lease_seconds: float) -> bool:
    """Extend the lease; False when the attempt is no longer current (never revives it)."""
    updated = session.execute(
        update(m.ingest_job_attempt)
        .where(
            and_(
                m.ingest_job_attempt.c.job_id == claim.job_id,
                m.ingest_job_attempt.c.fencing_token == claim.fence,
                m.ingest_job_attempt.c.status == "running",
            )
        )
        .values(heartbeat_at=_now(), lease_expires_at=_now() + timedelta(seconds=lease_seconds))
    )
    return updated.rowcount == 1  # type: ignore[attr-defined,no-any-return]


def cancel_requested(session: Session, claim: Claim) -> bool:
    row = _lock_fenced(session, claim)
    return bool(row["cancel_requested"])


def set_progress(session: Session, claim: Claim, processed: int, total: int) -> None:
    _lock_fenced(session, claim)
    session.execute(
        update(m.ingest_job)
        .where(m.ingest_job.c.job_id == claim.job_id)
        .values(
            progress_processed=processed,
            progress_total=total,
            progress_unit="document",
            updated_at=_now(),
        )
    )


def pending_documents(session: Session, claim: Claim) -> list[dict[str, Any]]:
    sd, srd, dp = m.source_document, m.source_revision_document, m.document_processing
    rows = session.execute(
        select(sd.c.document_id, sd.c.storage_key, sd.c.sha256, sd.c.size_bytes, dp.c.storage_state)
        .select_from(
            srd.join(
                sd,
                and_(sd.c.project_id == srd.c.project_id, sd.c.document_id == srd.c.document_id),
            ).join(dp, dp.c.document_id == sd.c.document_id)
        )
        .where(
            and_(
                srd.c.project_id == claim.project_id,
                srd.c.source_revision_id == claim.source_revision_id,
            )
        )
        .order_by(sd.c.created_at, sd.c.document_id)
    ).mappings()
    return [dict(r) for r in rows]


def record_document(
    session: Session,
    claim: Claim,
    document_id: UUID,
    state: str,
    detail: str | None,
    failure_reason: str | None = None,
    failed_by: str | None = None,
) -> None:
    _lock_fenced(session, claim)
    session.execute(
        update(m.document_processing)
        .where(
            and_(
                m.document_processing.c.project_id == claim.project_id,
                m.document_processing.c.document_id == document_id,
            )
        )
        .values(
            storage_state=state,
            detail=detail,
            storage_failure_reason=failure_reason,
            storage_failed_by=failed_by[:300] if failed_by else None,
            updated_at=_now(),
        )
    )


def _finish_job(
    session: Session,
    claim: Claim,
    job_status: str,
    attempt_status: str,
    *,
    result: dict[str, Any] | None = None,
    error: dict[str, str] | None = None,
) -> None:
    session.execute(
        update(m.ingest_job)
        .where(m.ingest_job.c.job_id == claim.job_id)
        .values(
            status=job_status,
            result=result,
            error=error,
            stage=None,
            updated_at=_now(),
            finished_at=_now(),
        )
    )
    session.execute(
        update(m.ingest_job_attempt)
        .where(
            and_(
                m.ingest_job_attempt.c.job_id == claim.job_id,
                m.ingest_job_attempt.c.fencing_token == claim.fence,
            )
        )
        .values(
            status=attempt_status,
            ended_at=_now(),
            error=error,
        )
    )


def _fail_revision(session: Session, claim: Claim, reason: str) -> None:
    coverage = Coverage(status=CoverageStatus.UNKNOWN, reasons=[reason])
    session.execute(
        update(m.source_revision)
        .where(
            and_(
                m.source_revision.c.project_id == claim.project_id,
                m.source_revision.c.source_revision_id == claim.source_revision_id,
                m.source_revision.c.status == "staging",
            )
        )
        .values(status="failed", coverage=coverage.model_dump(mode="json"))
    )


def finalize_cancelled(session: Session, claim: Claim) -> None:
    _lock_fenced(session, claim)
    _fail_revision(session, claim, "import_cancelled: nothing was published")
    _finish_job(session, claim, "cancelled", "cancelled")


def finalize_failed(session: Session, claim: Claim, code: str, message: str) -> None:
    _lock_fenced(session, claim)
    _fail_revision(session, claim, f"{code}: {message}")
    _finish_job(session, claim, "failed", "failed", error={"code": code, "message": message})


def publish(session: Session, claim: Claim) -> str:
    """Fenced publication of storage-verification results. Moves only the *source* pointer;
    never creates or activates an asset model."""
    _lock_fenced(session, claim)
    sd, srd, dp = m.source_document, m.source_revision_document, m.document_processing
    counts = session.execute(
        select(
            func.count(),
            func.count().filter(dp.c.storage_state == "stored"),
            func.count().filter(dp.c.storage_state == "failed"),
            func.count().filter(dp.c.storage_state == "pending_verification"),
            func.count().filter(dp.c.extraction_state == "pending_extraction"),
            func.count().filter(dp.c.extraction_state == "unsupported"),
        )
        .select_from(
            srd.join(
                sd,
                and_(sd.c.project_id == srd.c.project_id, sd.c.document_id == srd.c.document_id),
            ).join(dp, dp.c.document_id == sd.c.document_id)
        )
        .where(
            and_(
                srd.c.project_id == claim.project_id,
                srd.c.source_revision_id == claim.source_revision_id,
            )
        )
    ).one()
    total, stored, failed, unverified, pending, unsupported = counts
    if unverified:
        raise RuntimeError("publish attempted with unverified documents")
    result = JobResult(
        result_kind="storage_verification",
        documents=total,
        stored=stored,
        failed=failed,
        pending_extraction=pending,
        unsupported=unsupported,
        extraction_performed=False,
    ).model_dump(mode="json")
    if stored == 0:
        _fail_revision(session, claim, f"all_documents_failed: {failed} of {total}")
        _finish_job(
            session,
            claim,
            "failed",
            "failed",
            result=result,
            error={"code": "all_failed", "message": "no stored copy could be verified"},
        )
        return "failed"
    reasons = ["extraction_not_performed: storage verification only"]
    if failed:
        reasons.append(f"failed_documents: {failed} of {total}")
    revision_status = "ready_with_issues" if failed else "ready"
    session.execute(
        update(m.source_revision)
        .where(
            and_(
                m.source_revision.c.project_id == claim.project_id,
                m.source_revision.c.source_revision_id == claim.source_revision_id,
            )
        )
        .values(
            status=revision_status,
            coverage=Coverage(status=CoverageStatus.UNKNOWN, reasons=reasons).model_dump(
                mode="json"
            ),
        )
    )
    parent = session.execute(
        select(m.source_revision.c.parent_source_revision_id).where(
            m.source_revision.c.source_revision_id == claim.source_revision_id
        )
    ).scalar_one()
    moved = session.execute(
        update(m.project)
        .where(
            and_(
                m.project.c.project_id == claim.project_id,
                m.project.c.latest_source_revision_id.is_not_distinct_from(parent),
            )
        )
        .values(latest_source_revision_id=claim.source_revision_id)
    )
    if moved.rowcount != 1:  # type: ignore[attr-defined]
        raise FenceLost("project source pointer moved since staging")
    _finish_job(session, claim, "partial" if failed else "succeeded", "succeeded", result=result)
    return revision_status


def recover(session: Session, is_dead_owner: Any) -> list[UUID]:
    """Mark expired / dead-owner running attempts interrupted; requeue under a new fence until
    attempts are exhausted, then leave the job interrupted and its staging revision failed."""
    session.execute(select(func.pg_advisory_xact_lock(CLAIM_LOCK_KEY)))
    rows = (
        session.execute(
            select(m.ingest_job_attempt, m.ingest_job.c.attempt_count, m.ingest_job.c.max_attempts)
            .join(m.ingest_job, m.ingest_job.c.job_id == m.ingest_job_attempt.c.job_id)
            .where(m.ingest_job_attempt.c.status == "running")
            .with_for_update(of=m.ingest_job_attempt)
        )
        .mappings()
        .all()
    )
    now = session.execute(select(func.clock_timestamp())).scalar_one()
    recovered: list[UUID] = []
    for row in rows:
        if not (row["lease_expires_at"] <= now or is_dead_owner(row["lease_owner"])):
            continue
        job_id = row["job_id"]
        error = {"code": "attempt_interrupted", "message": "worker stopped before finishing"}
        session.execute(
            update(m.ingest_job_attempt)
            .where(m.ingest_job_attempt.c.attempt_id == row["attempt_id"])
            .values(status="interrupted", ended_at=_now(), error=error)
        )
        if row["attempt_count"] < row["max_attempts"]:
            session.execute(
                update(m.ingest_job)
                .where(m.ingest_job.c.job_id == job_id)
                .values(status="queued", stage="queued", updated_at=_now())
            )
        else:
            claim_row = (
                session.execute(select(m.ingest_job).where(m.ingest_job.c.job_id == job_id))
                .mappings()
                .one()
            )
            claim = Claim(
                job_id,
                claim_row["project_id"],
                claim_row["source_revision_id"],
                claim_row["fence_counter"],
                row["attempt_no"],
            )
            _fail_revision(session, claim, "attempt_interrupted: retries exhausted")
            session.execute(
                update(m.ingest_job)
                .where(m.ingest_job.c.job_id == job_id)
                .values(
                    status="interrupted",
                    error=error,
                    stage=None,
                    updated_at=_now(),
                    finished_at=_now(),
                )
            )
        recovered.append(job_id)
    return recovered


def request_cancel(session: Session, project_id: UUID, job_id: UUID) -> None:
    row = (
        session.execute(
            select(m.ingest_job)
            .where(and_(m.ingest_job.c.project_id == project_id, m.ingest_job.c.job_id == job_id))
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "job not found", 404)
    if row["status"] == "queued":
        claim = Claim(
            job_id,
            project_id,
            row["source_revision_id"],
            row["fence_counter"],
            row["attempt_count"],
        )
        _fail_revision(session, claim, "import_cancelled: nothing was published")
        session.execute(
            update(m.ingest_job)
            .where(m.ingest_job.c.job_id == job_id)
            .values(
                status="cancelled",
                cancel_requested=True,
                stage=None,
                updated_at=_now(),
                finished_at=_now(),
            )
        )
    elif row["status"] == "running":
        session.execute(
            update(m.ingest_job)
            .where(m.ingest_job.c.job_id == job_id)
            .values(cancel_requested=True, updated_at=_now())
        )


def get_job(session: Session, project_id: UUID, job_id: UUID) -> Job:
    row = (
        session.execute(
            select(m.ingest_job).where(
                and_(m.ingest_job.c.project_id == project_id, m.ingest_job.c.job_id == job_id)
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "job not found", 404)
    attempts = (
        session.execute(
            select(m.ingest_job_attempt)
            .where(m.ingest_job_attempt.c.job_id == job_id)
            .order_by(m.ingest_job_attempt.c.attempt_no)
        )
        .mappings()
        .all()
    )
    return Job(
        job_id=row["job_id"],
        project_id=row["project_id"],
        kind=row["kind"],
        source_revision_id=row["source_revision_id"],
        status=row["status"],
        stage=row["stage"],
        progress=JobProgress(
            processed=row["progress_processed"],
            total=row["progress_total"],
            unit=row["progress_unit"],
        ),
        cancel_requested=row["cancel_requested"],
        attempts=[
            JobAttempt(
                attempt_no=a["attempt_no"],
                status=a["status"],
                stage=a["stage"],
                fencing_token=a["fencing_token"],
                started_at=a["started_at"],
                heartbeat_at=a["heartbeat_at"],
                ended_at=a["ended_at"],
                error_code=(a["error"] or {}).get("code"),
            )
            for a in attempts
        ],
        result=JobResult.model_validate(row["result"]) if row["result"] else None,
        error=JobError.model_validate(row["error"]) if row["error"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
    )

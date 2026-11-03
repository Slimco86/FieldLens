"""Processing-run runner: one lease per run, bounded document concurrency, honest outcomes.

* A confirmed (``queued``) run is claimed with a lease and an attempt fence; every write checks
  the fence, so a stale worker can never overwrite a recovered or cancelled run.
* Documents run on a bounded thread pool (``processing_document_concurrency``); all work is
  synchronous code in worker threads, never on the API event loop.
* A run whose worker died or whose lease lapsed becomes ``interrupted`` (never succeeded); its
  unfinished documents become ``interrupted`` and retryable through a new estimate and confirm.
* Cancellation, provider failures, refusals, truncation, a budget stop and a confirmed estimate
  exceeded by actual usage each leave an explicit, retryable document state. Nothing restarts or
  spends automatically.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.contracts.processing import ProcessingFailureCode
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope
from fieldlens.processing import tables as t
from fieldlens.processing.service import PageCounter
from fieldlens.processing.steps import (
    DocumentTask,
    PageFailure,
    PageProvider,
    PageUsage,
    ProcessingStep,
    RunStop,
)

logger = logging.getLogger(__name__)
pr, prd = t.processing_run, t.processing_run_document
_UNFINISHED = ("pending", "running")


class FenceLost(Exception):
    """The run lease/attempt no longer belongs to this worker; abandon without writing."""


@dataclass(frozen=True)
class Claim:
    run_id: UUID
    project_id: UUID
    attempt_no: int
    confirmed_usd: Decimal


def _now() -> Any:
    return func.clock_timestamp()


class ProcessingRunner:
    def __init__(
        self,
        factory: sessionmaker[Session],
        counter: PageCounter,
        settings: Settings,
        provider: PageProvider,
        step: ProcessingStep,
        owner: str,
        is_dead_owner: Any,
        root_guard: StorageRootGuard | None = None,
    ) -> None:
        self._root_guard = root_guard
        self._factory = factory
        self._counter = counter
        self._settings = settings
        self._provider = provider
        self._step = step
        self.owner = owner
        self._is_dead_owner = is_dead_owner
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- recovery ---------------------------------------------------------------------------
    def recover_once(self) -> list[UUID]:
        """Running runs with a lapsed lease or dead owner become ``interrupted``."""
        recovered: list[UUID] = []
        with session_scope(self._factory) as s:
            rows = s.execute(
                select(pr.c.run_id, pr.c.lease_owner, pr.c.lease_expires_at)
                .where(pr.c.status == "running")
                .with_for_update(skip_locked=True)
            ).all()
            now = s.execute(select(_now())).scalar_one()
            for row in rows:
                lapsed = row.lease_expires_at is None or row.lease_expires_at < now
                dead = row.lease_owner is not None and self._is_dead_owner(row.lease_owner)
                if not (lapsed or dead):
                    continue
                s.execute(
                    update(prd)
                    .where(prd.c.run_id == row.run_id, prd.c.state.in_(_UNFINISHED))
                    .values(
                        state="interrupted",
                        failure_code=ProcessingFailureCode.INTERRUPTED.value,
                        failure_message="the worker stopped before this document finished",
                        retryable=True,
                        finished_at=now,
                    )
                )
                s.execute(
                    update(pr)
                    .where(pr.c.run_id == row.run_id)
                    .values(
                        status="interrupted",
                        lease_owner=None,
                        lease_expires_at=None,
                        error_code=ProcessingFailureCode.INTERRUPTED.value,
                        error_message="the worker stopped mid-run; not completed",
                        finished_at=now,
                    )
                )
                recovered.append(row.run_id)
        return recovered

    # -- claim ------------------------------------------------------------------------------
    def _claim(self) -> Claim | None:
        with session_scope(self._factory) as s:
            row = s.execute(
                select(pr.c.run_id, pr.c.project_id, pr.c.attempt_no, pr.c.confirmed_usd)
                .where(pr.c.status == "queued", pr.c.confirmed_usd.is_not(None))
                .order_by(pr.c.confirmed_at, pr.c.run_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return None
            attempt = row.attempt_no + 1
            s.execute(
                update(pr)
                .where(pr.c.run_id == row.run_id)
                .values(
                    status="running",
                    attempt_no=attempt,
                    lease_owner=self.owner,
                    lease_expires_at=_now() + _interval(self._settings.processing_lease_seconds),
                    started_at=func.coalesce(pr.c.started_at, _now()),
                )
            )
            return Claim(row.run_id, row.project_id, attempt, row.confirmed_usd)

    def _fence(self, s: Session, claim: Claim) -> None:
        ok = s.execute(
            select(pr.c.run_id).where(
                pr.c.run_id == claim.run_id,
                pr.c.status == "running",
                pr.c.lease_owner == self.owner,
                pr.c.attempt_no == claim.attempt_no,
            )
        ).first()
        if ok is None:
            raise FenceLost(str(claim.run_id))

    # -- execution --------------------------------------------------------------------------
    def run_once(self) -> bool:
        self.recover_once()
        if self._root_guard is not None and not self._root_guard.serves_database():
            return False  # wrong storage root: leave the confirmed run queued
        claim = self._claim()
        if claim is None:
            return False
        self._process(claim)
        return True

    def _process(self, claim: Claim) -> None:
        done = threading.Event()
        lost = threading.Event()

        def beat() -> None:
            while not done.wait(self._settings.processing_heartbeat_seconds):
                try:
                    with session_scope(self._factory) as s:
                        n = s.execute(
                            update(pr)
                            .where(
                                pr.c.run_id == claim.run_id,
                                pr.c.status == "running",
                                pr.c.lease_owner == self.owner,
                                pr.c.attempt_no == claim.attempt_no,
                            )
                            .values(
                                lease_expires_at=_now()
                                + _interval(self._settings.processing_lease_seconds)
                            )
                            .returning(pr.c.run_id)
                        ).first()
                    if n is None:
                        lost.set()
                        return
                except Exception:
                    logger.warning("processing heartbeat failed for run %s", claim.run_id)

        beater = threading.Thread(
            target=beat, name=f"processing-heartbeat-{claim.run_id}", daemon=True
        )
        beater.start()
        try:
            self._run_documents(claim, lost)
        except FenceLost:
            logger.warning("processing run %s lost its fence", claim.run_id)
        except Exception as exc:
            logger.error("processing run %s crashed: %s", claim.run_id, type(exc).__name__)
            # Deliberately not a success: leave the lease to lapse so recovery marks it interrupted.
            self._abandon(claim)
        finally:
            done.set()
            beater.join(timeout=5)

    def _abandon(self, claim: Claim) -> None:
        """Hand a crashed run to recovery immediately instead of waiting for the lease."""
        try:
            with session_scope(self._factory) as s:
                s.execute(
                    update(pr)
                    .where(
                        pr.c.run_id == claim.run_id,
                        pr.c.lease_owner == self.owner,
                        pr.c.attempt_no == claim.attempt_no,
                    )
                    .values(lease_expires_at=_now())
                )
        except Exception:
            logger.error("could not release lease of processing run %s", claim.run_id)
        self.recover_once()

    def _run_documents(self, claim: Claim, lost: threading.Event) -> None:
        with session_scope(self._factory) as s:
            docs = s.execute(
                select(prd, _storage_key())
                .where(prd.c.run_id == claim.run_id, prd.c.state == "pending")
                .order_by(prd.c.ordinal)
            ).all()
        stop: list[RunStop] = []
        stop_lock = threading.Lock()

        def work(row: Any) -> None:
            if stop or lost.is_set():
                return
            try:
                self._document(claim, row, lost, stop, stop_lock)
            except FenceLost:
                lost.set()

        with ThreadPoolExecutor(
            max_workers=self._settings.processing_document_concurrency,
            thread_name_prefix="processing-doc",
        ) as pool:
            list(pool.map(work, docs))
        if lost.is_set():
            raise FenceLost(str(claim.run_id))
        self._finalize(claim, stop[0] if stop else None)

    def _document(
        self,
        claim: Claim,
        row: Any,
        lost: threading.Event,
        stop: list[RunStop],
        stop_lock: threading.Lock,
    ) -> None:
        with session_scope(self._factory) as s:
            self._fence(s, claim)
            cancelled = s.execute(
                select(pr.c.cancel_requested).where(pr.c.run_id == claim.run_id)
            ).scalar_one()
            if cancelled:
                with stop_lock:
                    stop.append(RunStop(ProcessingFailureCode.CANCELLED, "cancelled by the user"))
            if stop:
                return
            s.execute(
                update(prd)
                .where(prd.c.run_id == claim.run_id, prd.c.document_id == row.document_id)
                .values(state="running")
            )
        task = DocumentTask(
            project_id=claim.project_id,
            run_id=claim.run_id,
            document_id=row.document_id,
            source_revision_id=row.source_revision_id,
            storage_key=row.storage_key,
            page_count=row.page_count,
            page_start=row.page_start,
            page_end=row.page_end,
            label_hints=tuple(row.label_hints or ()),
        )

        def checkpoint(page: int, usage: PageUsage) -> None:
            if lost.is_set():
                raise FenceLost(str(claim.run_id))
            if stop:
                raise stop[0]
            exceeded = False
            cancel = False
            with session_scope(self._factory) as s:
                updated = s.execute(
                    update(pr)
                    .where(
                        pr.c.run_id == claim.run_id,
                        pr.c.status == "running",
                        pr.c.lease_owner == self.owner,
                        pr.c.attempt_no == claim.attempt_no,
                    )
                    .values(actual_usd=pr.c.actual_usd + usage.cost_usd)
                    .returning(pr.c.actual_usd, pr.c.cancel_requested)
                ).first()
                if updated is None:
                    raise FenceLost(str(claim.run_id))
                s.execute(
                    update(prd)
                    .where(prd.c.run_id == claim.run_id, prd.c.document_id == row.document_id)
                    .values(
                        pages_done=prd.c.pages_done + 1,
                        actual_usd=prd.c.actual_usd + usage.cost_usd,
                    )
                )
                exceeded = updated.actual_usd > claim.confirmed_usd
                cancel = updated.cancel_requested
            if exceeded:
                raise self._record_stop(
                    stop,
                    stop_lock,
                    RunStop(
                        ProcessingFailureCode.CONFIRMED_ESTIMATE_EXCEEDED,
                        "actual usage exceeded the confirmed estimate",
                    ),
                )
            if cancel:
                raise self._record_stop(
                    stop,
                    stop_lock,
                    RunStop(ProcessingFailureCode.CANCELLED, "cancelled by the user"),
                )
            self._pause(lost)

        try:
            self._verify_pages(task)
            self._step.run_document(task, self._provider, checkpoint)
        except RunStop as halt:
            self._finish_document(
                claim, row.document_id, "cancelled", halt.code, halt.message, True
            )
            return
        except PageFailure as failure:
            self._finish_document(
                claim, row.document_id, "failed", failure.code, failure.message, failure.retryable
            )
            return
        except FenceLost:
            raise
        except Exception as exc:  # unexpected step/provider crash: explicit, retryable failure
            logger.error("processing step crashed: %s", type(exc).__name__)
            self._finish_document(
                claim,
                row.document_id,
                "failed",
                ProcessingFailureCode.PROVIDER_ERROR,
                f"step error: {type(exc).__name__}",
                True,
            )
            return
        self._finish_document(claim, row.document_id, "processed", None, None, False)

    @staticmethod
    def _record_stop(stop: list[RunStop], lock: threading.Lock, halt: RunStop) -> RunStop:
        with lock:
            if not stop:
                stop.append(halt)
            return stop[0]

    def _verify_pages(self, task: DocumentTask) -> None:
        try:
            count = self._counter.fresh(task.storage_key)
        except Exception as exc:
            raise PageFailure(
                ProcessingFailureCode.DOCUMENT_UNAVAILABLE, "the stored PDF could not be read"
            ) from exc
        if count != task.page_count:
            raise PageFailure(
                ProcessingFailureCode.PAGE_COUNT_CHANGED,
                f"page count changed from {task.page_count} to {count}",
            )

    def _pause(self, lost: threading.Event) -> None:
        remaining = self._settings.processing_stage_delay_s
        while remaining > 0:
            if lost.is_set():
                raise FenceLost("lease lost")
            step = min(0.05, remaining)
            time.sleep(step)
            remaining -= step

    def _finish_document(
        self,
        claim: Claim,
        document_id: UUID,
        state: str,
        code: ProcessingFailureCode | None,
        message: str | None,
        retryable: bool,
    ) -> None:
        if state == "failed":  # one structured line: ids, code and the safe reason only
            logger.warning(
                "processing document failed run_id=%s document_id=%s code=%s reason=%s",
                claim.run_id,
                document_id,
                code.value if code else None,
                (message or "")[:400],
            )
        with session_scope(self._factory) as s:
            self._fence(s, claim)
            s.execute(
                update(prd)
                .where(prd.c.run_id == claim.run_id, prd.c.document_id == document_id)
                .values(
                    state=state,
                    failure_code=code.value if code else None,
                    failure_message=(message or "")[:400] or None,
                    retryable=retryable,
                    finished_at=_now(),
                )
            )

    def _finalize(self, claim: Claim, halt: RunStop | None) -> None:
        with session_scope(self._factory) as s:
            self._fence(s, claim)
            code = halt.code if halt else None
            # documents the stop kept from starting are explicit, retryable and never "processed"
            s.execute(
                update(prd)
                .where(prd.c.run_id == claim.run_id, prd.c.state == "pending")
                .values(
                    state="cancelled",
                    failure_code=(code or ProcessingFailureCode.CANCELLED).value,
                    failure_message=(halt.message if halt else "not started")[:400],
                    retryable=True,
                    finished_at=_now(),
                )
            )
            states = [
                r.state for r in s.execute(select(prd.c.state).where(prd.c.run_id == claim.run_id))
            ]
            first_failure = s.execute(
                select(prd.c.failure_code, prd.c.failure_message)
                .where(prd.c.run_id == claim.run_id, prd.c.failure_code.is_not(None))
                .order_by(prd.c.ordinal)
                .limit(1)
            ).first()
            processed = sum(1 for x in states if x == "processed")
            if code is ProcessingFailureCode.CANCELLED:
                status = "cancelled"
            elif processed == len(states):
                status = "succeeded"
            elif processed:
                status = "partial"
            else:
                status = "failed"
            error_code = error_message = None
            if status != "succeeded":
                if halt is not None:
                    error_code, error_message = halt.code.value, halt.message
                elif first_failure is not None:
                    error_code, error_message = (
                        first_failure.failure_code,
                        first_failure.failure_message,
                    )
            s.execute(
                update(pr)
                .where(pr.c.run_id == claim.run_id)
                .values(
                    status=status,
                    lease_owner=None,
                    lease_expires_at=None,
                    error_code=error_code,
                    error_message=(error_message or None),
                    finished_at=_now(),
                )
            )

    # -- thread -----------------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="fieldlens-processing", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                handled = self.run_once()
            except Exception as exc:
                logger.error("processing loop error: %s", type(exc).__name__)
                handled = False
            if not handled:
                self._stop.wait(self._settings.job_poll_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=15)
            self._thread = None


def _interval(seconds: float) -> Any:
    return timedelta(seconds=seconds)


def _storage_key() -> Any:
    sd = m.source_document
    return (
        select(sd.c.storage_key)
        .where(sd.c.project_id == prd.c.project_id, sd.c.document_id == prd.c.document_id)
        .scalar_subquery()
        .label("storage_key")
    )

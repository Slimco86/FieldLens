"""Reconstruction-run runner: one lease per run, S1..S4 in order, honest outcomes (TASK-068).

Same patterns as the TASK-054 processing runner:

* a ``queued`` run is claimed with a lease and an attempt fence; every write checks the fence, so a
  stale worker can never overwrite a recovered or cancelled run;
* at most ``reconstruction_concurrency`` (<= 2) runs execute at once; a bulk estimate's runs are
  claimed one after another in confirm order, never all at once;
* a run whose worker died or whose lease lapsed becomes ``interrupted`` (never succeeded), with its
  unfinished stages ``interrupted``; retry is a new estimate and confirm;
* a stage that cannot run is ``not_available`` and makes the run ``partial``; a failed stage fails
  the run and skips the rest; a cancel stops between stages or at a checkpoint.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.contracts.reconstruction import ReconstructionStageName
from fieldlens.persistence.session import session_scope
from fieldlens.reconstruction import tables as t
from fieldlens.reconstruction.stages import (
    StageContext,
    StageExecutor,
    StageResult,
    StageStop,
)

logger = logging.getLogger(__name__)
rr, rs = t.reconstruction_run, t.reconstruction_run_stage
_UNFINISHED = ("pending", "running")


class FenceLost(Exception):
    """The run lease/attempt no longer belongs to this worker; abandon without writing."""


@dataclass(frozen=True)
class Claim:
    run_id: UUID
    project_id: UUID
    well_id: UUID
    wellbore_id: UUID
    wellbore_name: str
    source_revision: str
    attempt_no: int
    confirmed_usd: Decimal


def _now() -> Any:
    return func.clock_timestamp()


def _interval(seconds: float) -> Any:
    return timedelta(seconds=seconds)


class ReconstructionRunner:
    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: Settings,
        executors: Sequence[StageExecutor],
        owner: str,
        is_dead_owner: Callable[[str], bool],
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._executors = list(executors)
        self.owner = owner
        self._is_dead_owner = is_dead_owner
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # -- recovery ---------------------------------------------------------------------------
    def recover_once(self) -> list[UUID]:
        """Running runs with a lapsed lease or dead owner become ``interrupted``."""
        recovered: list[UUID] = []
        with session_scope(self._factory) as s:
            rows = s.execute(
                select(rr.c.run_id, rr.c.lease_owner, rr.c.lease_expires_at)
                .where(rr.c.status == "running")
                .with_for_update(skip_locked=True)
            ).all()
            now = s.execute(select(_now())).scalar_one()
            for row in rows:
                lapsed = row.lease_expires_at is None or row.lease_expires_at < now
                dead = row.lease_owner is not None and self._is_dead_owner(row.lease_owner)
                if not (lapsed or dead):
                    continue
                s.execute(
                    update(rs)
                    .where(rs.c.run_id == row.run_id, rs.c.state.in_(_UNFINISHED))
                    .values(
                        state="interrupted",
                        reason_code="interrupted",
                        message="the worker stopped before this stage finished",
                        finished_at=now,
                    )
                )
                s.execute(
                    update(rr)
                    .where(rr.c.run_id == row.run_id)
                    .values(
                        status="interrupted",
                        lease_owner=None,
                        lease_expires_at=None,
                        error_code="interrupted",
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
                select(
                    rr.c.run_id,
                    rr.c.project_id,
                    rr.c.well_id,
                    rr.c.wellbore_id,
                    rr.c.wellbore_name,
                    rr.c.source_revision,
                    rr.c.attempt_no,
                    rr.c.confirmed_usd,
                )
                .where(rr.c.status == "queued", rr.c.confirmed_usd.is_not(None))
                .order_by(rr.c.confirmed_at, rr.c.run_id)
                .limit(1)
                .with_for_update(skip_locked=True)
            ).first()
            if row is None:
                return None
            attempt = row.attempt_no + 1
            s.execute(
                update(rr)
                .where(rr.c.run_id == row.run_id)
                .values(
                    status="running",
                    attempt_no=attempt,
                    lease_owner=self.owner,
                    lease_expires_at=_now() + _interval(self._settings.processing_lease_seconds),
                    started_at=func.coalesce(rr.c.started_at, _now()),
                )
            )
            return Claim(
                row.run_id,
                row.project_id,
                row.well_id,
                row.wellbore_id,
                row.wellbore_name,
                row.source_revision,
                attempt,
                row.confirmed_usd,
            )

    def _fence(self, s: Session, claim: Claim) -> None:
        ok = s.execute(
            select(rr.c.run_id).where(
                rr.c.run_id == claim.run_id,
                rr.c.status == "running",
                rr.c.lease_owner == self.owner,
                rr.c.attempt_no == claim.attempt_no,
            )
        ).first()
        if ok is None:
            raise FenceLost(str(claim.run_id))

    # -- execution --------------------------------------------------------------------------
    def run_once(self) -> bool:
        self.recover_once()
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
                    if not self._renew(claim):
                        lost.set()
                        return
                except Exception:
                    logger.warning("reconstruction heartbeat failed for run %s", claim.run_id)

        beater = threading.Thread(
            target=beat, name=f"reconstruction-heartbeat-{claim.run_id}", daemon=True
        )
        beater.start()
        try:
            self._run_stages(claim, lost)
        except FenceLost:
            logger.warning("reconstruction run %s lost its fence", claim.run_id)
        except Exception as exc:
            logger.error("reconstruction run %s crashed: %s", claim.run_id, type(exc).__name__)
            # Deliberately not a success: the lease lapses at once and recovery marks it interrupted.
            self._abandon(claim)
        finally:
            done.set()
            beater.join(timeout=5)

    def _renew(self, claim: Claim) -> bool:
        """Extend the lease; False when the fence is lost."""
        with session_scope(self._factory) as s:
            row = s.execute(
                update(rr)
                .where(
                    rr.c.run_id == claim.run_id,
                    rr.c.status == "running",
                    rr.c.lease_owner == self.owner,
                    rr.c.attempt_no == claim.attempt_no,
                )
                .values(
                    lease_expires_at=_now() + _interval(self._settings.processing_lease_seconds)
                )
                .returning(rr.c.run_id)
            ).first()
        return row is not None

    def _abandon(self, claim: Claim) -> None:
        try:
            with session_scope(self._factory) as s:
                s.execute(
                    update(rr)
                    .where(
                        rr.c.run_id == claim.run_id,
                        rr.c.lease_owner == self.owner,
                        rr.c.attempt_no == claim.attempt_no,
                    )
                    .values(lease_expires_at=_now())
                )
        except Exception:
            logger.error("could not release lease of reconstruction run %s", claim.run_id)
        self.recover_once()

    def _run_stages(self, claim: Claim, lost: threading.Event) -> None:
        results: dict[ReconstructionStageName, StageResult] = {}
        halt: str | None = None  # "cancelled" | "failed"
        spent = Decimal(0)

        def checkpoint() -> None:
            if lost.is_set():
                raise FenceLost(str(claim.run_id))
            with session_scope(self._factory) as s:
                row = s.execute(
                    update(rr)
                    .where(
                        rr.c.run_id == claim.run_id,
                        rr.c.status == "running",
                        rr.c.lease_owner == self.owner,
                        rr.c.attempt_no == claim.attempt_no,
                    )
                    .values(
                        lease_expires_at=_now() + _interval(self._settings.processing_lease_seconds)
                    )
                    .returning(rr.c.cancel_requested)
                ).first()
            if row is None:
                raise FenceLost(str(claim.run_id))
            if row.cancel_requested:
                raise StageStop("cancelled by the user")

        for ex in self._executors:
            name = ex.stage
            if lost.is_set():
                raise FenceLost(str(claim.run_id))
            if halt is None:
                try:
                    checkpoint()
                except StageStop:
                    halt = "cancelled"
            if not ex.available:
                results[name] = StageResult("not_available", ex.reason_code, ex.message)
                self._persist_stage(claim, name, results[name])
                continue
            if halt is not None:
                self._mark_stage(
                    claim,
                    name,
                    "cancelled" if halt == "cancelled" else "skipped",
                    "cancelled" if halt == "cancelled" else "previous_stage_failed",
                )
                continue
            self._mark_running(claim, name)
            ctx = StageContext(
                factory=self._factory,
                settings=self._settings,
                project_id=claim.project_id,
                run_id=claim.run_id,
                well_id=claim.well_id,
                wellbore_id=claim.wellbore_id,
                wellbore_name=claim.wellbore_name,
                source_revision=claim.source_revision,
                previous=dict(results),
                checkpoint=checkpoint,
            )
            try:
                result = ex.run(ctx)
            except StageStop:
                self._mark_stage(claim, name, "cancelled", "cancelled")
                halt = "cancelled"
                continue
            except FenceLost:
                raise
            except Exception as exc:  # unexpected stage crash: explicit failure, never success
                logger.error("reconstruction stage %s crashed: %s", name.value, type(exc).__name__)
                result = StageResult(
                    "failed",
                    message=f"stage error: {type(exc).__name__}",
                    error_code="stage_error",
                )
            results[name] = result
            spent += result.usd
            if spent > claim.confirmed_usd:
                results[name] = StageResult(
                    "failed",
                    message="actual usage exceeded the confirmed estimate",
                    error_code="confirmed_estimate_exceeded",
                    usd=result.usd,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                )
            self._persist_stage(claim, name, results[name])
            if results[name].state == "failed":
                halt = "failed"
        if lost.is_set():
            raise FenceLost(str(claim.run_id))
        self._finalize(claim, results, halt)

    def _mark_running(self, claim: Claim, name: ReconstructionStageName) -> None:
        with session_scope(self._factory) as s:
            self._fence(s, claim)
            s.execute(
                update(rs)
                .where(rs.c.run_id == claim.run_id, rs.c.stage == name.value)
                .values(state="running", started_at=_now(), reason_code=None, message=None)
            )

    def _mark_stage(
        self, claim: Claim, name: ReconstructionStageName, state: str, reason: str
    ) -> None:
        with session_scope(self._factory) as s:
            self._fence(s, claim)
            s.execute(
                update(rs)
                .where(rs.c.run_id == claim.run_id, rs.c.stage == name.value)
                .values(state=state, reason_code=reason, finished_at=_now())
            )

    def _persist_stage(self, claim: Claim, name: ReconstructionStageName, r: StageResult) -> None:
        with session_scope(self._factory) as s:
            self._fence(s, claim)
            s.execute(
                update(rs)
                .where(rs.c.run_id == claim.run_id, rs.c.stage == name.value)
                .values(
                    state=r.state,
                    reason_code=r.reason_code,
                    message=(r.message or "")[:400] or None,
                    counts=r.counts,
                    input_tokens=r.input_tokens,
                    output_tokens=r.output_tokens,
                    actual_usd=r.usd,
                    error_code=r.error_code,
                    finished_at=_now(),
                )
            )
            values: dict[str, Any] = {}
            if r.usd:
                values["actual_usd"] = rr.c.actual_usd + r.usd
            if r.summary is not None:
                values["summary"] = r.summary.model_dump(mode="json")
            if values:
                s.execute(update(rr).where(rr.c.run_id == claim.run_id).values(**values))

    def _finalize(
        self, claim: Claim, results: dict[ReconstructionStageName, StageResult], halt: str | None
    ) -> None:
        failed = [r for r in results.values() if r.state == "failed"]
        unavailable = [n for n, r in results.items() if r.state == "not_available"]
        error_code: str | None = None
        error_message: str | None = None
        if halt == "cancelled":
            status, error_code, error_message = "cancelled", "cancelled", "cancelled by the user"
        elif failed:
            status = "failed"
            error_code, error_message = failed[0].error_code, failed[0].message
        elif unavailable:
            status = "partial"
            error_code = "stages_not_available"
            error_message = "stages not available: " + ", ".join(n.value for n in unavailable)
        else:
            status = "succeeded"
        with session_scope(self._factory) as s:
            self._fence(s, claim)
            s.execute(
                update(rr)
                .where(rr.c.run_id == claim.run_id)
                .values(
                    status=status,
                    lease_owner=None,
                    lease_expires_at=None,
                    error_code=error_code,
                    error_message=error_message[:400] if error_message else None,
                    finished_at=_now(),
                )
            )

    # -- threads ----------------------------------------------------------------------------
    def start(self) -> None:
        if self._threads:
            return
        for i in range(self._settings.reconstruction_concurrency):
            thread = threading.Thread(
                target=self._loop, name=f"fieldlens-reconstruction-{i}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                handled = self.run_once()
            except Exception as exc:
                logger.error("reconstruction loop error: %s", type(exc).__name__)
                handled = False
            if not handled:
                self._stop.wait(self._settings.job_poll_seconds)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=15)
        self._threads = []

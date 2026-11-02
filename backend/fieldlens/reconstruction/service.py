"""Reconstruction-run service: estimate, separate confirm, cancel, retry and read models (TASK-068).

An estimate only reads stored exposure and the ledger: it queues and spends nothing. One confirm
covers the whole (bulk) estimate and queues one run per wellbore. The start gate is revalidated per
wellbore at estimate and again at confirm; a wellbore that is not ready, or whose records changed,
is rejected with the server's reason. A wellbore + source revision with a queued or running run
returns that run instead of starting a second one (idempotent start). Budget code is shared with
the TASK-054 processing runs: one lock, one ledger, one USD 5 cap. Every statement is project
qualified.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldlens.config import Settings
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.reconstruction import (
    ReconstructionEstimate,
    ReconstructionEstimateItem,
    ReconstructionEstimateRequest,
    ReconstructionRun,
    ReconstructionRunPage,
    ReconstructionRunStatus,
    ReconstructionStage,
    ReconstructionStageEstimate,
    ReconstructionStageKind,
    ReconstructionStageName,
    ReconstructionStageState,
    ReconstructionSummary,
)
from fieldlens.exposure import service as exposure_service
from fieldlens.identity import service as identity_service
from fieldlens.persistence import models as m
from fieldlens.processing.service import lock_budget, remaining_budget
from fieldlens.processing.steps import STUB_PRICING_SOURCE, quantize
from fieldlens.reconstruction import tables as t
from fieldlens.reconstruction.stages import StageExecutor, WellboreSnapshot, snapshot_of

re_, rr, rs = t.reconstruction_estimate, t.reconstruction_run, t.reconstruction_run_stage
ZERO = Decimal("0")
ACTIVE = ("queued", "running")
RETRYABLE = ("failed", "cancelled", "interrupted")
PRICING_LABEL = (
    "Stub planning rates (illustrative, not a provider price). No live model call is made; the "
    "agent stages are not available yet and spend nothing."
)


def _not_found(what: str) -> ContractError:
    return ContractError(ErrorCode.NOT_FOUND, f"{what} not found", 404)


def _conflict(message: str, reason: str, **details: Any) -> ContractError:
    return ContractError(ErrorCode.CONFLICT, message, 409, {"reason": reason, **details})


def _refused(message: str, refusals: list[dict[str, Any]]) -> ContractError:
    return ContractError(ErrorCode.VALIDATION_ERROR, message, 422, {"refusals": refusals})


def _gate_refusal(snap: WellboreSnapshot) -> dict[str, Any]:
    gate = snap.exposure.gate
    return {
        "wellbore_id": str(gate.wellbore_id),
        "wellbore_name": gate.wellbore_name,
        "reason": "not_ready",
        "gate_reasons": [{"code": r.code, "message": r.message} for r in gate.unmet],
    }


# -- selection ---------------------------------------------------------------------------------
def _snapshots(
    session: Session, project_id: UUID, request: ReconstructionEstimateRequest
) -> list[WellboreSnapshot]:
    """Snapshots of the selected wellbores; refuses unknown and not-ready ones (nothing created)."""
    identity_service.require_project(session, project_id)
    snaps: list[WellboreSnapshot] = []
    refusals: list[dict[str, Any]] = []
    if request.wellbore_ids is not None:
        for wellbore_id in request.wellbore_ids:
            row = session.execute(
                select(m.wellbore.c.well_id, m.wellbore.c.name).where(
                    m.wellbore.c.project_id == project_id, m.wellbore.c.wellbore_id == wellbore_id
                )
            ).first()
            if row is None:
                refusals.append({"wellbore_id": str(wellbore_id), "reason": "unknown_wellbore"})
                continue
            snap = snapshot_of(
                exposure_service.wellbore_exposure(
                    session, project_id, row.well_id, wellbore_id, row.name
                )
            )
            if not snap.ready:
                refusals.append(_gate_refusal(snap))
                continue
            snaps.append(snap)
    else:
        project = exposure_service.project_exposure(session, project_id)
        everyone = [snapshot_of(b) for w in project.wells for b in w.wellbores]
        snaps = [s for s in everyone if s.ready]
        if not snaps:
            raise _refused(
                "no wellbore passes the start gate; nothing was estimated",
                [
                    {
                        "reason": "no_ready_wellbores",
                        "gate_reasons": [
                            {"code": r.code, "message": r.message} for r in project.gate.unmet
                        ],
                    }
                ],
            )
    if refusals:
        raise _refused("some wellbores cannot be reconstructed; nothing was estimated", refusals)
    return snaps


def _active_run(session: Session, project_id: UUID, wellbore_id: UUID, revision: str) -> Any:
    return session.execute(
        select(rr.c.run_id, rr.c.status).where(
            rr.c.project_id == project_id,
            rr.c.wellbore_id == wellbore_id,
            rr.c.source_revision == revision,
            rr.c.status.in_(ACTIVE),
        )
    ).first()


def _stage_estimates(executors: Sequence[StageExecutor]) -> list[ReconstructionStageEstimate]:
    return [
        ReconstructionStageEstimate(
            stage=e.stage,
            kind=e.kind,
            availability="will_run" if e.available else "not_available",
            reason_code=None if e.available else e.reason_code,
            estimated_usd=quantize(e.estimated_usd) if e.available else ZERO,
            page_cap=e.page_cap,
        )
        for e in executors
    ]


# -- estimate ----------------------------------------------------------------------------------
def create_estimate(
    session: Session,
    settings: Settings,
    executors: Sequence[StageExecutor],
    project_id: UUID,
    request: ReconstructionEstimateRequest,
    retry_of: UUID | None = None,
) -> ReconstructionEstimate:
    snaps = _snapshots(session, project_id, request)
    lock_budget(session)
    stages = _stage_estimates(executors)
    per_wellbore = quantize(sum((s.estimated_usd for s in stages), ZERO))
    items: list[ReconstructionEstimateItem] = []
    new: list[WellboreSnapshot] = []
    for snap in snaps:
        active = _active_run(session, project_id, snap.exposure.wellbore_id, snap.source_revision)
        if active is not None:
            items.append(_item(snap, active.run_id, active.status, stages, ZERO, True))
        else:
            new.append(snap)
    remaining = remaining_budget(session, settings)
    total = quantize(per_wellbore * len(new))
    fits = total <= remaining
    estimate_id: UUID | None = None
    if new:
        estimate_id = session.execute(
            insert(re_)
            .values(
                project_id=project_id,
                total_estimated_usd=total,
                pricing_source=STUB_PRICING_SOURCE,
                total_cap_usd=settings.processing_total_cap_usd,
                remaining_budget_usd=remaining,
            )
            .returning(re_.c.estimate_id)
        ).scalar_one()
        for snap in new:
            exp = snap.exposure
            run_id: UUID = session.execute(
                insert(rr)
                .values(
                    project_id=project_id,
                    estimate_id=estimate_id,
                    well_id=exp.well_id,
                    wellbore_id=exp.wellbore_id,
                    wellbore_name=exp.wellbore_name,
                    status="estimated",
                    source_revision=snap.source_revision,
                    retry_of_run_id=retry_of,
                    pricing_source=STUB_PRICING_SOURCE,
                    estimated_usd=per_wellbore,
                )
                .returning(rr.c.run_id)
            ).scalar_one()
            for ordinal, e in enumerate(executors, start=1):
                session.execute(
                    insert(rs).values(
                        run_id=run_id,
                        stage=e.stage.value,
                        project_id=project_id,
                        ordinal=ordinal,
                        kind=e.kind.value,
                        state="pending" if e.available else "not_available",
                        reason_code=None if e.available else e.reason_code,
                        message=None if e.available else e.message,
                        estimated_usd=quantize(e.estimated_usd) if e.available else ZERO,
                    )
                )
            items.append(_item(snap, run_id, "estimated", stages, per_wellbore, False))
    items.sort(key=lambda i: (i.wellbore_name, str(i.wellbore_id)))
    return ReconstructionEstimate(
        estimate_id=estimate_id,
        project_id=project_id,
        items=items,
        total_estimated_usd=total,
        pricing_source=STUB_PRICING_SOURCE,
        pricing_label=PRICING_LABEL,
        total_cap_usd=settings.processing_total_cap_usd,
        remaining_budget_usd=remaining,
        fits_budget=fits,
        confirmable=bool(new) and fits,
    )


def _item(
    snap: WellboreSnapshot,
    run_id: UUID,
    status: str,
    stages: list[ReconstructionStageEstimate],
    usd: Decimal,
    already_active: bool,
) -> ReconstructionEstimateItem:
    return ReconstructionEstimateItem(
        wellbore_id=snap.exposure.wellbore_id,
        wellbore_name=snap.exposure.wellbore_name,
        already_active=already_active,
        run_id=run_id,
        run_status=ReconstructionRunStatus(status),
        source_revision=snap.source_revision,
        stages=stages,
        estimated_usd=usd,
    )


# -- confirm / cancel / retry -------------------------------------------------------------------
def _lock_run(session: Session, project_id: UUID, run_id: UUID) -> Any:
    row = session.execute(
        select(rr).where(rr.c.project_id == project_id, rr.c.run_id == run_id).with_for_update()
    ).first()
    if row is None:
        raise _not_found("reconstruction run")
    return row


def confirm_estimate(
    session: Session,
    settings: Settings,
    project_id: UUID,
    estimate_id: UUID,
    estimated_usd: Decimal,
) -> ReconstructionRunPage:
    try:
        if not estimated_usd.is_finite() or not Decimal(0) <= estimated_usd <= Decimal(1_000_000):
            raise InvalidOperation
        echoed = quantize(estimated_usd)
    except InvalidOperation:
        raise _conflict(
            "the confirmed amount is not a valid estimate", "estimate_mismatch"
        ) from None
    lock_budget(session)
    est = session.execute(
        select(re_)
        .where(re_.c.project_id == project_id, re_.c.estimate_id == estimate_id)
        .with_for_update()
    ).first()
    if est is None:
        raise _not_found("reconstruction estimate")
    if est.confirmed_at is not None:
        if est.confirmed_usd == echoed:
            return _runs_of_estimate(session, project_id, estimate_id)  # idempotent replay
        raise _conflict("this estimate was already confirmed", "not_estimated")
    if echoed != est.total_estimated_usd:
        raise _conflict(
            "the confirmed amount does not match the estimate",
            "estimate_mismatch",
            estimated_usd=str(est.total_estimated_usd),
        )
    runs = session.execute(
        select(rr)
        .where(
            rr.c.project_id == project_id,
            rr.c.estimate_id == estimate_id,
            rr.c.status == "estimated",
        )
        .order_by(rr.c.wellbore_name, rr.c.run_id)
        .with_for_update()
    ).all()
    if not runs:
        raise _conflict("nothing in this estimate can be started", "nothing_to_confirm")
    remaining = remaining_budget(session, settings)
    if est.total_estimated_usd > remaining:
        raise _conflict(
            "the estimate exceeds the remaining budget",
            "budget_exceeded",
            estimated_usd=str(est.total_estimated_usd),
            remaining_budget_usd=str(remaining),
        )
    stale: list[dict[str, Any]] = []
    for run in runs:  # the gate and the records are revalidated: the estimate may be old
        try:
            snap = snapshot_of(
                exposure_service.wellbore_exposure(
                    session, project_id, run.well_id, run.wellbore_id, run.wellbore_name
                )
            )
        except Exception:  # noqa: BLE001 - a vanished wellbore is a stale estimate
            stale.append({"wellbore_id": str(run.wellbore_id), "reason": "unknown_wellbore"})
            continue
        if not snap.ready:
            stale.append(_gate_refusal(snap))
        elif snap.source_revision != run.source_revision:
            stale.append(
                {
                    "wellbore_id": str(run.wellbore_id),
                    "wellbore_name": run.wellbore_name,
                    "reason": "source_revision_changed",
                }
            )
    if stale:
        raise _conflict(
            "the estimate is stale; estimate again. Nothing was started",
            "stale_estimate",
            refusals=stale,
        )
    for run in runs:
        if _start(session, run):
            continue
        session.execute(  # a duplicate start: this estimated run is superseded by the active one
            update(rs)
            .where(rs.c.run_id == run.run_id, rs.c.state == "pending")
            .values(state="skipped", reason_code="duplicate_active_run", finished_at=func.now())
        )
        session.execute(
            update(rr)
            .where(rr.c.run_id == run.run_id)
            .values(
                status="cancelled",
                error_code="duplicate_active_run",
                error_message="a run for this wellbore and source revision is already active",
                finished_at=func.now(),
            )
        )
    session.execute(
        update(re_)
        .where(re_.c.estimate_id == estimate_id)
        .values(confirmed_usd=est.total_estimated_usd, confirmed_at=func.now())
    )
    return _runs_of_estimate(session, project_id, estimate_id)


def _start(session: Session, run: Any) -> bool:
    """Queue an estimated run; False when the wellbore + revision already has an active run."""
    try:
        with session.begin_nested():
            session.execute(
                update(rr)
                .where(rr.c.run_id == run.run_id)
                .values(status="queued", confirmed_usd=run.estimated_usd, confirmed_at=func.now())
            )
    except IntegrityError:
        return False
    return True


def _runs_of_estimate(
    session: Session, project_id: UUID, estimate_id: UUID
) -> ReconstructionRunPage:
    rows = session.execute(
        select(rr)
        .where(rr.c.project_id == project_id, rr.c.estimate_id == estimate_id)
        .order_by(rr.c.wellbore_name, rr.c.run_id)
    ).all()
    out: list[ReconstructionRun] = []
    for row in rows:
        if row.status == "cancelled" and row.error_code == "duplicate_active_run":
            active = _active_run(session, project_id, row.wellbore_id, row.source_revision)
            if active is not None:  # idempotent start: hand back the run that is already active
                current = session.execute(select(rr).where(rr.c.run_id == active.run_id)).one()
                out.extend(_dtos(session, project_id, [current]))
                continue
        out.extend(_dtos(session, project_id, [row]))
    return ReconstructionRunPage(items=out, total=len(out))


def cancel_run(session: Session, project_id: UUID, run_id: UUID) -> ReconstructionRun:
    run = _lock_run(session, project_id, run_id)
    if run.status == "cancelled" or (run.status == "running" and run.cancel_requested):
        return _dtos(session, project_id, [run])[0]
    if run.status in ("estimated", "queued"):
        session.execute(
            update(rs)
            .where(rs.c.run_id == run_id, rs.c.state == "pending")
            .values(state="cancelled", reason_code="cancelled", finished_at=func.now())
        )
        session.execute(
            update(rr)
            .where(rr.c.run_id == run_id)
            .values(
                status="cancelled",
                cancel_requested=True,
                error_code="cancelled",
                error_message="cancelled by the user",
                finished_at=func.now(),
            )
        )
    elif run.status == "running":
        session.execute(update(rr).where(rr.c.run_id == run_id).values(cancel_requested=True))
    else:
        raise _conflict(f"run is already {run.status}", "not_cancellable")
    return get_run(session, project_id, run_id)


def retry_run(
    session: Session,
    settings: Settings,
    executors: Sequence[StageExecutor],
    project_id: UUID,
    run_id: UUID,
) -> ReconstructionEstimate:
    """A retry is a *new estimate* for the same wellbore; it queues and spends only after confirm."""
    run = _lock_run(session, project_id, run_id)
    if run.status not in RETRYABLE:
        reason = "stages_not_available" if run.status == "partial" else "not_retryable"
        raise _conflict(f"run is {run.status}; nothing to retry", reason)
    return create_estimate(
        session,
        settings,
        executors,
        project_id,
        ReconstructionEstimateRequest(wellbore_ids=[run.wellbore_id]),
        retry_of=run_id,
    )


# -- read models --------------------------------------------------------------------------------
def _dtos(session: Session, project_id: UUID, rows: Sequence[Any]) -> list[ReconstructionRun]:
    if not rows:
        return []
    stage_rows = session.execute(
        select(rs)
        .where(rs.c.project_id == project_id, rs.c.run_id.in_([r.run_id for r in rows]))
        .order_by(rs.c.run_id, rs.c.ordinal)
    ).all()
    by_run: dict[UUID, list[ReconstructionStage]] = {}
    for s in stage_rows:
        by_run.setdefault(s.run_id, []).append(
            ReconstructionStage(
                stage=ReconstructionStageName(s.stage),
                ordinal=s.ordinal,
                kind=ReconstructionStageKind(s.kind),
                state=ReconstructionStageState(s.state),
                reason_code=s.reason_code,
                message=s.message,
                counts={k: int(v) for k, v in (s.counts or {}).items()},
                input_tokens=s.input_tokens,
                output_tokens=s.output_tokens,
                actual_usd=s.actual_usd,
                error_code=s.error_code,
                started_at=s.started_at,
                finished_at=s.finished_at,
            )
        )
    return [
        ReconstructionRun(
            run_id=r.run_id,
            project_id=r.project_id,
            estimate_id=r.estimate_id,
            well_id=r.well_id,
            wellbore_id=r.wellbore_id,
            wellbore_name=r.wellbore_name,
            status=ReconstructionRunStatus(r.status),
            source_revision=r.source_revision,
            retry_of_run_id=r.retry_of_run_id,
            stages=by_run.get(r.run_id, []),
            pricing_source=r.pricing_source,
            estimated_usd=r.estimated_usd,
            confirmed_usd=r.confirmed_usd,
            actual_usd=r.actual_usd,
            cancel_requested=r.cancel_requested,
            retryable=r.status in RETRYABLE,
            error_code=r.error_code,
            error_message=r.error_message,
            summary=ReconstructionSummary.model_validate(r.summary) if r.summary else None,
            created_at=r.created_at,
            confirmed_at=r.confirmed_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
        )
        for r in rows
    ]


def get_run(session: Session, project_id: UUID, run_id: UUID) -> ReconstructionRun:
    row = session.execute(
        select(rr).where(rr.c.project_id == project_id, rr.c.run_id == run_id)
    ).first()
    if row is None:
        raise _not_found("reconstruction run")
    return _dtos(session, project_id, [row])[0]


def list_runs(
    session: Session,
    project_id: UUID,
    limit: int,
    wellbore_id: UUID | None = None,
) -> ReconstructionRunPage:
    identity_service.require_project(session, project_id)
    cond = [rr.c.project_id == project_id]
    if wellbore_id is not None:
        cond.append(rr.c.wellbore_id == wellbore_id)
    total = session.execute(select(func.count()).select_from(rr).where(*cond)).scalar_one()
    rows = session.execute(
        select(rr).where(*cond).order_by(rr.c.created_at.desc(), rr.c.run_id.desc()).limit(limit)
    ).all()
    return ReconstructionRunPage(items=_dtos(session, project_id, rows), total=total)

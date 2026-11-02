"""Reconstruction stages S1..S4: the executor interface and the deterministic S1/S4 (TASK-068).

``StageExecutor`` is the seam later tasks fill: TASK-055 provides S2 (label-driven extraction on the
TASK-036 harness, pages capped at 500) and a later task provides S3 (identity proposals). Until then
both are wired as :class:`NotAvailableExecutor` with a stable reason code, so a run is ``partial``
and never reads as success. S1 and S4 are pure functions of stored exposure/gate data: nothing here
calls a model, and no summary entry carries a value without a source reference.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.contracts.exposure import (
    CategoryExposure,
    ExposureFinding,
    WellboreExposure,
)
from fieldlens.contracts.reconstruction import (
    ReconstructionConflict,
    ReconstructionCoverage,
    ReconstructionEvidenceRef,
    ReconstructionStageKind,
    ReconstructionStageName,
    ReconstructionSummary,
    ReconstructionUnresolved,
)
from fieldlens.exposure import service as exposure_service
from fieldlens.identity import service as identity_service
from fieldlens.merge_proposals import tables as mp

NOT_AVAILABLE_REASON = "agent_step_not_implemented"
MAX_EVIDENCE_PER_CATEGORY = 5
MAX_UNRESOLVED = 200
ZERO = Decimal("0")

StageStateName = Literal["succeeded", "not_available", "failed"]
SURFACE_WARNING_CODES = ("SURFACE_LOCATION_MISSING", "SURFACE_LOCATION_INCOMPLETE")


class StageStop(Exception):
    """Raised from a checkpoint: the user cancelled the run; the stage stops, nothing is lost."""


@dataclass(frozen=True)
class WellboreSnapshot:
    exposure: WellboreExposure
    source_revision: str

    @property
    def ready(self) -> bool:
        return self.exposure.gate.trajectory_validated


def source_revision_of(exposure: WellboreExposure) -> str:
    """Digest of the wellbore's record groups: a different extraction/record set is a new one."""
    rows = sorted(
        [
            str(g.document_id),
            str(g.run_id),
            g.kind,
            g.record_count,
            sorted(g.validation_counts.items()),
        ]
        for c in exposure.categories
        for g in c.groups
    )
    raw = json.dumps([str(exposure.wellbore_id), rows], separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def snapshot_of(exposure: WellboreExposure) -> WellboreSnapshot:
    return WellboreSnapshot(exposure, source_revision_of(exposure))


@dataclass
class StageResult:
    state: StageStateName
    reason_code: str | None = None
    message: str | None = None
    counts: dict[str, int] = field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    usd: Decimal = ZERO
    error_code: str | None = None
    summary: ReconstructionSummary | None = None


@dataclass(frozen=True)
class StageContext:
    factory: sessionmaker[Session]
    settings: Settings
    project_id: UUID
    run_id: UUID
    well_id: UUID
    wellbore_id: UUID
    wellbore_name: str
    source_revision: str
    previous: dict[ReconstructionStageName, StageResult]
    checkpoint: Callable[[], None]
    """Refreshes the lease, verifies the fence and raises :class:`StageStop` on cancellation."""


class StageExecutor(Protocol):
    @property
    def stage(self) -> ReconstructionStageName: ...

    @property
    def kind(self) -> ReconstructionStageKind: ...

    @property
    def available(self) -> bool: ...

    @property
    def reason_code(self) -> str | None: ...

    @property
    def message(self) -> str | None: ...

    @property
    def estimated_usd(self) -> Decimal:
        """Planning rate reserved against the cap at confirm; zero when unavailable."""
        ...

    @property
    def page_cap(self) -> int | None:
        """S2 only: the page cap (500) bounding its future scope."""
        ...

    def run(self, ctx: StageContext) -> StageResult: ...


@dataclass(frozen=True)
class NotAvailableExecutor:
    """A stage whose agent step does not exist yet: it never runs and never spends."""

    stage: ReconstructionStageName
    kind: ReconstructionStageKind
    message: str
    reason_code: str | None = NOT_AVAILABLE_REASON
    page_cap: int | None = None
    available: bool = False
    estimated_usd: Decimal = ZERO

    def run(self, ctx: StageContext) -> StageResult:
        return StageResult("not_available", self.reason_code, self.message)


def default_executors(settings: Settings) -> list[StageExecutor]:
    return [
        GatherExecutor(),
        NotAvailableExecutor(
            ReconstructionStageName.EXTRACT,
            ReconstructionStageKind.AGENT,
            "Label-driven document extraction is not implemented yet (TASK-055); nothing was "
            "extracted from documents without a native parse.",
            page_cap=settings.processing_max_pages,
        ),
        NotAvailableExecutor(
            ReconstructionStageName.IDENTIFY,
            ReconstructionStageKind.AGENT,
            "Identity proposals for a wellbore run are not implemented yet; existing merge "
            "proposals are listed as unresolved, never accepted.",
        ),
        AssembleExecutor(),
    ]


def _pending_proposals(session: Session, project_id: UUID, wellbore_id: UUID) -> list[UUID]:
    p, member = mp.merge_proposal, mp.merge_proposal_member
    rows = session.execute(
        select(p.c.proposal_id)
        .join(member, member.c.proposal_id == p.c.proposal_id)
        .where(
            p.c.project_id == project_id,
            p.c.status == "pending",
            member.c.wellbore_id == wellbore_id,
        )
        .distinct()
        .order_by(p.c.proposal_id)
    ).all()
    return [r.proposal_id for r in rows]


class GatherExecutor:
    """S1: revalidate the start gate and the source revision; count what exists. Deterministic."""

    stage = ReconstructionStageName.GATHER
    kind = ReconstructionStageKind.DETERMINISTIC
    available = True
    reason_code: str | None = None
    message: str | None = None
    estimated_usd = ZERO
    page_cap: int | None = None

    def run(self, ctx: StageContext) -> StageResult:
        with ctx.factory() as session:
            exposure = exposure_service.one_wellbore(session, ctx.project_id, ctx.wellbore_id)
            listing = identity_service.listing(session, ctx.project_id)
            pending = _pending_proposals(session, ctx.project_id, ctx.wellbore_id)
        snap = snapshot_of(exposure)
        if not snap.ready:
            reasons = "; ".join(r.code for r in exposure.gate.unmet) or "NO_VALIDATED_TRAJECTORY"
            return StageResult(
                "failed",
                message=f"the start gate no longer holds for this wellbore ({reasons})",
                error_code="gate_no_longer_holds",
            )
        if snap.source_revision != ctx.source_revision:
            return StageResult(
                "failed",
                message="the wellbore's records changed after the estimate; estimate again",
                error_code="source_revision_changed",
            )
        groups = [g for c in exposure.categories for g in c.groups]
        sets = exposure.gate.trajectory_sets
        counts = {
            "categories_present": sum(1 for c in exposure.categories if c.present),
            "records": sum(c.record_count for c in exposure.categories),
            "documents": len({g.document_id for g in groups}),
            "trajectory_sets": len(sets),
            "trajectory_sets_validated": sum(1 for s in sets if s.validated),
            "unresolved_identity_records": listing.unresolved_record_count,
            "pending_merge_proposals": len(pending),
            "gate_warnings": len(exposure.gate.warnings),
        }
        return StageResult("succeeded", counts=counts)


def _refs(category: CategoryExposure) -> tuple[list[ReconstructionEvidenceRef], bool]:
    refs: list[ReconstructionEvidenceRef] = []
    for g in category.groups:
        locator = dict(g.sample[0].locator) if g.sample else {}
        refs.append(
            ReconstructionEvidenceRef(
                document_id=g.document_id,
                filename=g.filename,
                record_kind=g.kind,
                locator=locator,
            )
        )
    for prop in category.proposals:
        if prop.is_accepted_fact:
            refs.append(
                ReconstructionEvidenceRef(
                    document_id=prop.document_id,
                    record_kind=prop.attribute_kind,
                    locator=dict(prop.locator),
                )
            )
    return refs[:MAX_EVIDENCE_PER_CATEGORY], len(refs) > MAX_EVIDENCE_PER_CATEGORY


def _finding_refs(finding: ExposureFinding) -> list[ReconstructionEvidenceRef]:
    if finding.locators:
        return [
            ReconstructionEvidenceRef(
                document_id=finding.document_id,
                locator=dict(loc),
            )
            for loc in finding.locators
        ]
    return [ReconstructionEvidenceRef(document_id=finding.document_id, locator={})]


def build_summary(
    exposure: WellboreExposure,
    unresolved_identity: list[ReconstructionUnresolved],
    pending_proposals: list[UUID],
    previous: dict[ReconstructionStageName, StageResult],
    usd: Decimal,
) -> ReconstructionSummary:
    coverage: list[ReconstructionCoverage] = []
    conflicts: list[ReconstructionConflict] = []
    unresolved: list[ReconstructionUnresolved] = []
    for c in exposure.categories:
        refs, truncated = _refs(c)
        coverage.append(
            ReconstructionCoverage(
                category=c.category,
                present=c.present,
                record_count=c.record_count,
                conflicting_record_count=c.conflicting_record_count,
                accepted_candidate_count=c.accepted_proposal_count,
                open_candidate_count=max(c.proposal_total - c.accepted_proposal_count, 0),
                gap_reasons=list(c.gap_reasons),
                evidence=refs,
                evidence_truncated=truncated,
            )
        )
        for f in c.conflicts:
            conflicts.append(
                ReconstructionConflict(
                    category=c.category,
                    code=f.code,
                    severity=f.severity,
                    message=f.message,
                    evidence=_finding_refs(f),
                )
            )
        open_count = c.proposal_total - c.accepted_proposal_count
        if open_count > 0:
            unresolved.append(
                ReconstructionUnresolved(
                    kind="open_candidates",
                    code="OPEN_CANDIDATES",
                    message=f"{open_count} proposed {c.category} candidate(s) are not accepted "
                    "facts and are not part of this draft.",
                    count=open_count,
                    evidence=[
                        ReconstructionEvidenceRef(
                            document_id=p.document_id,
                            record_kind=p.attribute_kind,
                            locator=dict(p.locator),
                        )
                        for p in c.proposals
                        if not p.is_accepted_fact
                    ][:MAX_EVIDENCE_PER_CATEGORY],
                )
            )
    for w in exposure.gate.warnings:
        unresolved.append(
            ReconstructionUnresolved(
                kind="unlocated_surface" if w.code in SURFACE_WARNING_CODES else "warning",
                code=w.code,
                message=w.message,
            )
        )
    for proposal_id in pending_proposals:
        unresolved.append(
            ReconstructionUnresolved(
                kind="pending_merge_proposal",
                code="MERGE_PROPOSAL_PENDING",
                message="A merge proposal touching this wellbore awaits your review; it is not "
                "accepted and this draft does not apply it.",
                reference_id=proposal_id,
            )
        )
    unresolved.extend(unresolved_identity)
    states = {s: previous[s].state for s in previous}
    succeeded = [s for s in ReconstructionStageName if states.get(s) == "succeeded"]
    succeeded.append(ReconstructionStageName.ASSEMBLE)
    unavailable = [s for s in ReconstructionStageName if states.get(s) == "not_available"]
    failed = [s for s in ReconstructionStageName if states.get(s) == "failed"]
    note = (
        "Draft from stored, source-referenced records only. "
        + (
            "Stages not available: "
            + ", ".join(s.value for s in unavailable)
            + "; nothing was extracted or proposed by them. "
            if unavailable
            else ""
        )
        + "Nothing is published and no 3D scene is generated."
    )
    return ReconstructionSummary(
        wellbore_id=exposure.wellbore_id,
        wellbore_name=exposure.wellbore_name,
        stages_succeeded=succeeded,
        stages_not_available=unavailable,
        stages_failed=failed,
        coverage=coverage,
        unresolved=unresolved[:MAX_UNRESOLVED],
        conflicts=conflicts,
        actual_usd=usd,
        note=note,
    )


class AssembleExecutor:
    """S4: the draft summary from stored data: coverage, unresolved items and conflicts."""

    stage = ReconstructionStageName.ASSEMBLE
    kind = ReconstructionStageKind.DETERMINISTIC
    available = True
    reason_code: str | None = None
    message: str | None = None
    estimated_usd = ZERO
    page_cap: int | None = None

    def run(self, ctx: StageContext) -> StageResult:
        with ctx.factory() as session:
            exposure = exposure_service.one_wellbore(session, ctx.project_id, ctx.wellbore_id)
            listing = identity_service.listing(session, ctx.project_id)
            pending = _pending_proposals(session, ctx.project_id, ctx.wellbore_id)
        if source_revision_of(exposure) != ctx.source_revision:
            return StageResult(
                "failed",
                message="the wellbore's records changed during the run; estimate again",
                error_code="source_revision_changed",
            )
        unresolved_identity = [
            ReconstructionUnresolved(
                kind="unresolved_identity",
                code=u.reason,
                message=f"{u.record_count} record(s) in {u.document_count} document(s) have an "
                f"unresolved identity ({u.detail}); labels: {', '.join(u.labels)}.",
                scope="project",
                count=u.record_count,
            )
            for u in listing.unresolved
        ]
        usd = sum((r.usd for r in ctx.previous.values()), ZERO)
        summary = build_summary(exposure, unresolved_identity, pending, ctx.previous, usd)
        counts = {
            "categories": len(summary.coverage),
            "categories_present": sum(1 for c in summary.coverage if c.present),
            "evidence_refs": sum(len(c.evidence) for c in summary.coverage),
            "unresolved": len(summary.unresolved),
            "conflicts": len(summary.conflicts),
        }
        return StageResult("succeeded", counts=counts, summary=summary)

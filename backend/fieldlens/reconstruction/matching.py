"""S3 *Match wellbores* executor (TASK-076): proposes same-wellbore matches for user review.

Owner decision (2026-11-02, supersedes the auto-apply default): a merge is **never** applied here.
The stage runs the TASK-057 proposer (model step + deterministic guards G1..G7 + quote
verification), which stores ``pending`` or ``blocked`` proposals with alias quotes and guard
results. Only a user Accept in the merge review applies a revertible merge record. On the stub
provider (no proposer) the stage reports ``stubbed`` and proposes nothing.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldlens.contracts.reconstruction import ReconstructionStageKind, ReconstructionStageName
from fieldlens.merge_proposals import tables as mp
from fieldlens.merge_proposals.blocking import build_dataset
from fieldlens.merge_proposals.proposer import MergeProposer
from fieldlens.reconstruction.stages import StageContext, StagePlan, StageResult

STUB_REASON = "stub_provider"
ZERO = Decimal("0")


def _count(session: Session, project_id: UUID, statuses: tuple[str, ...]) -> int:
    p = mp.merge_proposal
    return int(
        session.execute(
            select(func.count())
            .select_from(p)
            .where(p.c.project_id == project_id, p.c.status.in_(statuses))
        ).scalar_one()
    )


class MatchWellboresExecutor:
    stage = ReconstructionStageName.IDENTIFY
    kind = ReconstructionStageKind.AGENT
    title = "Match wellbores"
    description = (
        "Looks for names that denote the same wellbore (for example 15/9-F-12 and F-12) and "
        "proposes matches for you to review, each with a quote from the source. Nothing is "
        "merged until you accept it, and an accepted match can be reverted."
    )
    reason_code: str | None = None
    message: str | None = None
    page_cap: int | None = None

    def __init__(self, proposer: MergeProposer | None) -> None:
        self._proposer = proposer

    @property
    def available(self) -> bool:
        return True

    @property
    def estimated_usd(self) -> Decimal:
        return ZERO

    def plan(self, session: Session, project_id: UUID) -> StagePlan:
        decided = _count(session, project_id, ("pending", "accepted", "blocked"))
        if self._proposer is None:
            blocks = len(build_dataset(session, project_id).blocks)
            return StagePlan(
                "stub",
                new_work=blocks,
                reused=decided,
                unit="name groups",
                note="Stub provider: no model is called, so no matches are proposed."
                if blocks
                else "No wellbore names need matching.",
            )
        est = self._proposer.estimate(project_id)
        return StagePlan(
            "will_run",
            new_work=est.blocks,
            reused=decided,
            unit="name groups",
            usd=est.upper_bound_usd,
            note=None if est.blocks else "No wellbore names need matching.",
        )

    def run(self, ctx: StageContext) -> StageResult:
        if self._proposer is None:
            with ctx.factory() as session:
                blocks = len(build_dataset(session, ctx.project_id).blocks)
            return StageResult(
                "stubbed",
                STUB_REASON,
                "Stub run: no model was called; no wellbore matches were proposed.",
                counts={"name_groups": blocks},
            )
        ctx.checkpoint()
        run = self._proposer.run(ctx.project_id)
        with ctx.factory() as session:
            pending = _count(session, ctx.project_id, ("pending",))
            blocked = _count(session, ctx.project_id, ("blocked",))
        counts = {
            "name_groups": run.blocks,
            "deferred": run.deferred_blocks,
            "proposed": run.proposals_created,
            "dropped": run.proposals_dropped,
            "awaiting_review": pending,
            "blocked": blocked,
        }
        usd = run.cost_usd or ZERO
        tokens_in, tokens_out = run.input_tokens or 0, run.output_tokens or 0
        if run.state in ("failed", "partial"):
            return StageResult(
                "failed",
                message=f"matching stopped: {run.reason or 'provider failure'}; "
                "proposals already stored are kept",
                error_code=(run.reason or "provider_failure")[:48],
                counts=counts,
                usd=usd,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                fatal=False,
            )
        message = (
            f"{run.proposals_created} match(es) proposed for you to review"
            if run.proposals_created
            else "no new matches to propose"
        )
        return StageResult(
            "succeeded",
            message=message,
            counts=counts,
            usd=usd,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
        )

"""S5 *Design 3D asset* executor (TASK-079): one labelled, visual-only 3D model per wellbore.

A run belongs to one wellbore (a bulk estimate queues one run per merged wellbore), so this stage
designs ``ctx.wellbore_id`` only. A user-confirmed run is the authorization: the estimate is shown
for information and no spend gate applies here. Without a model (or on the stub provider) the stage
is ``stubbed`` and stores nothing; with one, the latest valid spec becomes the current one and the
earlier ones stay as history. A failed design leaves the current 3D model untouched.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldlens.assetspec.live_designer import LiveDesigner
from fieldlens.candidates.tables import extraction_candidate as c
from fieldlens.contracts.reconstruction import ReconstructionStageKind, ReconstructionStageName
from fieldlens.reconstruction.matching import _StageCancel
from fieldlens.reconstruction.stages import StageContext, StagePlan, StageResult, StageStop

STUB_REASON = "stub_provider"
ZERO = Decimal("0")


class DesignAssetExecutor:
    stage = ReconstructionStageName.DESIGN
    kind = ReconstructionStageKind.AGENT
    title = "Design 3D asset"
    description = (
        "Builds a labelled 3D illustration of each wellbore (casing, tubing, packers, pumps, "
        "valves, wellhead and surface facilities) from its equipment records. It is visual only: "
        "no engineering numbers come from it. It may look up public pictures of named equipment, "
        "within fixed limits; the latest 3D model replaces the previous one, which stays in history."
    )
    message: str | None = None
    page_cap: int | None = None

    def __init__(self, designer: LiveDesigner | None) -> None:
        self._designer = designer

    @property
    def reason_code(self) -> str | None:
        return STUB_REASON if self._designer is None else None

    @property
    def available(self) -> bool:
        return True

    @property
    def estimated_usd(self) -> Decimal:
        return ZERO

    @staticmethod
    def _wellbores(session: Session, project_id: UUID) -> list[UUID]:
        return list(
            session.execute(
                select(c.c.wellbore_id)
                .where(
                    c.c.project_id == project_id,
                    c.c.wellbore_id.is_not(None),
                    c.c.state != "rejected",
                    c.c.attributes["kind"].astext == "equipment",
                )
                .distinct()
            ).scalars()
        )

    def plan(self, session: Session, project_id: UUID) -> StagePlan:
        wellbores = self._wellbores(session, project_id)
        if self._designer is None:
            return StagePlan(
                "stub",
                new_work=len(wellbores),
                unit="wellbores",
                note="Not available: no model configured, so no 3D model is designed.",
            )
        research = (
            " Public pictures of named equipment may be looked up."
            if self._designer.research_enabled
            else ""
        )
        return StagePlan(
            "will_run",
            new_work=len(wellbores),
            unit="wellbores",
            usd=self._designer.estimate_usd(session, project_id, wellbores),
            note=(
                "A new 3D model replaces the current one; the previous one stays in history."
                if wellbores
                else "No equipment records to design from."
            )
            + research,
        )

    def run(self, ctx: StageContext) -> StageResult:
        if self._designer is None:
            return StageResult(
                "stubbed",
                STUB_REASON,
                "Not available: no model configured. Stub run: no 3D model was designed.",
            )
        ctx.checkpoint()
        outcome = self._designer.design(
            ctx.project_id, ctx.wellbore_id, str(ctx.run_id), _StageCancel(ctx.checkpoint)
        )
        if outcome.cancelled:
            raise StageStop("cancelled by the user")
        ctx.checkpoint()
        common = {
            "counts": outcome.counts,
            "usd": outcome.usd,
            "input_tokens": outcome.input_tokens,
            "output_tokens": outcome.output_tokens,
        }
        if not outcome.ok:
            return StageResult(
                "failed",
                message=outcome.message,
                error_code=(outcome.reason or "design_failed")[:48],
                fatal=False,
                **common,  # type: ignore[arg-type]
            )
        return StageResult("succeeded", message=outcome.message, **common)  # type: ignore[arg-type]

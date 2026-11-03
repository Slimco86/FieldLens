"""S5 *Design 3D asset* executor (TASK-079): one labelled, visual-only 3D model per wellbore.

A run belongs to one wellbore (a bulk estimate queues one run per merged wellbore), so this stage
designs ``ctx.wellbore_id`` only. A user-confirmed run is the authorization: the estimate is shown
for information and no spend gate applies here. The input is the union of the wellbore's structured
records (converted deterministically, no model call) and its model-read equipment items (F2). Without
a model the spec is still built and stored from them; with one, the model is called only when there
are model-read items to label. The latest valid spec becomes the current one (an unchanged spec makes
no new revision) and earlier ones stay as history. A failed design leaves the current 3D model
untouched. "No equipment data" is reported only when both sources are empty.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldlens.assetspec.live_designer import NO_DATA, LiveDesigner, design_without_model
from fieldlens.assetspec.structured import wellbores_with_structured
from fieldlens.assetspec.sweep import wellbore_documents
from fieldlens.candidates.tables import extraction_candidate as c
from fieldlens.contracts.reconstruction import ReconstructionStageKind, ReconstructionStageName
from fieldlens.persistence import models as m
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

    def _wellbores(self, session: Session, project_id: UUID) -> list[UUID]:
        model_read = set(
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
        found = model_read | set(wellbores_with_structured(session, project_id))
        if self._designer is not None and self._designer.has_sweeper:  # F2b: documents count too
            for wb in session.execute(
                select(m.wellbore.c.wellbore_id).where(m.wellbore.c.project_id == project_id)
            ).scalars():
                if wb not in found and wellbore_documents(session, project_id, wb):
                    found.add(wb)
        return sorted(found, key=str)

    def plan(self, session: Session, project_id: UUID) -> StagePlan:
        wellbores = self._wellbores(session, project_id)
        if self._designer is None:
            if not wellbores:
                return StagePlan(
                    "stub",
                    new_work=0,
                    unit="wellbores",
                    note="No equipment records to design from.",
                )
            return StagePlan(
                "will_run",
                new_work=len(wellbores),
                unit="wellbores",
                note=(
                    "No model configured: the 3D model is built from structured records "
                    "without a model call; model-read items are used unlabelled."
                ),
            )
        research = (
            " Public pictures of named equipment may be looked up."
            if self._designer.research_enabled
            else ""
        )
        sweep = self._designer.sweep_estimate(session, project_id, wellbores)
        usd = self._designer.label_estimate_usd(session, project_id, wellbores)
        sweep_note = ""
        if sweep is not None:
            usd += sweep.usd
            sweep_note = (
                f" Equipment sweep: {sweep.documents} document(s), {sweep.pages} page(s) to read, "
                f"{sweep.reused_pages} already read (estimate for information only)."
            )
        return StagePlan(
            "will_run",
            new_work=len(wellbores),
            reused=sweep.reused_pages if sweep is not None else 0,
            unit="wellbores",
            usd=usd,
            note=(
                "A new 3D model replaces the current one; the previous one stays in history."
                if wellbores
                else "No equipment records to design from."
            )
            + sweep_note
            + research,
        )

    def run(self, ctx: StageContext) -> StageResult:
        ctx.checkpoint()
        if self._designer is None:
            outcome = design_without_model(
                ctx.factory, ctx.project_id, ctx.wellbore_id, str(ctx.run_id)
            )
            if outcome.ok and outcome.message == NO_DATA:  # nothing to build and no model
                return StageResult(
                    "stubbed",
                    STUB_REASON,
                    "No equipment data for this wellbore; nothing to design (no model configured).",
                    counts=outcome.counts,
                )
        else:
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

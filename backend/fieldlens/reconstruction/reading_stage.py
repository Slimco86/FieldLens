"""S2 *Read documents* executor (TASK-076): reuse stored model reads, read only what is new."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from fieldlens.contracts.reconstruction import ReconstructionStageKind, ReconstructionStageName
from fieldlens.reconstruction.reading import (
    DocumentReader,
    ReadFailure,
    ReadScope,
    read_scope,
)
from fieldlens.reconstruction.stages import StageContext, StagePlan, StageResult

MAX_DOCUMENTS_PER_RUN = 25
STUB_REASON = "stub_provider"
ZERO = Decimal("0")


class ReadDocumentsExecutor:
    stage = ReconstructionStageName.EXTRACT
    kind = ReconstructionStageKind.AGENT
    title = "Read documents"
    description = (
        "Asks the model to read PDFs that have no automatic parser (category, tags and the "
        "wellbore names written in them, each with a quote). Documents already read are reused "
        "and never read again. What the model returns stays an unverified proposal."
    )
    reason_code: str | None = None
    message: str | None = None

    def __init__(
        self,
        reader: DocumentReader | None,
        model_pages: int,
        scope: Callable[[Session, UUID], ReadScope] = read_scope,
    ) -> None:
        self._reader = reader
        self._pages = model_pages
        self._scope = scope

    @property
    def available(self) -> bool:
        return True

    @property
    def page_cap(self) -> int | None:
        return self._pages

    @property
    def estimated_usd(self) -> Decimal:
        return ZERO

    @property
    def live(self) -> bool:
        return self._reader is not None and self._reader.live

    def plan(self, session: Session, project_id: UUID) -> StagePlan:
        scope = self._scope(session, project_id)
        n = min(len(scope.to_read), MAX_DOCUMENTS_PER_RUN)
        if not self.live:
            return StagePlan(
                "stub",
                new_work=0 if not scope.to_read else len(scope.to_read),
                reused=scope.reused,
                unit="documents",
                note="Stub provider: no model is called, so nothing is read."
                if scope.to_read
                else "No documents need reading.",
            )
        assert self._reader is not None
        if not scope.to_read:
            return StagePlan(
                reused=scope.reused, unit="documents", note="No documents need reading."
            )
        return StagePlan(
            "will_run",
            new_work=n,
            reused=scope.reused,
            unit="documents",
            usd=self._reader.usd_per_document * n,
            note=None
            if len(scope.to_read) <= n
            else f"{len(scope.to_read) - n} more are left for a later run.",
        )

    def run(self, ctx: StageContext) -> StageResult:
        with ctx.factory() as session:
            scope = self._scope(session, ctx.project_id)
        counts = {"to_read": len(scope.to_read), "reused": scope.reused, "read": 0}
        if not scope.to_read:
            return StageResult("succeeded", counts=counts, message="no documents need reading")
        if not self.live or self._reader is None:
            return StageResult(
                "stubbed",
                STUB_REASON,
                f"Stub run: no model was called; {len(scope.to_read)} document(s) were not read.",
                counts=counts,
            )
        batch = scope.to_read[:MAX_DOCUMENTS_PER_RUN]
        counts["deferred"] = len(scope.to_read) - len(batch)
        usd = ZERO
        for target in batch:
            ctx.checkpoint()
            try:
                outcome = self._reader.read(ctx.project_id, target, ctx.checkpoint)
            except ReadFailure as exc:
                return StageResult(
                    "failed",
                    message=f"{target.filename}: {exc.message}; earlier reads are kept",
                    error_code=exc.code[:48],
                    counts=counts,
                    usd=usd,
                    fatal=False,
                )
            counts["read"] += 1
            usd += outcome.usd
        return StageResult("succeeded", counts=counts, usd=usd)

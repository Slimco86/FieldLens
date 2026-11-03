"""S5 equipment sweep (spec §16 F2b): read the wellbore's own documents for equipment.

For every document linked to the wellbore that has not yet been read at its current source revision,
equipment prompt and model, run the EXISTING candidates harness (unit kind ``equipment``: page
selection, validators, text-match evidence). Results are normal reviewable ``extraction_candidate``
rows; the harness caches every page unit, so an unchanged document costs no second call. Documents
classified as completion/equipment come first, then the wellbore's other PDFs. A native parser
covering one file never excuses another. Bounds: documents per wellbore, pages per document, model
calls, wall time and cancellation. There is no USD limit (a confirmed run is the authorization).
A failed, truncated or refused document is reported per document and never blocks the rest;
truncation is retried once with a larger output bound. Nothing here is engineering: the output is
candidates for the visual designer only."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.provider import CancelToken
from fieldlens.candidates.equipment import EquipmentExtractor, check_document_scope
from fieldlens.candidates.equipment_prompt import EQUIPMENT_QUESTION
from fieldlens.candidates.harness import ExtractionHarness, UnitRequest
from fieldlens.candidates.sources import SourceError
from fieldlens.candidates.tables import extraction_candidate as cand
from fieldlens.identity.tables import record_wellbore_link
from fieldlens.persistence import models as m
from fieldlens.processing.tables import document_identity_proposal as dip
from fieldlens.processing.tables import document_model_result as dmr

log = logging.getLogger(__name__)

NOT_AVAILABLE = "Not available: no model configured"
EQUIPMENT_CATEGORY = "completion_equipment"
_PROMPT_OVERHEAD_TOKENS = 1500


@dataclass(frozen=True)
class SweepLimits:
    max_documents: int = 12
    max_pages_per_document: int = 12
    max_calls: int = 80
    wall_s: float = 900.0
    retry_output_tokens: int = 16384  # one retry of a truncated page with this output bound


@dataclass(frozen=True)
class SweepDoc:
    document_id: UUID
    revision_id: UUID
    name: str
    category: str | None

    @property
    def rank(self) -> int:
        return 0 if self.category == EQUIPMENT_CATEGORY else 1


@dataclass
class DocResult:
    document_id: UUID
    name: str
    state: str  # read | reused | failed | excluded | skipped
    reason: str | None = None
    pages: int = 0
    pages_failed: int = 0
    calls: int = 0


@dataclass
class SweepReport:
    available: bool = True
    note: str | None = None
    docs: list[DocResult] = field(default_factory=list)
    considered: int = 0
    not_swept: int = 0  # over the document or wall-time bound
    cancelled: bool = False
    usd: Decimal = Decimal(0)
    input_tokens: int = 0
    output_tokens: int = 0

    def count(self, state: str) -> int:
        return sum(1 for d in self.docs if d.state == state)

    @property
    def calls(self) -> int:
        return sum(d.calls for d in self.docs)

    def counts(self) -> dict[str, int]:
        return {
            "sweep_documents": self.considered,
            "sweep_read": self.count("read"),
            "sweep_reused": self.count("reused"),
            "sweep_failed": self.count("failed"),
            "sweep_excluded": self.count("excluded"),
            "sweep_skipped": self.count("skipped"),
            "sweep_not_swept": self.not_swept,
            "sweep_calls": self.calls,
        }

    def message(self) -> str:
        if not self.available:
            return f"Equipment sweep: {self.note or NOT_AVAILABLE}"
        if not self.docs and not self.not_swept:
            return "Equipment sweep: no linked documents to read"
        text = (
            f"Equipment sweep: read {self.count('read')} of {self.considered} document(s), "
            f"{self.count('reused')} reused, {self.count('failed')} failed"
        )
        if self.count("excluded"):
            text += f", {self.count('excluded')} excluded"
        if self.not_swept:
            text += f", {self.not_swept} not swept (bound reached)"
        failed = [f"{d.name}: {d.reason}" for d in self.docs if d.state == "failed"]
        if failed:
            text += " (" + "; ".join(failed[:3]) + ")"
        if self.cancelled:
            text += "; cancelled"
        return text


@dataclass
class SweepEstimate:
    documents: int = 0
    pages: int = 0
    reused_pages: int = 0
    usd: Decimal = Decimal(0)


HarnessFor = Callable[[int | None], ExtractionHarness]
"""Builds the equipment harness; the argument is an output-token bound override (None = default)."""


def wellbore_documents(session: Session, project_id: UUID, wellbore_id: UUID) -> list[SweepDoc]:
    """Documents linked to the wellbore by native records, model-read candidates or identity
    proposals, in the sweep order (completion/equipment first, then name, for determinism)."""
    ru, er, lk = m.extraction_run, m.extracted_record, record_wellbore_link
    ids: set[UUID] = set(
        session.execute(
            select(ru.c.document_id)
            .join(er, er.c.run_id == ru.c.run_id)
            .join(lk, (lk.c.run_id == er.c.run_id) & (lk.c.ordinal == er.c.ordinal))
            .where(lk.c.project_id == project_id, lk.c.wellbore_id == wellbore_id)
            .distinct()
        ).scalars()
    )
    ids |= set(
        session.execute(
            select(cand.c.document_id)
            .where(cand.c.project_id == project_id, cand.c.wellbore_id == wellbore_id)
            .distinct()
        ).scalars()
    )
    wb = m.wellbore
    ids |= set(
        session.execute(
            select(dip.c.document_id)
            .join(
                wb,
                (wb.c.project_id == dip.c.project_id) & (wb.c.wellbore_key == dip.c.normalized_key),
            )
            .where(dip.c.project_id == project_id, wb.c.wellbore_id == wellbore_id)
            .distinct()
        ).scalars()
    )
    if not ids:
        return []
    sd, srd, rev = m.source_document, m.source_revision_document, m.source_revision
    revision_of: dict[UUID, UUID] = {}
    for row in session.execute(
        select(srd.c.document_id, srd.c.source_revision_id)
        .join(rev, rev.c.source_revision_id == srd.c.source_revision_id)
        .where(srd.c.project_id == project_id, srd.c.document_id.in_(ids))
        .order_by(rev.c.created_at.asc(), srd.c.source_revision_id.asc())
    ):
        revision_of[row.document_id] = row.source_revision_id  # newest revision wins
    names = {
        r.document_id: r.original_filename
        for r in session.execute(
            select(sd.c.document_id, sd.c.original_filename).where(
                sd.c.project_id == project_id, sd.c.document_id.in_(ids)
            )
        )
    }
    category: dict[UUID, str] = {}
    for row in session.execute(
        select(dmr.c.document_id, dmr.c.category)
        .where(dmr.c.project_id == project_id, dmr.c.document_id.in_(ids))
        .order_by(dmr.c.created_at.asc(), dmr.c.result_id.asc())
    ):
        category[row.document_id] = row.category  # latest classification wins
    docs = [
        SweepDoc(d, revision_of[d], names.get(d, str(d)), category.get(d))
        for d in ids
        if d in revision_of
    ]
    return sorted(docs, key=lambda d: (d.rank, d.name, str(d.document_id)))


def _subject(session: Session, project_id: UUID, wellbore_id: UUID) -> str | None:
    wb = m.wellbore
    return session.execute(
        select(wb.c.name).where(wb.c.project_id == project_id, wb.c.wellbore_id == wellbore_id)
    ).scalar_one_or_none()


class EquipmentSweeper:
    def __init__(
        self,
        factory: sessionmaker[Session],
        harness_for: HarnessFor,
        limits: SweepLimits | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._factory = factory
        self._harness_for = harness_for
        self.limits = limits or SweepLimits()
        self._clock = clock

    # -- estimate (information only; no call, no spend) -----------------------------------------
    def estimate(
        self, session: Session, project_id: UUID, wellbore_ids: list[UUID]
    ) -> SweepEstimate:
        est = SweepEstimate()
        harness = self._harness_for(None)
        extractor = EquipmentExtractor(harness)
        pricing = harness.config.pricing
        cap = harness.config.equipment_max_output_tokens
        seen: set[UUID] = set()
        for wb in wellbore_ids:
            subject = _subject(session, project_id, wb)
            for d in wellbore_documents(session, project_id, wb)[: self.limits.max_documents]:
                if d.document_id in seen:
                    continue
                seen.add(d.document_id)
                try:
                    doc = harness.reader.require(project_id, d.revision_id, d.document_id)
                    if doc.kind != "pdf":
                        continue
                    sel = extractor.select_pages(
                        project_id,
                        d.revision_id,
                        d.document_id,
                        max_pages=self.limits.max_pages_per_document,
                    )
                except SourceError:
                    continue
                est.documents += 1
                for page in sel.pages[: self.limits.max_pages_per_document]:
                    req = UnitRequest(
                        project_id,
                        d.revision_id,
                        d.document_id,
                        EQUIPMENT_QUESTION,
                        "equipment",
                        page=page,
                        rotation=sel.rotations.get(page),
                        document_subject=subject,
                    )
                    if self._cached(session, project_id, harness.unit_key(req, doc)):
                        est.reused_pages += 1
                        continue
                    est.pages += 1
                    try:
                        chars = len(harness.reader.read_page(doc, page).text)
                    except SourceError:
                        chars = 0
                    tokens_in = chars // 3 + harness.config.equipment_image_token_bound
                    tokens_in += _PROMPT_OVERHEAD_TOKENS
                    est.usd += (
                        Decimal(tokens_in) * pricing.input_usd_per_mtok
                        + Decimal(cap) * pricing.output_usd_per_mtok
                    ) / Decimal(1_000_000)
        return est

    @staticmethod
    def _cached(session: Session, project_id: UUID, key: str) -> bool:
        t = m.agent_work_unit
        state = session.execute(
            select(t.c.state).where(t.c.project_id == project_id, t.c.unit_key == key)
        ).scalar_one_or_none()
        return state in ("succeeded", "failed", "cancelled")

    # -- the sweep -------------------------------------------------------------------------------
    def sweep(
        self, project_id: UUID, wellbore_id: UUID, cancel: CancelToken | None = None
    ) -> SweepReport:
        cancel = cancel or CancelToken()
        report = SweepReport()
        with self._factory() as s:
            docs = wellbore_documents(s, project_id, wellbore_id)
            subject = _subject(s, project_id, wellbore_id)
        report.considered = len(docs)
        started = self._clock()
        calls = 0
        for index, d in enumerate(docs):
            if cancel.cancelled:
                report.cancelled = True
                report.not_swept += len(docs) - index
                break
            if (
                index >= self.limits.max_documents
                or calls >= self.limits.max_calls
                or self._clock() - started >= self.limits.wall_s
            ):
                report.not_swept += len(docs) - index
                break
            result = self._one(
                project_id, d, subject, cancel, self.limits.max_calls - calls, report
            )
            calls += result.calls
            report.docs.append(result)
            if cancel.cancelled:
                report.cancelled = True
                report.not_swept += len(docs) - index - 1
                break
        return report

    def _one(
        self,
        project_id: UUID,
        d: SweepDoc,
        subject: str | None,
        cancel: CancelToken,
        calls_left: int,
        report: SweepReport,
    ) -> DocResult:
        out = DocResult(d.document_id, d.name, "failed")
        try:
            harness = self._harness_for(None)
            doc = harness.reader.require(project_id, d.revision_id, d.document_id)
            if doc.kind != "pdf":
                out.state, out.reason = "skipped", "not a PDF page document"
                return out
            scope = check_document_scope(harness, doc, subject)
            if scope.excluded:
                code = scope.code or "document_excluded"
                harness.record_exclusion(
                    project_id,
                    d.revision_id,
                    d.document_id,
                    EQUIPMENT_QUESTION,
                    code,
                    f"{code}: {scope.detail}",
                )
                out.state, out.reason = "excluded", scope.detail[:120]
                return out
            extractor = EquipmentExtractor(harness)
            sel = extractor.select_pages(
                project_id,
                d.revision_id,
                d.document_id,
                max_pages=min(self.limits.max_pages_per_document, max(calls_left, 1)),
            )
            summary = harness.run_document(
                project_id,
                d.revision_id,
                d.document_id,
                EQUIPMENT_QUESTION,
                kind="equipment",
                pages=sel.pages,
                rotations=sel.rotations,
                cancel=cancel,
                document_subject=subject,
            )
            outcomes = list(summary.pages)
            truncated = [o.page for o in outcomes if o.stop_reason == "output_truncated" and o.page]
            if truncated and not cancel.cancelled:  # one retry with a larger output bound
                retry = self._harness_for(self.limits.retry_output_tokens).run_document(
                    project_id,
                    d.revision_id,
                    d.document_id,
                    EQUIPMENT_QUESTION,
                    kind="equipment",
                    pages=truncated,
                    rotations={p: r for p, r in sel.rotations.items() if p in truncated},
                    cancel=cancel,
                    document_subject=subject,
                )
                by_page = {o.page: o for o in retry.pages}
                outcomes = [by_page.get(o.page, o) if o.page in truncated else o for o in outcomes]
            out.pages = len(outcomes)
            out.pages_failed = sum(1 for o in outcomes if o.state != "succeeded")
            out.calls = sum(o.provider_calls for o in outcomes)
            report.usd += sum((o.cost_usd for o in outcomes if not o.cache_hit), Decimal(0))
            report.input_tokens += sum(o.input_tokens for o in outcomes if not o.cache_hit)
            report.output_tokens += sum(o.output_tokens for o in outcomes if not o.cache_hit)
            if not outcomes:
                out.reason = "no equipment pages selected"
            elif cancel.cancelled:
                out.state, out.reason = "failed", "cancelled"
            elif out.pages_failed:
                reasons = sorted(
                    {o.stop_reason or o.state for o in outcomes if o.state != "succeeded"}
                )
                out.reason = ", ".join(reasons)[:120]
                out.state = "failed"
            elif all(o.cache_hit for o in outcomes):
                out.state = "reused"
            else:
                out.state = "read"
        except SourceError as exc:
            out.state, out.reason = "failed", exc.code
        except Exception as exc:  # noqa: BLE001 - one document never stops the sweep
            log.warning("equipment sweep document failed: %s", type(exc).__name__)
            out.state, out.reason = "failed", type(exc).__name__
        return out


def build_sweeper(
    processing: Any, factory: sessionmaker[Session], store: Any, settings: Any
) -> EquipmentSweeper | None:
    """Sweeper on the live Meta context (same provider, ledger period and owner rates);
    ``None`` without a live runtime."""
    from fieldlens.candidates.harness import HarnessConfig
    from fieldlens.candidates.sources import SourceReader

    meta = getattr(processing, "meta", None)
    if processing is None or meta is None:
        return None
    reader = SourceReader(factory, store, meta.renderer)

    def harness_for(output_tokens: int | None) -> ExtractionHarness:
        extra: dict[str, Any] = {}
        if output_tokens is not None:
            extra["equipment_max_output_tokens"] = output_tokens
        config = HarnessConfig(
            model=settings.meta_model,
            pricing=meta.rates,
            pricing_id=meta.pricing_id,
            period_id=meta.period_id,
            effort="low",
            **extra,
        )
        return ExtractionHarness(
            factory=factory,
            reader=reader,
            ledger=meta.ledger,
            provider=meta.provider,
            config=config,
        )

    return EquipmentSweeper(factory, harness_for)

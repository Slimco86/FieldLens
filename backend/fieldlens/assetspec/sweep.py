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

from fieldlens.assistant.messages import Effort
from fieldlens.assistant.provider import CancelToken
from fieldlens.candidates.equipment import EquipmentExtractor, check_document_scope
from fieldlens.candidates.equipment_prompt import EQUIPMENT_QUESTION
from fieldlens.candidates.harness import ExtractionHarness, UnitOutcome, UnitRequest
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
    retry_effort: Effort = "minimal"  # one retry of a truncated page (output cap stays <= 8192)


@dataclass(frozen=True)
class SweepDoc:
    document_id: UUID
    revision_id: UUID
    name: str
    category: str | None
    profile: str | None = None

    @property
    def not_equipment(self) -> bool:
        if self.category == EQUIPMENT_CATEGORY:
            return False
        if self.category in SKIP_CATEGORIES:
            return True
        prof = (self.profile or "").casefold()
        return any(w in prof for w in SKIP_PROFILE_WORDS)

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
        if self.count("skipped"):
            text += f", {self.count('skipped')} skipped (not equipment documents)"
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
    failed_pages: int = 0
    skipped: int = 0  # documents that are not equipment documents
    usd: Decimal = Decimal(0)


HarnessFor = Callable[[Effort | None], ExtractionHarness]
"""Builds the equipment harness; the argument is an effort override (None = the default, low)."""

# Not an equipment document: survey/trajectory/production/log classes and parser profiles.
SKIP_CATEGORIES = frozenset(
    {"trajectory", "production_injection", "well_logs", "terrain_bathymetry"}
)
SKIP_PROFILE_WORDS = ("survey", "trajectory", "production", "log")
SKIP_REASON = "skipped: not an equipment document"
# A cached failure with one of these reasons says nothing about the page: it is read again.
TRANSIENT_REASONS = frozenset(
    {
        "provider_unavailable",
        "budget_exhausted",
        "unit_error",
        "cancelled",
        "request_cancelled",
        "provider_timeout",
        "timeout",
        "rate_limited",
        "provider_auth",
    }
)


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
            .where(
                dip.c.project_id == project_id,
                wb.c.wellbore_id == wellbore_id,
                dip.c.read_mode == "text",  # TASK-115: an image-read identity never links by itself
            )
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
    profile: dict[UUID, str] = {
        r.document_id: r.profile_name
        for r in session.execute(
            select(ru.c.document_id, ru.c.profile_name).where(
                ru.c.project_id == project_id,
                ru.c.document_id.in_(ids),
                ru.c.superseded.is_(False),
                ru.c.profile_name.is_not(None),
            )
        )
    }
    docs = [
        SweepDoc(d, revision_of[d], names.get(d, str(d)), category.get(d), profile.get(d))
        for d in ids
        if d in revision_of
    ]
    return sorted(docs, key=lambda d: (d.rank, d.name, str(d.document_id)))


def _page_request(
    project_id: UUID, d: SweepDoc, page: int, rotations: dict[int, int], subject: str | None
) -> UnitRequest:
    return UnitRequest(
        project_id,
        d.revision_id,
        d.document_id,
        EQUIPMENT_QUESTION,
        "equipment",
        page=page,
        rotation=rotations.get(page),
        document_subject=subject,
    )


def unit_status(session: Session, project_id: UUID, key: str) -> tuple[str, int]:
    """State of a page unit and the retry number to use: ``done``, ``failed`` (deterministic: a
    refusal, a rejected or truncated reply; stays cached), ``transient`` (provider/budget/cancel:
    read again as retry N+1) or ``new``."""
    t = m.agent_work_unit
    rows = session.execute(
        select(t.c.unit_key, t.c.state, t.c.stop_reason).where(
            t.c.project_id == project_id, t.c.unit_key.like(f"{key}%")
        )
    ).all()
    latest: tuple[int, str, str | None] | None = None
    for r in rows:
        suffix = r.unit_key[len(key) :]
        if suffix == "":
            n = 0
        elif suffix.startswith(":r") and suffix[2:].isdigit():
            n = int(suffix[2:])
        else:
            continue
        if latest is None or n > latest[0]:
            latest = (n, r.state, r.stop_reason)
    if latest is None:
        return "new", 0
    n, state, reason = latest
    if state == "succeeded":
        return "done", n
    if state in ("failed", "cancelled"):
        transient = state == "cancelled" or (reason or "") in TRANSIENT_REASONS
        transient = transient or (reason or "").startswith("limit_")
        return ("transient", n + 1) if transient else ("failed", n)
    return "new", n  # running / interrupted: the same unit resumes


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
                if d.not_equipment:
                    est.skipped += 1
                    continue
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
                    req = _page_request(project_id, d, page, sel.rotations, subject)
                    status, _ = unit_status(session, project_id, harness.unit_key(req, doc))
                    if status == "done":
                        est.reused_pages += 1
                        continue
                    if (
                        status == "failed"
                    ):  # a stored deterministic failure: neither read nor reused
                        est.failed_pages += 1
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
        swept = 0
        for index, d in enumerate(docs):
            if cancel.cancelled:
                report.cancelled = True
                report.not_swept += len(docs) - index
                break
            if d.not_equipment:  # survey/trajectory/production/log: no page is read
                report.docs.append(DocResult(d.document_id, d.name, "skipped", SKIP_REASON))
                continue
            if (
                swept >= self.limits.max_documents
                or calls >= self.limits.max_calls
                or self._clock() - started >= self.limits.wall_s
            ):
                report.not_swept += len(docs) - index
                break
            result = self._one(
                project_id, d, subject, cancel, self.limits.max_calls - calls, report
            )
            swept += 1
            calls += result.calls
            report.docs.append(result)
            if cancel.cancelled:
                report.cancelled = True
                report.not_swept += len(docs) - index - 1
                break
        return report

    def _run(
        self,
        harness: ExtractionHarness,
        project_id: UUID,
        d: SweepDoc,
        pages: list[int],
        rotations: dict[int, int],
        subject: str | None,
        cancel: CancelToken,
        retries: dict[int, int] | None = None,
    ) -> list[UnitOutcome]:
        summary = harness.run_document(
            project_id,
            d.revision_id,
            d.document_id,
            EQUIPMENT_QUESTION,
            kind="equipment",
            pages=pages,
            rotations={p: r for p, r in rotations.items() if p in pages},
            cancel=cancel,
            document_subject=subject,
            retries=retries,
        )
        return list(summary.pages)

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
            sel = EquipmentExtractor(harness).select_pages(
                project_id,
                d.revision_id,
                d.document_id,
                max_pages=min(self.limits.max_pages_per_document, max(calls_left, 1)),
            )
            retries: dict[int, int] = {}
            with self._factory() as s:  # a cached transient failure is read again, not reused
                for page in sel.pages:
                    req = _page_request(project_id, d, page, sel.rotations, subject)
                    status, number = unit_status(s, project_id, harness.unit_key(req, doc))
                    if status == "transient":
                        retries[page] = number
            first = self._run(
                harness, project_id, d, sel.pages, sel.rotations, subject, cancel, retries
            )
            used = sum(o.provider_calls for o in first)
            outcomes = list(first)
            truncated = [o.page for o in first if o.stop_reason == "output_truncated" and o.page]
            room = max(calls_left - used, 0)
            if truncated and room and not cancel.cancelled:
                # one retry at lower effort inside the same output cap (the request contract
                # allows at most 8192 output tokens)
                again = self._run(
                    self._harness_for(self.limits.retry_effort),
                    project_id,
                    d,
                    truncated[:room],
                    sel.rotations,
                    subject,
                    cancel,
                )
                by_page = {o.page: o for o in again}
                outcomes = [by_page.get(o.page, o) for o in first]
                outcomes += [o for o in again if o.page not in {x.page for x in first}]
                used += sum(o.provider_calls for o in again)
            billed = [*first, *(again if truncated and room and not cancel.cancelled else [])]
            out.calls = used
            report.usd += sum((o.cost_usd for o in billed if not o.cache_hit), Decimal(0))
            report.input_tokens += sum(o.input_tokens for o in billed if not o.cache_hit)
            report.output_tokens += sum(o.output_tokens for o in billed if not o.cache_hit)
            out.pages = len(outcomes)
            out.pages_failed = sum(1 for o in outcomes if o.state != "succeeded")
            if not outcomes:
                out.reason = "no equipment pages selected"
            elif cancel.cancelled:
                out.state, out.reason = "failed", "cancelled"
            elif out.pages_failed:
                bad = [o for o in outcomes if o.state != "succeeded"]
                out.reason = "; ".join(f"p{o.page}: {o.stop_reason or o.state}" for o in bad[:4])[
                    :160
                ]
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
    """Sweeper on the live Meta context (same provider, ledger period, owner rates and provider
    settings); ``None`` without a live runtime. The sweep adds no USD gate of its own: only the
    ledger's own refusals (period cap, confirmed balance, per-unit reserve) can stop a page, and
    such a page is reported and read again next time."""
    from fieldlens.assistant.runner import RequestLimits
    from fieldlens.candidates.harness import HarnessConfig
    from fieldlens.candidates.sources import SourceReader

    meta = getattr(processing, "meta", None)
    if processing is None or meta is None:
        return None
    reader = SourceReader(factory, store, meta.renderer)
    limits = RequestLimits(
        max_attempts=settings.provider_max_attempts,
        max_tool_calls=settings.provider_max_tool_calls,
        deadline_s=settings.provider_deadline_s,
        max_output_tokens=settings.provider_max_output_tokens,
        max_reserved_usd=settings.provider_max_reserved_usd,
        image_token_bound=settings.provider_image_token_bound,
    )

    def harness_for(effort: Effort | None) -> ExtractionHarness:
        config = HarnessConfig(
            model=settings.meta_model,
            pricing=meta.rates,
            pricing_id=meta.pricing_id,
            period_id=meta.period_id,
            limits=limits,
            effort=effort or "low",
        )
        return ExtractionHarness(
            factory=factory,
            reader=reader,
            ledger=meta.ledger,
            provider=meta.provider,
            config=config,
        )

    return EquipmentSweeper(factory, harness_for)

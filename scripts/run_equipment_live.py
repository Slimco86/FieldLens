"""EQ-11 live runbook: equipment candidates on the approved F-14/F-5 pages (opt-in, spends credit).

NOT run by the TASK-041 implementer. Three steps; only the last one spends credit.

1. Put the two PDFs into a throwaway LANE project (read-only local files, nothing leaves the
   machine; no provider is constructed; the lane database must already be migrated):

       uv run python scripts/run_equipment_live.py --bootstrap-project "task-041 live" \
           --pdf <root>/Well_logs_pr_WELL/15_9-F-14/14.DIV.REPORTS/FWR_Completion_F14.pdf \
           --pdf <root>/Well_logs_pr_WELL/15_9-F-5/14.DIV.REPORTS/COMPLETION_REPORT_1.PDF

   Add ``--file PATH`` (repeatable) to upload native files too, so that deterministic wellbore
   identities exist and candidates can attach: the Volve perforation table
   ``Geophysical_Interpretations/Wells/Well_perforations_Volve.dat`` names 15/9-F-14 and 15/9-F-5
   (add ``Well_picks_Volve_v1.dat`` for more records). The helper runs the application in-process
   against the configured lane database and storage, uploads, drives the ingestion jobs (identity
   resolves after extraction), and prints the project id, the resolved wellbore identities and one
   ``--document`` line per document (the well label after the colon is YOUR statement of which
   well the file is about; it must resolve to one of those identities).

2. Dry run (the default whenever ``--allow-live`` is absent; no provider, no network). It prints the
   exact plan: documents by content hash, pages, rotations, effort, concurrency, image size, the
   number of provider calls and the worst-case reservation total at the placeholder rates versus
   the cap, and refuses when the worst case exceeds the cap:

       uv run python scripts/run_equipment_live.py --project-id <uuid> --spend-cap-usd 3 \
           --document <doc_uuid>:15/9-F-14 --document <doc_uuid>:15/9-F-5 [--include-controls]

   A retry of only some pages: ``--only-failed`` (planned pages whose last read in this project did
   not succeed) or ``--pages <doc_uuid>=30,36`` (a subset of the planned pages; nothing outside the
   plan can be added). The plan also shows what the cap's budget period has already committed and
   refuses when the worst case exceeds what remains.

3. The live run needs ALL of ``--allow-live``, a positive ``--spend-cap-usd`` and the owner's
   ``FIELDLENS_LIVE_META=1``. The provider key reaches the process ONLY through the environment as
   ``MODEL_API_KEY``, injected by the owner/orchestrator at invocation, e.g.

       MODEL_API_KEY=... FIELDLENS_LIVE_META=1 uv run python scripts/run_equipment_live.py \
           --allow-live --spend-cap-usd 3 --project-id <uuid> --document ... [--report PATH]

   It is read only through the existing adapter configuration (``Settings`` -> ``MetaProvider``) and
   is never printed, logged or written. The budget period is named after the cap
   (``task-041-live-cap-<cap>``) and the run refuses if a period of that name has another cap; the
   report states the cap actually enforced. Harness limits: effort ``low``, page concurrency 3,
   image 1600 px. Each ``--document`` must be a document of the project whose content hash matches
   a configured page plan (nothing else is sent). The comparison against
   ``scripts/spikes/spike042_gold.py`` is against an AGENT-READ reference that is NOT human
   verified; model-read results are never described as verified. The report is written only after
   a live run, never by a refused run or a dry run.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "spikes"))

from spike042_gold import CONTROLS, GOLD  # noqa: E402
from sqlalchemy import create_engine, select, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from fieldlens.assistant.budget import BudgetLedger  # noqa: E402
from fieldlens.assistant.errors import ReservationStateError  # noqa: E402
from fieldlens.assistant.meta import MetaProvider  # noqa: E402
from fieldlens.assistant.provider import Pricing, Provider  # noqa: E402
from fieldlens.assistant.runner import RequestLimits  # noqa: E402
from fieldlens.candidates.equipment import (  # noqa: E402
    DEFAULT_PLANS,
    EquipmentExtractor,
    EquipmentRunResult,
    PagePlan,
    find_plan,
)
from fieldlens.candidates.harness import (  # noqa: E402
    EQUIPMENT_UNIT_RESERVE_USD,
    ExtractionHarness,
    HarnessConfig,
)  # noqa: E402
from fieldlens.candidates.pages import PageRenderer  # noqa: E402
from fieldlens.candidates.sources import SourceReader  # noqa: E402
from fieldlens.config import Settings  # noqa: E402
from fieldlens.evidence.storage import BlobStore  # noqa: E402
from fieldlens.persistence import models as m  # noqa: E402
from fieldlens.persistence.session import create_session_factory  # noqa: E402

OPT_IN_VAR = "FIELDLENS_LIVE_META"
PERIOD_PREFIX = "task-041-live-cap-"
PAGE_RESERVE_USD = EQUIPMENT_UNIT_RESERVE_USD  # one 8,192-token attempt bounds to ~USD 0.24
LONG_SIDE = 1600
CONCURRENCY = 3
MAX_CAP_USD = Decimal("25")
RATES = (Decimal("5.00"), Decimal("25.00"))  # conservative placeholder, not provider rates
PRICING_REVISION = "mi6-conservative-placeholder-1"
DEFAULT_REPORT = ROOT / "docs" / "evidence" / "TASK041_EQUIPMENT_LIVE_RUN.md"

# TASK-042 reference groups -> EQ-8 categories (visual level)
CATEGORY_OF_GROUP = {
    "casing": "casing",
    "liner": "liner",
    "tubing": "tubing",
    "pup_joint": "tubing",
    "packer": "packer",
    "plug": "isolation",
    "pump": "pump",
    "bearing": "bearing",
}


def category_of(group: str) -> str:
    return CATEGORY_OF_GROUP.get(group, "completion_accessory")


class RunbookRefusal(Exception):
    """A clean refusal (printed, exit 2); never a stack trace."""


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"not a number: {value[:20]!r}") from None


def refusal(args: argparse.Namespace, env: dict[str, str]) -> str | None:
    """Why a LIVE run must not start (None when every explicit gate is present)."""
    if not args.allow_live:
        return "refusing: --allow-live is required (this run spends credit)"
    cap = args.spend_cap_usd
    if cap is None or not cap.is_finite() or cap <= 0:
        return "refusing: --spend-cap-usd must be a positive amount"
    if args.spend_cap_usd > MAX_CAP_USD:
        return f"refusing: --spend-cap-usd above the runbook bound of {MAX_CAP_USD}"
    if env.get(OPT_IN_VAR) != "1":
        return f"refusing: {OPT_IN_VAR}=1 must be set in the environment by the owner"
    if not args.document:
        return "refusing: at least one --document <uuid>:<well label> is required"
    return None


@dataclass
class PageRecord:
    pv: str | None
    page: int
    state: str
    latency_s: float
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    items: list[dict[str, Any]] = field(default_factory=list)
    control: bool = False


def _nums(value: str | None) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", value or "")]


def _close(a: float, b: float, tol: float) -> bool:
    return abs(a - b) <= tol * max(abs(a), abs(b), 1e-9)


def compare_page(pv: str, page: int, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Category and rough size agreement of one page's items with the agent-read reference.

    ``items`` are candidate ``attributes`` dicts. Category agreement is the share of reference
    items covered per category (multiset overlap); size agreement is the share of reference items
    with a printed depth or OD that some same-category candidate matches within 1 percent
    (depth) or 3 percent (OD). The reference is not human verified, so these are rough."""
    key = f"{pv}:{page}"
    if key in CONTROLS:
        return {"key": key, "control": True, "reference_items": 0, "read_items": len(items)}
    gold = GOLD.get(key)
    if gold is None:
        return {"key": key, "reference": False, "read_items": len(items)}
    sure = [g for g in gold["items"] if not g["unsure"]]
    want = Counter(category_of(g["group"]) for g in sure)
    perf = len(gold["perforations"])
    if perf:
        want["perforation_interval"] += perf
    got = Counter(i["category"] for i in items)
    covered = sum(min(n, got[c]) for c, n in want.items())
    total = sum(want.values())
    sized = hit = 0
    for g in sure:
        depth = _nums(g["attrs"].get("depth"))
        od = _nums(g["attrs"].get("od"))
        if not depth and not od:
            continue
        sized += 1
        cat = category_of(g["group"])
        for i in items:
            if i["category"] != cat:
                continue
            read_depths = [
                x
                for f in ("top_depth", "bottom_depth")
                for x in _nums((i.get(f) or {}).get("value_text"))
            ]
            read_od = _nums((i.get("od") or {}).get("value_text"))
            if (depth and any(_close(depth[0], r, 0.01) for r in read_depths)) or (
                od and any(_close(od[0], r, 0.03) for r in read_od)
            ):
                hit += 1
                break
    return {
        "key": key,
        "reference_items": total,
        "read_items": len(items),
        "category_agreement": round(covered / total, 2) if total else None,
        "sized_reference_items": sized,
        "size_matches": hit,
        "by_category_reference": dict(want),
        "by_category_read": dict(got),
    }


def render_report(
    records: list[PageRecord],
    comparisons: list[dict[str, Any]],
    *,
    cap: Decimal,
    committed: Decimal,
    model: str,
    effort: str,
    wall_s: float,
    notes: list[str],
    live: bool = True,
) -> str:
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = [
        "# TASK-041 EQ-11: live equipment-candidate run (reported, not gated)",
        "",
        f"Run {when}. Class: {'LIVE' if live else 'OFFLINE STUB (not a live result)'} "
        f"(`{model}`, effort `{effort}`, page concurrency 3, upright 1600 px).",
        "Values are model-read and UNVERIFIED; they are never accepted, never used in calculations and the",
        "reference below is an AGENT-READ reference (TASK-042), NOT human verified. Agreement figures are rough.",
        "",
        f"Spend cap USD {cap}; committed USD {committed} (placeholder rates, not provider rates); "
        f"wall {wall_s:.1f} s.",
        "",
        "| Doc | Page | State | Items | Latency s | In tok | Out tok | Cost USD |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in records:
        out.append(
            f"| {r.pv or '?'}{' (control)' if r.control else ''} | {r.page} | {r.state} | "
            f"{len(r.items)} | {r.latency_s:.1f} | {r.input_tokens} | {r.output_tokens} | "
            f"{r.cost_usd} |"
        )
    out += ["", "## Agreement with the agent-read reference (rough)", ""]
    for c in comparisons:
        if c.get("control"):
            out.append(f"- {c['key']}: control page, {c['read_items']} item(s) read (expected 0)")
        elif c.get("reference") is False:
            out.append(f"- {c['key']}: no reference entry, {c['read_items']} item(s) read")
        else:
            out.append(
                f"- {c['key']}: category agreement {c['category_agreement']} "
                f"({c['read_items']} read / {c['reference_items']} reference); "
                f"size matches {c['size_matches']}/{c['sized_reference_items']}"
            )
    out += ["", "## Notes", "", *[f"- {n}" for n in notes], ""]
    return "\n".join(out)


def collect(
    factory: sessionmaker[Session],
    result: EquipmentRunResult,
    pv: str | None,
    controls: set[int],
) -> list[PageRecord]:
    if result.summary is None:
        return []
    records: list[PageRecord] = []
    for o in result.summary.pages:
        items: list[dict[str, Any]] = []
        if o.unit_id.int:
            with factory() as s:
                rows = s.execute(
                    text(
                        "select attributes from extraction_candidate where unit_id = :u "
                        "and attributes->>'kind' = 'equipment' order by ordinal"
                    ),
                    {"u": o.unit_id},
                ).all()
            items = [dict(r[0]) for r in rows]
        records.append(
            PageRecord(
                pv,
                o.page or 0,
                o.state,
                o.elapsed_s,
                o.input_tokens,
                o.output_tokens,
                o.cost_usd,
                items,
                (o.page or 0) in controls,
            )
        )
    return records


def run(
    *,
    factory: sessionmaker[Session],
    provider: Provider,
    store: BlobStore,
    project_id: UUID,
    documents: list[tuple[UUID, str]],
    cap: Decimal,
    include_controls: bool,
    model: str,
    report_path: Path | None,
    revision_id: UUID | None = None,
    effort: str = "low",
    plans: tuple[PagePlan, ...] = DEFAULT_PLANS,
    only_pages: dict[UUID, list[int]] | None = None,
) -> tuple[str, list[PageRecord], list[dict[str, Any]]]:
    if not cap.is_finite() or cap <= 0:
        raise RunbookRefusal("the cap must be a positive amount")
    ledger = BudgetLedger(factory)
    period = ledger.ensure_period(
        f"{PERIOD_PREFIX}{cap.normalize():f}",
        ledger_cap_usd=cap,
        warn_usd=cap,
        unattended_block_usd=cap,
    )
    try:
        ledger.confirm_balance(period, cap, "TASK-041 owner allowance (runbook argument)")
    except ReservationStateError:
        pass  # already confirmed on an earlier run of this period
    enforced = ledger.status(period).cap_usd
    if enforced != cap:  # an old period of this name keeps its old cap: never silently reuse it
        raise RunbookRefusal(f"budget period cap is USD {enforced}, not the requested USD {cap}")
    pricing = Pricing(PRICING_REVISION, model, RATES[0], RATES[1])
    pricing_id = ledger.register_pricing(pricing, "MI-6 conservative placeholder, not rates")
    reader = SourceReader(factory, store, PageRenderer(store))
    harness = ExtractionHarness(
        factory=factory,
        reader=reader,
        ledger=ledger,
        provider=provider,
        config=HarnessConfig(
            model=model,
            pricing=pricing,
            pricing_id=pricing_id,
            period_id=period,
            limits=RequestLimits(retry_backoff_s=2.0),
            effort="low",
            page_reserve_usd=PAGE_RESERVE_USD,
            long_side=LONG_SIDE,
            read_concurrency=CONCURRENCY,
        ),
    )
    extractor = EquipmentExtractor(harness, plans=plans)
    with factory() as s:
        rev = (
            revision_id
            or s.execute(
                select(m.project.c.latest_source_revision_id).where(
                    m.project.c.project_id == project_id
                )
            ).scalar_one()
        )
    records: list[PageRecord] = []
    comparisons: list[dict[str, Any]] = []
    notes: list[str] = [
        "model-read and unverified; documents named only by their project document ids",
        "control pages are included only with --include-controls",
    ]
    started = time.monotonic()
    for document_id, label in documents:
        doc = reader.require(project_id, rev, document_id)
        plan = find_plan(doc, None, plans)
        if plan is None:
            notes.append(f"document {document_id}: no configured page plan, skipped (nothing sent)")
            continue
        pv_match = re.search(r"\((PV-\d+)\)", plan.label)
        pv = pv_match.group(1) if pv_match else None
        result = extractor.run_document(
            project_id,
            rev,
            document_id,
            subject_label=label,
            include_controls=include_controls,
            only_pages=(only_pages or {}).get(document_id),
        )
        if result.excluded:
            notes.append(f"{plan.label}: excluded ({result.exclusion_code})")
            continue
        recs = collect(factory, result, pv, set(plan.controls))
        records += recs
        if pv:
            comparisons += [compare_page(pv, r.page, r.items) for r in recs]
        if result.summary is not None and result.summary.state != "succeeded":
            notes.append(
                f"{plan.label}: run {result.summary.state} ({result.summary.stop_reason}); "
                "partial coverage, not complete"
            )
    status = ledger.status(period)
    report = render_report(
        records,
        comparisons,
        cap=status.cap_usd,
        committed=status.committed_usd,
        model=model,
        effort=effort,
        wall_s=time.monotonic() - started,
        notes=notes,
        live=provider.name == "meta",
    )
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report, encoding="utf-8")
    return report, records, comparisons


@dataclass
class PlanEntry:
    document_id: UUID
    filename: str | None
    sha256: str | None
    plan_label: str | None
    pages: list[int]
    rotations: dict[int, int]
    note: str


@dataclass
class Plan:
    entries: list[PlanEntry]
    pages: int
    provider_calls_expected: int
    provider_calls_max: int
    worst_case_usd: Decimal
    cap: Decimal | None
    text: str
    available_usd: Decimal | None = None  # the cap less what the period already committed

    @property
    def over_cap(self) -> bool:
        limit = self.available_usd if self.available_usd is not None else self.cap
        return limit is not None and self.worst_case_usd > limit


def build_plan(
    factory: sessionmaker[Session],
    project_id: UUID,
    revision_id: UUID | None,
    documents: list[tuple[UUID, str]],
    *,
    include_controls: bool,
    cap: Decimal | None,
    plans: tuple[PagePlan, ...] = DEFAULT_PLANS,
    effort: str = "low",
    only_pages: dict[UUID, list[int]] | None = None,
    only_failed: bool = False,
) -> Plan:
    """The exact plan, from the database and the page plans only (no provider, no network)."""
    limits = RequestLimits()
    entries: list[PlanEntry] = []
    with factory() as s:
        rev = (
            revision_id
            or s.execute(
                select(m.project.c.latest_source_revision_id).where(
                    m.project.c.project_id == project_id
                )
            ).scalar_one()
        )
        for document_id, label in documents:
            row = s.execute(
                select(m.source_document.c.sha256, m.source_document.c.original_filename)
                .join(
                    m.source_revision_document,
                    (m.source_revision_document.c.project_id == m.source_document.c.project_id)
                    & (m.source_revision_document.c.document_id == m.source_document.c.document_id),
                )
                .where(
                    m.source_document.c.project_id == project_id,
                    m.source_document.c.document_id == document_id,
                    m.source_revision_document.c.source_revision_id == rev,
                )
            ).first()
            if row is None:
                entries.append(PlanEntry(document_id, None, None, None, [], {}, "not in project"))
                continue
            match = next((p for p in plans if p.sha256 == row.sha256), None)
            if match is None or not (match.pages or include_controls and match.controls):
                entries.append(
                    PlanEntry(
                        document_id,
                        row.original_filename,
                        row.sha256,
                        None,
                        [],
                        {},
                        "no configured page plan: skipped, nothing is sent",
                    )
                )
                continue
            pages = list(
                dict.fromkeys([*match.pages, *(match.controls if include_controls else ())])
            )
            note_extra = ""
            if only_failed:
                bad = failed_pages(s, project_id, document_id)
                pages = [p for p in pages if p in bad]
                note_extra = f"; only pages whose last read failed: {sorted(bad)}"
            if only_pages is not None and document_id in only_pages:
                pages = [p for p in pages if p in set(only_pages[document_id])]
                note_extra += f"; restricted to {only_pages[document_id]}"
            entries.append(
                PlanEntry(
                    document_id,
                    row.original_filename,
                    row.sha256,
                    match.label,
                    pages,
                    {p: r for p, r in match.rotations if p in pages},
                    f"subject label given by the caller: {label or '(none)'}{note_extra}",
                )
            )
    total = sum(len(e.pages) for e in entries)
    worst = PAGE_RESERVE_USD * total
    available = _available(factory, cap)
    attempt_bound = (
        Decimal(HarnessConfig.equipment_image_token_bound + 2000) * RATES[0]
        + Decimal(HarnessConfig.equipment_max_output_tokens) * RATES[1]
    ) / Decimal(1_000_000)
    limit = available if available is not None else cap
    lines = [
        f"DRY RUN plan (no provider constructed, no network). effort={effort} "
        f"concurrency={CONCURRENCY} image_long_side={LONG_SIDE}px",
    ]
    for e in entries:
        lines.append(
            f"- document {e.document_id} file={e.filename} sha256={e.sha256} plan={e.plan_label} "
            f"pages={e.pages} rotations={e.rotations or '{}'} ({e.note})"
        )
    lines += [
        f"pages: {total}; provider calls: {total} expected (1 per page, no tools; a retry only "
        f"after a transient provider error, at most {limits.max_attempts} attempts each, hard max "
        f"{total * limits.max_attempts})",
        f"per page: one turn, max {HarnessConfig.equipment_max_output_tokens} output tokens; "
        f"one-attempt upper bound ~USD {attempt_bound:.3f} <= reservation USD {PAGE_RESERVE_USD}",
        f"worst-case reservation total: {total} x USD {PAGE_RESERVE_USD} = USD {worst} "
        f"at placeholder rates {RATES[0]}/{RATES[1]} USD per Mtok (not provider rates)",
        f"cap: {('USD ' + str(cap)) if cap is not None else 'none given'}"
        + (
            f"; still available in this cap's budget period: USD {available}"
            if available is not None and available != cap
            else ""
        ),
        (
            "verdict: EXCEEDS THE CAP (or what remains of it), refusing"
            if limit is not None and worst > limit
            else "verdict: within the cap"
        ),
    ]
    return Plan(
        entries, total, total, total * limits.max_attempts, worst, cap, "\n".join(lines), available
    )


def _available(factory: sessionmaker[Session], cap: Decimal | None) -> Decimal | None:
    """The cap less what this cap's budget period has already committed (None without a cap)."""
    if cap is None or not cap.is_finite() or cap <= 0:
        return None
    with factory() as s:
        row = s.execute(
            text("select period_id from budget_period where name = :n"),
            {"n": f"{PERIOD_PREFIX}{cap.normalize():f}"},
        ).first()
    if row is None:
        return cap
    return min(cap, BudgetLedger(factory).status(row[0]).available_usd)


def failed_pages(s: Session, project_id: UUID, document_id: UUID) -> set[int]:
    """Pages whose last equipment read did not succeed (a unit that fetched the page image and
    ended failed/interrupted, with no later succeeded unit for the same page)."""
    rows = s.execute(
        text(
            "select coalesce(g.detail->>'page', g.detail->'args'->>'page') as page, u.state "
            "from agent_work_unit u "
            "join agent_step g on g.unit_id = u.unit_id and g.tool_name = 'get_page_image' "
            "where u.project_id = :p and u.unit_key like 'extract:%' "
            "and g.detail->'args'->>'document_id' = :d order by u.created_at"
        ),
        {"p": project_id, "d": str(document_id)},
    ).all()
    last: dict[int, str] = {}
    for page, state in rows:
        if page is not None and str(page).isdigit():  # a refused image keeps its page in args
            last[int(page)] = state
    return {p for p, st in last.items() if st != "succeeded"}


def bootstrap_project(
    client: Any,
    headers: dict[str, str],
    worker: Any,
    name: str,
    pdfs: list[Path],
    files: list[Path] | None = None,
) -> tuple[str, str, dict[str, str]]:
    """Create a project, upload local PDFs (read-only), drive the ingestion jobs to idle.
    Returns (project_id, revision_id, {document_id: filename}). No provider is involved."""
    created = client.post("/api/v1/projects", json={"name": name}, headers=headers)
    created.raise_for_status()
    pid = str(created.json()["project_id"])
    import json as _json

    natives = files or []
    meta: dict[str, Any] = {
        "expected_parent_source_revision_id": None,
        "files": [{} for _ in [*pdfs, *natives]],
    }
    parts: list[Any] = [("metadata", (None, _json.dumps(meta).encode(), "application/json"))]
    parts += [("files", (p.name, p.read_bytes(), "application/pdf")) for p in pdfs]
    parts += [("files", (p.name, p.read_bytes(), "application/octet-stream")) for p in natives]
    up = client.post(f"/api/v1/projects/{pid}/imports", files=parts, headers=headers)
    up.raise_for_status()
    for _ in range(3):
        while worker.run_once():
            pass
        while worker.extraction.run_once():
            pass
    rev = client.get(f"/api/v1/projects/{pid}").json()["latest_source_revision_id"]
    docs = client.get(f"/api/v1/projects/{pid}/documents?source_revision_id={rev}").json()["items"]
    return pid, str(rev), {str(d["document_id"]): str(d["original_filename"]) for d in docs}


def parse_pages(values: list[str]) -> dict[UUID, list[int]]:
    out: dict[UUID, list[int]] = {}
    for value in values:
        ident, sep, pages = value.partition("=")
        if not sep:
            raise ValueError("missing '='")
        out[UUID(ident)] = [int(p) for p in pages.split(",") if p.strip()]
    return out


def parse_documents(values: list[str]) -> list[tuple[UUID, str]]:
    out = []
    for value in values:
        ident, _, label = value.partition(":")
        out.append((UUID(ident), label.strip()))
    return out


def _lane_engine(settings: Settings) -> Any:
    if settings.database_url is None:
        raise RunbookRefusal("no database configured")
    engine = create_engine(settings.database_url.get_secret_value())
    if (engine.url.database or "") in ("", "fieldlens_app"):
        raise RunbookRefusal("this run must use a lane database, not the application database")
    return engine


def main(
    argv: list[str] | None = None,
    env: dict[str, str] | None = None,
    provider_factory: Callable[[Settings], Provider] | None = None,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--allow-live", action="store_true", help="explicit opt-in: spends credit")
    ap.add_argument(
        "--dry-run", action="store_true", help="plan only (default without --allow-live)"
    )
    ap.add_argument("--spend-cap-usd", type=_decimal, default=None)
    ap.add_argument("--project-id", type=UUID, default=None)
    ap.add_argument("--revision-id", type=UUID, default=None)
    ap.add_argument("--document", action="append", default=[], help="<document uuid>:<well label>")
    ap.add_argument("--include-controls", action="store_true")
    ap.add_argument(
        "--pages",
        action="append",
        default=[],
        metavar="DOC=P,P",
        help="retry only these planned pages of a document, e.g. <doc uuid>=30,36",
    )
    ap.add_argument(
        "--only-failed",
        action="store_true",
        help="plan/read only the planned pages whose last read in this project did not succeed",
    )
    ap.add_argument("--file", action="append", default=[], type=Path, help="native file to upload")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--bootstrap-project", default=None, metavar="NAME")
    ap.add_argument("--pdf", action="append", default=[], type=Path)
    args = ap.parse_args(argv)
    environ = dict(os.environ) if env is None else env
    try:
        for path in [*args.pdf, *args.file]:
            if not path.is_file():
                raise RunbookRefusal(f"file not found: {path.name}")
        try:
            parse_documents(args.document)
            parse_pages(args.pages)
        except ValueError:
            raise RunbookRefusal(
                "bad --document/--pages value: <document uuid>[:label] and <document uuid>=1,2 "
                "with integer page numbers are required"
            ) from None
        if args.bootstrap_project:
            return _bootstrap(args)
        if args.project_id is None:
            ap.error("--project-id is required")
        dry = args.dry_run or not args.allow_live
        cap = args.spend_cap_usd
        if cap is not None and (not cap.is_finite() or cap <= 0):
            raise RunbookRefusal("--spend-cap-usd must be a positive amount")
        if not dry:
            problem = refusal(args, environ)
            if problem:
                raise RunbookRefusal(problem.removeprefix("refusing: "))
        settings = Settings()
        if not dry and (
            settings.meta_api_key is None or not settings.meta_api_key.get_secret_value().strip()
        ):
            raise RunbookRefusal("the provider key is not configured")
        factory = create_session_factory(_lane_engine(settings))
        plan = build_plan(
            factory,
            args.project_id,
            args.revision_id,
            parse_documents(args.document),
            include_controls=args.include_controls,
            cap=cap,
            only_pages=parse_pages(args.pages),
            only_failed=args.only_failed,
        )
        print(plan.text)
        if plan.over_cap:
            raise RunbookRefusal("the worst-case reservation total exceeds the cap")
        if dry:
            print("dry run only: nothing was sent and nothing was written")
            return 0
        provider = (provider_factory or MetaProvider)(settings)
        assert cap is not None
        report, records, _ = run(
            factory=factory,
            provider=provider,
            store=BlobStore(settings.storage_root),
            project_id=args.project_id,
            documents=parse_documents(args.document),
            cap=cap,
            include_controls=args.include_controls,
            model=settings.meta_model,
            report_path=args.report,
            revision_id=args.revision_id,
            only_pages={e.document_id: e.pages for e in plan.entries},
        )
        print(f"{len(records)} page(s) read; report written to {args.report}")
        return 0
    except RunbookRefusal as exc:
        print(f"refusing: {exc}")
        return 2


def _bootstrap(args: argparse.Namespace) -> int:
    from fastapi.testclient import TestClient

    from fieldlens.app import create_app

    if not args.pdf:
        raise RunbookRefusal("--bootstrap-project needs at least one --pdf")
    settings = Settings()
    _lane_engine(settings)  # refuses the application database
    app = create_app(settings.model_copy(update={"job_worker_enabled": False}))
    client = TestClient(app, base_url=f"http://127.0.0.1:{settings.port}")
    token = client.get("/api/v1/session").json()["csrf_token"]
    pid, rev, docs = bootstrap_project(
        client,
        {"X-FieldLens-Token": token},
        app.state.job_worker,
        args.bootstrap_project,
        args.pdf,
        args.file,
    )
    print(f"project {pid} revision {rev}")
    identity = client.get(f"/api/v1/projects/{pid}/identity").json()
    names = sorted(b["name"] for w in identity.get("wells", []) for b in w.get("wellbores", []))
    print(f"wellbore identities resolved: {', '.join(names) or 'none'}")
    for doc_id, name in docs.items():
        print(f"--document {doc_id}:<well label>   # {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

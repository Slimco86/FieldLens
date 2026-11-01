"""EQ-11 live runbook: equipment candidates on the approved F-14/F-5 pages (opt-in, spends credit).

NOT run by the TASK-041 implementer. The owner authorizes a run separately; it needs ALL of:

    FIELDLENS_LIVE_META=1 uv run python scripts/run_equipment_live.py \
        --allow-live --spend-cap-usd 1.00 --project-id <uuid> \
        --document <document_uuid>:15/9-F-14 --document <document_uuid>:15/9-F-5 \
        [--include-controls] [--report docs/evidence/TASK041_EQUIPMENT_LIVE_RUN.md]

Refuses to run unless ``--allow-live``, a positive ``--spend-cap-usd`` and ``FIELDLENS_LIVE_META=1``
are all present. The provider key is read only through the existing adapter configuration
(``Settings`` -> ``MetaProvider``); it is never printed, logged or written. The run uses the
existing budget ledger (a new period capped at the given amount), the harness limits (effort
``low``, page concurrency 3) and records per-page latency, tokens and cost. Each ``--document`` must
be a document of the project whose content hash matches a configured page plan (nothing else is
sent). The comparison against ``scripts/spikes/spike042_gold.py`` is against an AGENT-READ reference
that is NOT human verified; model-read results are never described as verified. The report is
written only after a run, never by a refused run or by ``--dry-run``.
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
from decimal import Decimal
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
from fieldlens.candidates.harness import ExtractionHarness, HarnessConfig  # noqa: E402
from fieldlens.candidates.pages import PageRenderer  # noqa: E402
from fieldlens.candidates.sources import SourceReader  # noqa: E402
from fieldlens.config import Settings  # noqa: E402
from fieldlens.evidence.storage import BlobStore  # noqa: E402
from fieldlens.persistence import models as m  # noqa: E402
from fieldlens.persistence.session import create_session_factory  # noqa: E402

OPT_IN_VAR = "FIELDLENS_LIVE_META"
PERIOD = "task-041-live"
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


def refusal(args: argparse.Namespace, env: dict[str, str]) -> str | None:
    """Why the run must not start (None when every explicit gate is present)."""
    if not args.allow_live:
        return "refusing: --allow-live is required (this run spends credit)"
    if args.spend_cap_usd is None or args.spend_cap_usd <= 0:
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
) -> tuple[str, list[PageRecord], list[dict[str, Any]]]:
    ledger = BudgetLedger(factory)
    period = ledger.ensure_period(
        PERIOD, ledger_cap_usd=cap, warn_usd=cap, unattended_block_usd=cap
    )
    try:
        ledger.confirm_balance(period, cap, "TASK-041 owner allowance (runbook argument)")
    except ReservationStateError:
        pass  # already confirmed on an earlier run of this period
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
        cap=cap,
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


def parse_documents(values: list[str]) -> list[tuple[UUID, str]]:
    out = []
    for value in values:
        ident, _, label = value.partition(":")
        out.append((UUID(ident), label.strip()))
    return out


def main(
    argv: list[str] | None = None,
    env: dict[str, str] | None = None,
    provider_factory: Callable[[Settings], Provider] | None = None,
) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--allow-live", action="store_true", help="explicit opt-in: spends credit")
    ap.add_argument("--spend-cap-usd", type=Decimal, default=None)
    ap.add_argument("--project-id", type=UUID, required=True)
    ap.add_argument("--revision-id", type=UUID, default=None)
    ap.add_argument("--document", action="append", default=[], help="<document uuid>:<well label>")
    ap.add_argument("--include-controls", action="store_true")
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = ap.parse_args(argv)
    problem = refusal(args, dict(os.environ) if env is None else env)
    if problem:
        print(problem)
        return 2
    settings = Settings()
    if settings.meta_api_key is None or not settings.meta_api_key.get_secret_value().strip():
        print("refusing: the provider key is not configured")
        return 2
    if settings.database_url is None:
        print("refusing: no database configured")
        return 2
    engine = create_engine(settings.database_url.get_secret_value())
    if (engine.url.database or "") in ("", "fieldlens_app"):
        print("refusing: this run must use a lane database, not the application database")
        return 2
    factory = create_session_factory(engine)
    provider = (provider_factory or MetaProvider)(settings)
    report, records, _ = run(
        factory=factory,
        provider=provider,
        store=BlobStore(settings.storage_root),
        project_id=args.project_id,
        documents=parse_documents(args.document),
        cap=args.spend_cap_usd,
        include_controls=args.include_controls,
        model=settings.meta_model,
        report_path=args.report,
        revision_id=args.revision_id,
    )
    print(f"{len(records)} page(s) read; report written to {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

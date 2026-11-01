"""Opt-in (``-m local_data``): the approved F-14/F-5 page lists on the REAL completion PDFs.

Covers ONLY render, triage, page-plan identity and a STUB-provider end-to-end run (nothing is
sent anywhere; the files are read in place; no model call, no credit). It does not measure model
quality: that is the guarded live runbook (``scripts/run_equipment_live.py``)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import pytest

from fieldlens.candidates import harness as harness_module
from fieldlens.candidates.equipment import DEFAULT_PLANS, EquipmentExtractor
from fieldlens.candidates.pages import PageRenderer
from tests.candidates.conftest import World
from tests.candidates.support import FixtureProvider, json_response

pytestmark = pytest.mark.local_data
_ENV = os.environ.get("FIELDLENS_LOCAL_DATA_ROOT")
if not _ENV or not Path(_ENV).is_dir():
    pytest.skip("FIELDLENS_LOCAL_DATA_ROOT is not set to a directory", allow_module_level=True)
BASE = Path(_ENV) / "Well_logs_pr_WELL"
PV17 = BASE / "15_9-F-14/14.DIV.REPORTS/FWR_Completion_F14.pdf"
PV21 = BASE / "15_9-F-5/14.DIV.REPORTS/COMPLETION_REPORT_1.PDF"
PV11 = BASE / "15_9-F-12/14.DIV.REPORTS/COMPLETION_REPORT_1.PDF"
PV13 = BASE / "15_9-F-12/14.DIV.REPORTS/COMPLETION_REPORT_3.PDF"
PLANNED = {PV17: [4, 29, 30, 35, 36], PV21: [48, 49]}
pytestmark = [
    pytest.mark.local_data,
    pytest.mark.skipif(not (PV17.exists() and PV21.exists()), reason="PV-17/PV-21 not present"),
]


class _Store:
    def path_for(self, key: str) -> Path:
        return Path(key)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_plan_hashes_match_the_real_documents() -> None:
    shas = {p.sha256 for p in DEFAULT_PLANS}
    assert _sha(PV17) in shas and _sha(PV21) in shas
    if PV11.exists():
        assert _sha(PV11) not in shas  # same file name as PV-21, different bytes


def test_render_time_per_planned_page_and_rotation(capsys: pytest.CaptureFixture[str]) -> None:
    r = PageRenderer(_Store())  # type: ignore[arg-type]
    rows: list[dict[str, Any]] = []
    for path, pages in PLANNED.items():
        plan = next(p for p in DEFAULT_PLANS if p.sha256 == _sha(path))
        rotations = dict(plan.rotations)
        for page in pages:
            t0 = time.perf_counter()
            img = r.render(_sha(path)[:12], str(path), page, rotation=rotations.get(page))
            wall = (time.perf_counter() - t0) * 1000
            assert max(img.width, img.height) == 1600
            rows.append(
                {
                    "doc": path.name,
                    "page": page,
                    "rotation": rotations.get(page),
                    "w": img.width,
                    "h": img.height,
                    "render_ms": round(img.render_ms, 1),
                    "wall_ms": round(wall, 1),
                    "bytes": len(img.data),
                }
            )
    plain = r.render("plain36", str(PV17), 36)
    rotated = r.render("rot36", str(PV17), 36, rotation=90)
    assert (plain.width, plain.height) == (rotated.height, rotated.width)  # sideways -> upright
    with capsys.disabled():
        print("\nLOCAL RENDER TIMES " + json.dumps(rows))


def test_scanned_documents_have_no_text_layer_so_the_plan_is_what_selects() -> None:
    from fieldlens.candidates.triage import triage

    r = PageRenderer(_Store())  # type: ignore[arg-type]
    for path in (PV17, PV21):
        result = triage(r.all_page_texts(str(path)))
        assert result.selected == [] and result.strategy == "no_text_layer"


def test_stub_end_to_end_on_the_real_page_lists(
    world: World, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    files = [("pv17_f14.pdf", PV17.read_bytes()), ("pv21_f5.pdf", PV21.read_bytes())]
    wrong = [p for p in (PV11, PV13) if p.exists()]
    files += [(f"f12_{p.stem.lower()}.pdf", p.read_bytes()) for p in wrong]
    assert world.api.upload(
        str(world.project_id), files, parent=str(world.revision_id)
    ).status_code in (200, 201, 202)
    for _ in range(3):
        while world.api.worker.run_once():
            pass
        while world.api.worker.extraction.run_once():
            pass
    revision = world.api.latest(str(world.project_id))
    assert revision is not None
    from uuid import UUID

    docs = {
        d["original_filename"]: UUID(d["document_id"])
        for d in world.api.documents(str(world.project_id), revision)
    }
    rev = UUID(revision)

    def respond(request: Any, n: int) -> Any:
        text = next(
            p.text
            for m in request.messages
            if m.role == "user"
            for p in m.parts
            if hasattr(p, "text")
        )
        page = int(re.search(r'"page":(\d+)', text).group(1))  # type: ignore[union-attr]
        doc = re.search(r'"document_id":"([0-9a-f-]{36})"', text).group(1)  # type: ignore[union-attr]
        items = [
            {
                "kind": "equipment",
                "category": cat,
                "label_text": f"{cat} {i}",
                "od": {"value_text": "9 5/8", "unit": "in"},
                "top_depth": {
                    "value_text": str(3000 + 10 * i),
                    "unit": "m",
                    "reference_text": "MD",
                },
                "locator": {"document_id": doc, "page": page},
            }
            for i, cat in enumerate(
                ["casing", "tubing", "packer", "liner", "completion_accessory", "other"]
            )
        ]
        return json_response(items)

    validate_ms: list[float] = []
    real = harness_module.validate_equipment

    def timed(ctx: Any, wire: Any) -> Any:
        t0 = time.perf_counter()
        try:
            return real(ctx, wire)
        finally:
            validate_ms.append((time.perf_counter() - t0) * 1000)

    monkeypatch.setattr(harness_module, "validate_equipment", timed)
    provider = FixtureProvider(respond)
    ex = EquipmentExtractor(world.harness(provider))
    t0 = time.perf_counter()
    out = {}
    for name, label in (("pv17_f14.pdf", "15/9-F-99"), ("pv21_f5.pdf", "15/9-F-98")):
        out[name] = ex.run_document(world.project_id, rev, docs[name], subject_label=label)
    wall = time.perf_counter() - t0
    for name, res in out.items():
        assert not res.excluded and res.summary is not None and res.summary.state == "succeeded", (
            name
        )
    assert [o.page for o in out["pv17_f14.pdf"].summary.pages] == [4, 29, 30, 35, 36]  # type: ignore[union-attr]
    assert [o.page for o in out["pv21_f5.pdf"].summary.pages] == [48, 49]  # type: ignore[union-attr]
    n = world.scalar(
        "select count(*) from extraction_candidate where attributes->>'kind'='equipment'"
    )
    assert n == 7 * 6
    assert world.scalar("select count(*) from extraction_candidate where state='accepted'") == 0
    # wrong-folder: the F-12 folder's reports print F-11 wells and are excluded without a read
    for p in wrong:
        res = ex.run_document(
            world.project_id, rev, docs[f"f12_{p.stem.lower()}.pdf"], subject_label="15/9-F-12"
        )
        assert res.excluded and res.exclusion_code == "document_excluded_wrong_subject"
    calls_before = len(provider.calls)
    assert calls_before == 7
    with capsys.disabled():
        per_page = {
            f"{n}:p{o.page}": round(o.elapsed_s * 1000)
            for n, r in out.items()
            for o in r.summary.pages  # type: ignore[union-attr]
        }
        print(
            "\nLOCAL STUB E2E "
            + json.dumps(
                {
                    "wall_s": round(wall, 2),
                    "pages": 7,
                    "per_page_ms": per_page,
                    "validate_ms_per_item_avg": round(sum(validate_ms) / len(validate_ms), 2),
                    "validate_ms_per_item_max": round(max(validate_ms), 2),
                    "items": len(validate_ms),
                    "excluded_f12_docs": len(wrong),
                }
            )
        )


def test_dry_run_plan_on_the_real_documents(
    world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    """Bootstrap the two real PDFs into a throwaway project and print the runbook's dry-run plan
    (no provider, no network, nothing written)."""
    import importlib.util
    import sys
    from decimal import Decimal

    script = Path(__file__).resolve().parents[3] / "scripts" / "run_equipment_live.py"
    spec = importlib.util.spec_from_file_location("run_equipment_live_local", script)
    assert spec and spec.loader
    runbook = importlib.util.module_from_spec(spec)
    sys.modules["run_equipment_live_local"] = runbook
    spec.loader.exec_module(runbook)
    pid, rev, docs = runbook.bootstrap_project(
        world.api.client, world.api.headers, world.api.worker, "dry-run", [PV17, PV21]
    )
    by_name = {name: doc for doc, name in docs.items()}
    from uuid import UUID

    plan = runbook.build_plan(
        world.factory,
        UUID(pid),
        UUID(rev),
        [(UUID(by_name[PV17.name]), "15/9-F-14"), (UUID(by_name[PV21.name]), "15/9-F-5")],
        include_controls=False,
        cap=Decimal("3"),
    )
    assert plan.pages == 7 and plan.worst_case_usd == Decimal("1.75") and not plan.over_cap
    with capsys.disabled():
        print("\n" + plan.text)

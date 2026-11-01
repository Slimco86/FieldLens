"""EQ-11 runbook code paths, OFFLINE (the live run itself is opt-in and is NOT run here):
the refusal gates, the report, the comparison with the agent-read reference and a stub-provider
pass through the whole script. No credit, no network."""

from __future__ import annotations

import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest

from fieldlens.candidates.equipment import PagePlan
from tests.candidates.conftest import World
from tests.candidates.eq_helpers import equip
from tests.candidates.support import FixtureProvider, first_user_text, json_response

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "run_equipment_live.py"


@pytest.fixture(scope="module")
def runbook() -> ModuleType:
    spec = importlib.util.spec_from_file_location("run_equipment_live", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_equipment_live"] = module
    spec.loader.exec_module(module)
    return module


DOC = "00000000-0000-0000-0000-000000000001:15/9-F-14"
PID = "00000000-0000-0000-0000-0000000000aa"


@pytest.mark.parametrize(
    ("argv", "env", "needle"),
    [
        (
            ["--project-id", PID, "--document", DOC, "--spend-cap-usd", "1"],
            {"FIELDLENS_LIVE_META": "1"},
            "--allow-live",
        ),
        (
            ["--project-id", PID, "--document", DOC, "--allow-live"],
            {"FIELDLENS_LIVE_META": "1"},
            "--spend-cap-usd",
        ),
        (
            ["--project-id", PID, "--document", DOC, "--allow-live", "--spend-cap-usd", "0"],
            {"FIELDLENS_LIVE_META": "1"},
            "positive",
        ),
        (
            ["--project-id", PID, "--document", DOC, "--allow-live", "--spend-cap-usd", "-3"],
            {"FIELDLENS_LIVE_META": "1"},
            "positive",
        ),
        (
            ["--project-id", PID, "--document", DOC, "--allow-live", "--spend-cap-usd", "999"],
            {"FIELDLENS_LIVE_META": "1"},
            "bound",
        ),
        (
            ["--project-id", PID, "--document", DOC, "--allow-live", "--spend-cap-usd", "1"],
            {},
            "FIELDLENS_LIVE_META",
        ),
        (
            ["--project-id", PID, "--allow-live", "--spend-cap-usd", "1"],
            {"FIELDLENS_LIVE_META": "1"},
            "--document",
        ),
    ],
)
def test_runbook_refuses_without_every_gate(
    runbook: ModuleType,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    env: dict[str, str],
    needle: str,
) -> None:
    report = tmp_path / "report.md"
    code = runbook.main([*argv, "--report", str(report)], env)
    assert code == 2 and needle in capsys.readouterr().out
    assert not report.exists()  # a refused run writes nothing


def test_runbook_refuses_without_key_or_on_the_application_database(
    runbook: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class NoKey:
        meta_api_key = None
        database_url = None

    monkeypatch.setattr(runbook, "Settings", NoKey)
    argv = ["--project-id", PID, "--document", DOC, "--allow-live", "--spend-cap-usd", "1"]
    assert runbook.main(argv, {"FIELDLENS_LIVE_META": "1"}) == 2
    assert "key is not configured" in capsys.readouterr().out
    assert not any(tmp_path.iterdir())


def test_compare_with_the_agent_read_reference(runbook: ModuleType) -> None:
    items = [
        {
            "category": "casing",
            "od": {"value_text": "9.625"},
            "top_depth": {"value_text": "2921.0"},
        },
        {"category": "tubing", "top_depth": {"value_text": "2783.77"}},
        {"category": "perforation_interval", "top_depth": {"value_text": "3605"}},
        {"category": "pump"},  # no reference counterpart
    ]
    c = runbook.compare_page("PV-21", 49, items)
    assert c["key"] == "PV-21:49" and c["read_items"] == 4 and c["reference_items"] > 4
    assert 0 < c["category_agreement"] < 1 and c["size_matches"] >= 1
    assert c["by_category_read"]["pump"] == 1
    # a control page expects no items at all; a page with no reference entry is only counted
    assert runbook.compare_page("PV-18", 1, [])["control"] is True
    assert runbook.compare_page("PV-18", 1, items)["read_items"] == 4
    assert runbook.compare_page("PV-99", 1, items)["reference"] is False
    assert runbook.category_of("safety_valve") == "completion_accessory"
    assert (
        runbook.category_of("pup_joint") == "tubing" and runbook.category_of("plug") == "isolation"
    )


def test_runbook_end_to_end_on_the_stub_provider(
    runbook: ModuleType, world: World, tmp_path: Path
) -> None:
    sha = str(
        world.scalar("select sha256 from source_document where document_id=:d", d=world.scan_doc)
    )
    plan = PagePlan("synthetic scan (PV-17)", sha, None, (1,), controls=(2,))
    provider = FixtureProvider(
        lambda r, n: (
            json_response([equip(world.scan_doc, 1)])
            if '"page":1' in first_user_text(r).replace(" ", "")
            else json_response([])
        )
    )
    report_path = tmp_path / "docs" / "report.md"
    report, records, comparisons = runbook.run(
        factory=world.factory,
        provider=provider,
        store=world.api.client.app.state.blob_store,
        project_id=world.project_id,
        documents=[(world.scan_doc, "15/9-F-99")],
        cap=Decimal("1.00"),
        include_controls=True,
        model="stub-model-1",
        report_path=report_path,
        revision_id=world.revision_id,
        plans=(plan,),
    )
    assert [r.page for r in records] == [1, 2] and all(r.state == "succeeded" for r in records)
    assert sum(len(r.items) for r in records) == 1
    assert records[1].control and comparisons[1].get("reference") is False
    text = report_path.read_text()
    assert "OFFLINE STUB" in text and "LIVE (" not in text
    assert report == text and "UNVERIFIED" in text and "NOT human verified" in text
    assert "| PV-17 | 1 | succeeded | 1 |" in text and "(control)" in text
    assert "Spend cap USD 1.00" in text
    # nothing but the planned pages was sent: one provider call per page
    assert len(provider.calls) == 2
    # a document with no configured plan is skipped, never sent
    other = runbook.run(
        factory=world.factory,
        provider=provider,
        store=world.api.client.app.state.blob_store,
        project_id=world.project_id,
        documents=[(world.pdf_doc, "15/9-F-99")],
        cap=Decimal("1.00"),
        include_controls=False,
        model="stub-model-1",
        report_path=None,
        revision_id=world.revision_id,
        plans=(plan,),
    )
    assert other[1] == [] and "no configured page plan" in other[0] and len(provider.calls) == 2

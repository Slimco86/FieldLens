"""EQ-11 runbook code paths, OFFLINE (the live run itself is opt-in and is NOT run here):
the refusal gates, the report, the comparison with the agent-read reference and a stub-provider
pass through the whole script. No credit, no network."""

from __future__ import annotations

import importlib.util
import re
import sys
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

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


def test_bad_caps_refuse_cleanly(runbook: ModuleType, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--project-id", PID, "--document", DOC, "--allow-live"]
    for bad in ("nan", "-inf", "inf", "-1"):
        assert runbook.main([*base, f"--spend-cap-usd={bad}"], {"FIELDLENS_LIVE_META": "1"}) == 2
        assert "positive" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:  # argparse's own clean usage error, no traceback
        runbook.main([*base, "--spend-cap-usd=abc"], {"FIELDLENS_LIVE_META": "1"})
    assert exc.value.code == 2
    # a dry run (no --allow-live) also rejects them cleanly
    dry = ["--project-id", PID, "--document", DOC, "--spend-cap-usd", "nan"]
    assert runbook.main(dry, {}) == 2 and "positive" in capsys.readouterr().out


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
    assert re.search(r"Spend cap USD 1(\.0+)?;", text)
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


def _plan(world: World) -> tuple[Any, ...]:
    sha = str(
        world.scalar("select sha256 from source_document where document_id=:d", d=world.scan_doc)
    )
    return (PagePlan("synthetic scan (PV-17)", sha, None, (1,), ((1, 90),), controls=(2,)),)


def test_dry_run_plan_and_worst_case_cap(runbook: ModuleType, world: World) -> None:
    docs = [(world.scan_doc, "15/9-F-99"), (world.pdf_doc, "15/9-F-99")]
    plan = runbook.build_plan(
        world.factory,
        world.project_id,
        world.revision_id,
        docs,
        include_controls=True,
        cap=Decimal("3"),
        plans=_plan(world),
    )
    assert plan.pages == 2 and plan.provider_calls_expected == 2
    assert plan.worst_case_usd == Decimal("0.50") and not plan.over_cap
    sha = str(
        world.scalar("select sha256 from source_document where document_id=:d", d=world.scan_doc)
    )
    for needle in (
        sha,
        "pages=[1, 2]",
        "rotations={1: 90}",
        "effort=low",
        "concurrency=3",
        "1600px",
        "worst-case reservation total",
        "within the cap",
        "no configured page plan",
    ):
        assert needle in plan.text, needle
    tight = runbook.build_plan(
        world.factory,
        world.project_id,
        world.revision_id,
        docs,
        include_controls=True,
        cap=Decimal("0.40"),
        plans=_plan(world),
    )
    assert tight.over_cap and "EXCEEDS THE CAP" in tight.text


def test_main_dry_run_constructs_no_provider_and_writes_nothing(
    runbook: ModuleType,
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class Fake:
        meta_api_key = None
        database_url = None

    monkeypatch.setattr(runbook, "Settings", Fake)
    monkeypatch.setattr(runbook, "_lane_engine", lambda settings: None)
    monkeypatch.setattr(runbook, "create_session_factory", lambda engine: world.factory)
    original = runbook.build_plan
    monkeypatch.setattr(
        runbook, "build_plan", lambda *a, **k: original(*a, plans=_plan(world), **k)
    )

    def no_provider(settings: Any) -> Any:
        raise AssertionError("a dry run must not construct a provider")

    report = tmp_path / "r.md"
    argv = [
        "--project-id",
        str(world.project_id),
        "--spend-cap-usd",
        "3",
        "--document",
        f"{world.scan_doc}:15/9-F-99",
        "--include-controls",
        "--report",
        str(report),
    ]
    assert runbook.main(argv, {}, no_provider) == 0
    out = capsys.readouterr().out
    assert "DRY RUN plan" in out and "pages=[1, 2]" in out and "nothing was sent" in out
    assert not report.exists()
    # the worst case above the cap refuses, even in a dry run
    assert runbook.main([*argv[:3], "0.2", *argv[4:]], {}, no_provider) == 2
    assert "exceeds the cap" in capsys.readouterr().out
    # --allow-live with every gate but a worst case over the cap also refuses before any provider
    live = [*argv[:3], "0.2", *argv[4:], "--allow-live"]

    class WithKey(Fake):
        class _K:
            def get_secret_value(self) -> str:
                return "x"

        meta_api_key = _K()

    monkeypatch.setattr(runbook, "Settings", WithKey)
    assert runbook.main(live, {"FIELDLENS_LIVE_META": "1"}, no_provider) == 2
    assert "exceeds the cap" in capsys.readouterr().out


def test_period_cap_is_never_silently_reused(
    runbook: ModuleType, world: World, tmp_path: Path
) -> None:
    from fieldlens.assistant.budget import BudgetLedger

    # an old period with the name this cap would use, but another cap
    ledger = BudgetLedger(world.factory)
    old = ledger.ensure_period(
        runbook.PERIOD_PREFIX + "1",
        ledger_cap_usd=Decimal("2"),
        warn_usd=Decimal("2"),
        unattended_block_usd=Decimal("2"),
    )
    ledger.confirm_balance(old, Decimal("2"), "old")
    kwargs: dict[str, Any] = {
        "factory": world.factory,
        "provider": FixtureProvider(lambda r, n: json_response([])),
        "store": world.api.client.app.state.blob_store,
        "project_id": world.project_id,
        "documents": [(world.scan_doc, "15/9-F-99")],
        "include_controls": False,
        "model": "stub-model-1",
        "report_path": None,
        "revision_id": world.revision_id,
        "plans": _plan(world),
    }
    with pytest.raises(runbook.RunbookRefusal, match="not the requested"):
        runbook.run(cap=Decimal("1"), **kwargs)
    assert kwargs["provider"].calls == []
    # another cap gets its own period and the report prints the cap actually enforced
    report, records, _ = runbook.run(cap=Decimal("3"), **kwargs)
    assert re.search(r"Spend cap USD 3(\.0+)?;", report) and records
    for bad in (Decimal("nan"), Decimal("-1"), Decimal(0)):
        with pytest.raises(runbook.RunbookRefusal):
            runbook.run(cap=bad, **kwargs)


def test_bootstrap_helper_uploads_local_pdfs_without_a_provider(
    runbook: ModuleType, world: World, tmp_path: Path
) -> None:
    from tests.candidates.pdfs import EQUIPMENT_LINES, PdfPage, make_pdf

    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(make_pdf([PdfPage(lines=EQUIPMENT_LINES)]))
    pid, rev, docs = runbook.bootstrap_project(
        world.api.client, world.api.headers, world.api.worker, "throwaway", [pdf]
    )
    assert list(docs.values()) == ["x.pdf"] and pid and rev

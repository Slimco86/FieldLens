"""BK-1..BK-3: strict ledger parser/validator, conversion inventory, helpers."""

from __future__ import annotations

import importlib
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))
ledger = importlib.import_module("ledger")
track = importlib.import_module("track")

BACKLOG = REPO / "docs" / "BACKLOG.md"

FEATURE = {
    "Type": "feature",
    "Status": "in_progress",
    "Priority": "P0",
    "Tags": "backend",
    "Depends on": "none",
    "Assignee": "owner",
    "Due": "2026-11-01",
    "Sprint": "Hackathon",
    "Spec": "none",
    "Version": "none",
}
TASK = {**FEATURE, "Type": "task", "Parent": "FL-001", "Slice": "FL-001-A"}


def block(item_id: str, title: str = "Title", **over: Any) -> str:
    base = dict(TASK if item_id.startswith("TASK") else FEATURE)
    for key, value in over.items():
        key = key.replace("_", " ")
        if value is None:
            base.pop(key, None)
        else:
            base[key] = value
    rows = "\n".join(f"| {k} | {v} |" for k, v in base.items())
    return (
        f"### {item_id} · {title}\n\n| Field | Value |\n|---|---|\n{rows}\n\n"
        "**Outcome.** Does a thing.\n**Next action.** Do more.\n**Evidence.** none yet\n\n"
    )


def ledger_text(features: str = "", tasks: str = "", journal: bool = True) -> str:
    text = "# FieldLens backlog\n\nPreamble.\n\n## Features\n\n" + features
    text += "## Tasks\n\n" + tasks
    if journal:
        text += "## Journal\n\nHistory.\n"
    return text


GOOD_FEATURES = block("FL-001") + block("FL-002", Depends_on="FL-001", Due="2026-11-02")
GOOD_TASKS = block("TASK-001") + block("TASK-002", Depends_on="TASK-001", Due="2026-11-02")


def messages(text: str, base: Path | None = None) -> list[str]:
    parsed = ledger.parse_text(text)
    found = list(parsed.violations) + ledger.validate(parsed.items, base)
    return [str(v) for v in found]


def test_minimal_good_ledger_passes() -> None:
    assert messages(ledger_text(GOOD_FEATURES, GOOD_TASKS)) == []


@pytest.mark.parametrize(
    ("features", "tasks", "needle"),
    [
        # required field missing
        (block("FL-001", Priority=None), "", "missing required field 'Priority'"),
        (block("FL-001"), block("TASK-001", Parent=None), "missing required field 'Parent'"),
        (block("FL-001"), block("TASK-001", Slice=None), "missing required field 'Slice'"),
        # enum values
        (block("FL-001", Status="started"), "", "Status 'started'"),
        (block("FL-001", Priority="P3"), "", "Priority 'P3'"),
        (block("FL-001", Tags="Backend"), "", "lowercase kebab"),
        (block("FL-001", Tags="unknown-tag"), "", "not in the vocabulary"),
        (block("FL-001", Assignee="bob"), "", "Assignee must be"),
        (block("FL-001", Sprint="Sprint 1"), "", "Sprint must be 'Hackathon'"),
        (block("FL-001", Version="v1"), "", "Version 'v1'"),
        (block("FL-001", Type="task"), "", "contradicts"),
        # dates
        (block("FL-001", Due="2026-13-01"), "", "valid YYYY-MM-DD"),
        (block("FL-001", Due="2026-11-05"), "", "outside"),
        (block("FL-001", Due="2026-10-28"), "", "outside"),
        # dependencies
        (block("FL-001", Depends_on="FL-009"), "", "FL-009 does not exist"),
        (block("FL-001", Depends_on="FL-001"), "", "depends on itself"),
        (block("FL-001", Depends_on="nope"), "", "not an item ID"),
        (
            block("FL-001", Depends_on="FL-002", Due="2026-11-01")
            + block("FL-002", Depends_on="FL-001", Due="2026-11-01"),
            "",
            "dependency cycle",
        ),
        (
            block("FL-001", Due="2026-11-03")
            + block("FL-002", Depends_on="FL-001", Due="2026-11-01"),
            "",
            "before dependency FL-001",
        ),
        # parent rules
        (block("FL-001"), block("TASK-001", Parent="FL-009"), "Parent FL-009 does not exist"),
        (
            block("FL-001"),
            block("TASK-001", Parent="TASK-002", Slice="TASK-002-A") + block("TASK-002"),
            "is not a feature",
        ),
        (block("FL-001", Parent="FL-001"), "", "tasks only"),
        # done rules
        (block("FL-001", Status="done", Version="none"), "", "need a Version"),
        (block("FL-001", Status="done", Version="0.1.0"), "", "not 'none yet'"),
        (
            block("FL-001") + block("FL-002", Status="done", Version="0.1.0", Depends_on="FL-001"),
            "",
            "done item depends on FL-001",
        ),
        # secrets
        (
            block("FL-001").replace("Does a thing.", "password=hunter2hunter2 leaked"),
            "",
            "secret-like",
        ),
    ],
)
def test_check_rules(features: str, tasks: str, needle: str) -> None:
    found = messages(ledger_text(features, tasks))
    assert any(needle in m for m in found), (needle, found)


def test_check_rules_duplicate_and_missing_journal() -> None:
    dup = messages(ledger_text(block("FL-001") + block("FL-001")))
    assert any("duplicate ID" in m for m in dup)
    nojournal = messages(ledger_text(GOOD_FEATURES, GOOD_TASKS, journal=False))
    assert any("missing '## Journal'" in m for m in nojournal)


def test_done_with_evidence_and_relaxed_window_passes() -> None:
    done = block("FL-001", Status="done", Version="0.1.0", Due="2026-10-27").replace(
        "**Evidence.** none yet", "**Evidence.** Integrated in `abc1234`."
    )
    assert messages(ledger_text(done)) == []


def test_violations_carry_line_numbers_and_exit_code(tmp_path: Path) -> None:
    text = ledger_text(block("FL-001", Status="bogus"))
    path = tmp_path / "BACKLOG.md"
    path.write_text(text, encoding="utf-8")
    line = next(i for i, ln in enumerate(text.splitlines(), 1) if "| Status | bogus" in ln)
    led = ledger.load_ledger(path)
    assert any(v.line == line for v in led.violations)
    assert track.main(["--file", str(path), "check"]) == 1
    good = tmp_path / "GOOD.md"
    good.write_text(ledger_text(GOOD_FEATURES, GOOD_TASKS), encoding="utf-8")
    assert track.main(["--file", str(good), "check"]) == 0
    assert track.main(["--file", str(tmp_path / "missing.md"), "check"]) == 2


# ---------------------------------------------------------------- BK-3 strict parser


@pytest.mark.parametrize(
    ("text", "needle"),
    [
        (block("FL-001", Colour="red"), "unknown field 'Colour'"),
        (
            block("FL-001").replace("| Status | in_progress |", "| Status | in_progress | x |"),
            "2 columns",
        ),
        (block("FL-001").replace("| Field | Value |", "| Name | Value |"), "table header"),
        (block("FL-001").replace("|---|---|", "| a | b |"), "separator"),
        (
            block("FL-001").replace("### FL-001 · Title", "### FL-001 - Title"),
            "heading does not match",
        ),
        (block("FL-001").replace("### FL-001", "### FL-01"), "heading does not match"),
        (block("FL-001").replace("**Outcome.**", "**Result.**"), "unexpected text"),
        (block("FL-001").replace("**Evidence.** none yet", ""), "missing label **Evidence.**"),
        (block("FL-001") + "Stray paragraph.\n", "unexpected text"),
        (
            block("FL-001").replace("| Type | feature |", "| Type | feature |\n| Type | feature |"),
            "duplicate field 'Type'",
        ),
        (block("FL-001").replace("| Field | Value |\n|---|---|\n", ""), "table header must be"),
        (block("TASK-001"), "wrong section"),
    ],
)
def test_parser_strict(text: str, needle: str) -> None:
    found = messages(ledger_text(text))
    assert any(needle in m for m in found), (needle, found)


def test_item_heading_outside_sections_and_journal_ignored() -> None:
    pre = "# FieldLens backlog\n\n### FL-001 · Early\n\n"
    found = messages(pre + "## Features\n\n" + block("FL-002") + "## Tasks\n\n## Journal\n")
    assert any("outside" in m for m in found)
    journal = (
        ledger_text(GOOD_FEATURES, GOOD_TASKS)
        + "\n### FL-999 · history only\n\n| junk |\n\n**Outcome.** x\n"
    )
    assert messages(journal) == []


def test_parse_multiline_labels_and_fields() -> None:
    text = ledger_text(block("FL-001").replace("Does a thing.", "Does a\nsecond line."))
    item = ledger.parse_text(text).items[0]
    assert item.outcome == "Does a second line."
    assert item.title == "Title" and item.depends_on == () and item.due == date(2026, 11, 1)


# ------------------------------------------------------------ BK-2 conversion inventory


def test_conversion_inventory() -> None:
    led = ledger.load_ledger(BACKLOG)
    assert [str(v) for v in led.violations] == []
    features = [i.id for i in led.items if i.is_feature]
    tasks = [i.id for i in led.items if not i.is_feature]
    assert features == [f"FL-{n:03d}" for n in range(21)]
    assert sorted(tasks) == [f"TASK-{n:03d}" for n in range(1, 33)]
    by_id = led.by_id()
    assert by_id["FL-019"].status == "done" and by_id["FL-019"].version == "0.10.0"
    assert by_id["FL-020"].status == "in_progress"
    for tid, version in {
        "TASK-003": "0.4.0",
        "TASK-025": "0.5.0",
        "TASK-006": "0.8.0",
        "TASK-007": "0.6.0",
        "TASK-008": "0.7.0",
    }.items():
        assert by_id[tid].status == "done" and by_id[tid].version == version
    text = BACKLOG.read_text(encoding="utf-8")
    journal = text.split("\n## Journal\n", 1)[1]
    for marker in (
        "Parallel lane allocation, October 29",
        "Foundation implementation and independent acceptance",
        "Finalized priorities and next dispatch",
        "TASK-025 completed lifecycle integration",
        "Data-first planning checkpoint",
        "Add a record when scheduling",
    ):
        assert marker in journal, marker
    profiles = {
        p.name.removesuffix(".agent.md") for p in (REPO / ".github/agents").glob("*.agent.md")
    }
    for item in led.items:
        if item.assignee.startswith("agent:"):
            assert item.assignee[6:] in profiles, item.id


def test_backlog_links_resolve() -> None:
    text = BACKLOG.read_text(encoding="utf-8")
    broken = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        if not (BACKLOG.parent / target.split("#", 1)[0]).exists():
            broken.append(target)
    assert broken == []


def test_plan_command_and_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert track.main(["plan"]) == 0
    out = capsys.readouterr().out
    assert "feature: 21" in out and "task: 32" in out
    assert "sync not available in this slice" in out
    assert track.main(["list", "--status", "done", "--tag", "foundation"]) == 0
    assert "FL-004" in capsys.readouterr().out


# ----------------------------------------------------------------- Taiga-sync helpers


def test_unmet_dependencies_and_blocked_note() -> None:
    feats = (
        block("FL-001", Status="done", Version="0.1.0").replace("none yet", "Done in `abc`.")
        + block("FL-002", Depends_on="FL-001", Due="2026-11-02")
        + block("FL-003", Depends_on="FL-001, FL-002", Due="2026-11-03")
        + block("FL-004", Status="done", Version="0.1.0", Depends_on="FL-001").replace(
            "none yet", "Done in `abc`."
        )
    )
    items = ledger.parse_text(ledger_text(feats)).items
    by_id = {i.id: i for i in items}
    assert [d.id for d in ledger.unmet_dependencies(by_id["FL-003"], by_id)] == ["FL-002"]
    assert ledger.unmet_dependencies(by_id["FL-002"], by_id) == []
    assert ledger.blocked_note(by_id["FL-003"], by_id) == "Waiting for FL-002 (in_progress)"
    assert ledger.blocked_note(by_id["FL-002"], by_id) is None
    assert ledger.blocked_note(by_id["FL-004"], by_id) is None


def test_taiga_status_map_matches_spec() -> None:
    m = ledger.TAIGA_STATUS_MAP
    assert set(m) == set(ledger.STATUSES)
    assert (m["ready"].story, m["ready"].task) == ("Ready", "New")
    assert (m["done"].story, m["done"].task) == ("Done", "Closed")
    assert m["blocked"].is_blocked and m["blocked"].story == "New"
    assert m["cancelled"].story == "Archived" and m["cancelled"].task_tag == "cancelled"
    assert m["testing"] == m["integration_pending"]


def test_description_renderer_is_deterministic_and_guards_secrets() -> None:
    items = ledger.parse_text(ledger_text(GOOD_FEATURES)).items
    by_id = {i.id: i for i in items}
    first = ledger.render_description(by_id["FL-002"], by_id)
    assert first == ledger.render_description(by_id["FL-002"], by_id)
    assert first.startswith("**Outcome.** Does a thing.\n")
    assert "- FL-001 (in_progress)" in first and "**Spec.** none" in first
    assert "**Version.** none" in first
    leaky = ledger.parse_text(
        ledger_text(block("FL-001").replace("Do more.", "token=abcdef123456 here"))
    ).items
    with pytest.raises(ledger.SecretInDescription):
        ledger.render_description(leaky[0], {leaky[0].id: leaky[0]})
    assert ledger.find_secret("123456789:" + "A" * 35) == "telegram-bot-token"
    assert ledger.find_secret("commit 2f56a43 passes") is None

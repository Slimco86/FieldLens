"""TASK-041 EQ-10 run level: page selection (configured lists, triage fallback, blind sample),
rotation, wrong-folder exclusion, prompt/cache identity, speed bounds. Offline stub provider."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fieldlens.assistant.messages import ImagePart
from fieldlens.candidates import harness as harness_module
from fieldlens.candidates.equipment import (
    DEFAULT_PLANS,
    PLAN_VERSION,
    EquipmentExtractor,
    PagePlan,
    check_document_scope,
    find_plan,
)
from fieldlens.candidates.equipment_prompt import (
    EQUIPMENT_CATEGORIES,
    EQUIPMENT_PROMPT_VERSION,
    EQUIPMENT_QUESTION,
    EQUIPMENT_SYSTEM_PROMPT,
)
from fieldlens.candidates.harness import UnitRequest
from tests.candidates.conftest import World
from tests.candidates.eq_helpers import eq_rows, equip
from tests.candidates.support import FixtureProvider, json_response


def _sha(world: World, doc: Any) -> str:
    return str(world.scalar("select sha256 from source_document where document_id = :d", d=doc))


def _extractor(world: World, provider: FixtureProvider, **kw: Any) -> EquipmentExtractor:
    plans = kw.pop("plans", DEFAULT_PLANS)
    excluded = kw.pop("excluded_documents", None)
    return EquipmentExtractor(
        world.harness(provider, **kw), plans=plans, excluded_documents=excluded
    )


def test_default_plans_are_versioned_configuration() -> None:
    assert PLAN_VERSION == "eq-pages-1"
    by = {p.label: p for p in DEFAULT_PLANS}
    f14 = by["F-14 FWR completion (PV-17)"]
    assert f14.pages == (4, 29, 30, 35, 36) and dict(f14.rotations) == {36: 90}
    f5 = by["F-5 completion report (PV-21)"]
    assert f5.pages == (48, 49) and f5.filename is None  # the name also exists in the F-12 folder
    for plan in DEFAULT_PLANS:
        assert plan.sha256 is None or len(plan.sha256) == 64
        assert not any(w in plan.label for w in ("15/9", "wellbore"))  # no identity in the plan


def test_plan_matches_by_hash_and_only_unique_filenames(world: World) -> None:
    doc = world.reader.require(world.project_id, world.revision_id, world.scan_doc)
    plan = PagePlan("scan", _sha(world, world.scan_doc), None, (1,))
    assert find_plan(doc, "whatever.pdf", (plan,)) is plan
    named = PagePlan("by name", None, "Scan.PDF", (2,))
    assert find_plan(doc, "scan.pdf", (named,)) is named
    twin = PagePlan("twin", None, "scan.pdf", (3,))
    assert find_plan(doc, "scan.pdf", (named, twin)) is None  # ambiguous name: no match
    assert find_plan(doc, "scan.pdf", ()) is None


def test_configured_pages_and_rotation_reach_the_page_image(world: World) -> None:
    plan = PagePlan("scan", _sha(world, world.scan_doc), None, (1, 2), ((1, 90),))
    provider = FixtureProvider(lambda r, n: json_response([equip(world.scan_doc, 1)]))
    ex = _extractor(world, provider, plans=(plan,))
    res = ex.run_document(
        world.project_id, world.revision_id, world.scan_doc, subject_label="15/9-F-99"
    )
    assert not res.excluded and res.selection is not None
    assert res.selection.strategy == "configured" and res.selection.pages == [1, 2]
    assert res.selection.rotations == {1: 90}
    assert res.summary is not None and res.summary.state == "succeeded"
    assert [o.page for o in res.summary.pages] == [1, 2]
    args = [
        json.loads(r[2])["args"]
        for r in world.rows(
            "select tool_name, outcome, detail::text from agent_step where tool_name='get_page_image'"
        )
    ]
    rotated = [a for a in args if a.get("page") == 1]
    assert rotated and all(a.get("rotation") == 90 for a in rotated)
    assert all("rotation" not in a for a in args if a.get("page") == 2)
    # the model got the image and the equipment instruction at effort low, upright 1600 px
    first = provider.calls[0]
    assert first.effort == "low"
    assert any(isinstance(p, ImagePart) for m in first.messages for p in m.parts)
    sizes = [
        max(json.loads(r[0])["width"], json.loads(r[0])["height"])
        for r in world.rows("select detail::text from agent_step where tool_name='get_page_image'")
    ]
    assert sizes and max(sizes) == 1600


def test_triage_fallback_and_blind_sample_are_explicit(world: World) -> None:
    provider = FixtureProvider(lambda r, n: json_response([]))
    ex = _extractor(world, provider, plans=())
    # a text-layer document with no list uses triage
    sel = ex.select_pages(world.project_id, world.revision_id, world.big_doc)
    assert sel.strategy == "triage" and 1 < len(sel.pages) <= 12 and sel.rotations == {}
    # a document whose pages have no equipment text and no list: nothing selected, loudly
    res = ex.run_document(world.project_id, world.revision_id, world.scan_doc)
    assert res.selection is not None and res.selection.pages == []
    assert res.summary is not None
    assert (res.summary.state, res.summary.stop_reason) == ("failed", "no_pages_selected")
    assert provider.calls == []
    # the opt-in blind sample reads pages that cannot be scored
    blind = ex.select_pages(world.project_id, world.revision_id, world.scan_doc, blind_sample=True)
    assert blind.strategy == "triage+blind_sample" and blind.pages == [1]
    # a wholly image-only document is sampled evenly, only on request
    imageonly = ex.select_pages(world.project_id, world.revision_id, world.imageonly_doc)
    assert imageonly.pages == [] and imageonly.strategy == "triage"
    sampled = ex.select_pages(
        world.project_id, world.revision_id, world.imageonly_doc, blind_sample=True
    )
    assert sampled.strategy == "blind_sample" and sampled.pages == [1, 2, 3]
    # a text document: no page list exists
    assert ex.select_pages(world.project_id, world.revision_id, world.perf_doc).strategy == "none"


def test_controls_are_opt_in(world: World) -> None:
    plan = PagePlan("scan", _sha(world, world.scan_doc), None, (1,), controls=(2,))
    ex = _extractor(world, FixtureProvider(lambda r, n: json_response([])), plans=(plan,))
    off = ex.select_pages(world.project_id, world.revision_id, world.scan_doc)
    on = ex.select_pages(world.project_id, world.revision_id, world.scan_doc, include_controls=True)
    assert off.pages == [1] and on.pages == [1, 2]


def test_f12_excluded(world: World) -> None:
    """The F-12 folder's completion reports print the F-11 wells: excluded with a reason, no
    model call, no candidate."""
    provider = FixtureProvider(lambda r, n: json_response([equip(world.wrong_doc, 2)]))
    ex = _extractor(world, provider, plans=())
    res = ex.run_document(
        world.project_id, world.revision_id, world.wrong_doc, subject_label="15/9-F-12"
    )
    assert res.excluded and res.exclusion_code == "document_excluded_wrong_subject"
    assert (
        res.scope is not None and res.scope.checked and "15/9-F-11" in " ".join(res.scope.printed)
    )
    assert res.summary is None and provider.calls == []
    assert world.scalar("select count(*) from extraction_candidate") == 0
    unit = world.rows(
        "select state, stop_reason, stop_detail from agent_work_unit where unit_key like 'extract-excluded:%'"
    )
    assert len(unit) == 1 and unit[0][0] == "failed"
    assert unit[0][1] == "document_excluded_wrong_subject" and "15/9-F-11" in unit[0][2]
    # idempotent: a second run records nothing new
    ex.run_document(world.project_id, world.revision_id, world.wrong_doc, subject_label="15/9-F-12")
    assert (
        world.scalar(
            "select count(*) from agent_work_unit where unit_key like 'extract-excluded:%'"
        )
        == 1
    )
    # the same file read for the wells it is about is not excluded
    ok = ex.run_document(
        world.project_id, world.revision_id, world.wrong_doc, subject_label="15/9-F-11 B"
    )
    assert not ok.excluded and ok.scope is not None and ok.scope.checked
    # the unit itself cannot attach F-11 wells either: no such wellbore in the project
    assert (
        world.scalar("select count(*) from extraction_candidate where wellbore_id is not null") == 0
    )


def test_scope_check_is_text_layer_only_and_never_a_pass_for_scans(world: World) -> None:
    ex = _extractor(world, FixtureProvider(lambda r, n: json_response([])), plans=())
    h = ex._harness
    scan = h.reader.require(world.project_id, world.revision_id, world.scan_doc)
    chk = check_document_scope(h, scan, "15/9-F-12")
    assert not chk.excluded and not chk.checked and "unchecked" in chk.detail
    assert not check_document_scope(h, scan, None).excluded  # no expectation: no check
    other = h.reader.require(world.project_id, world.revision_id, world.other_doc)
    assert check_document_scope(h, other, "15/9-F-99").checked
    assert check_document_scope(h, other, "15/9-F-77").excluded is True  # prints F-99 and F-98


def test_explicit_exclusion_is_recorded(world: World) -> None:
    provider = FixtureProvider(lambda r, n: json_response([]))
    ex = _extractor(
        world, provider, plans=(), excluded_documents={world.scan_doc: "owner: wrong well"}
    )
    res = ex.run_document(world.project_id, world.revision_id, world.scan_doc)
    assert res.excluded and res.exclusion_code == "document_excluded" and provider.calls == []
    row = world.rows(
        "select stop_reason, stop_detail from agent_work_unit where unit_key like 'extract-excluded:%'"
    )
    assert row[0][0] == "document_excluded" and "owner: wrong well" in row[0][1]


def test_prompt_id_and_inputs_feed_the_cache_key(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FixtureProvider(lambda r, n: json_response([equip(world.pdf_doc, 1)]))
    h = world.harness(provider)
    doc = h.reader.require(world.project_id, world.revision_id, world.pdf_doc)

    def req(**kw: Any) -> UnitRequest:
        base: dict[str, Any] = {"kind": "equipment", "page": 1}
        base.update(kw)
        return UnitRequest(
            world.project_id, world.revision_id, world.pdf_doc, EQUIPMENT_QUESTION, **base
        )

    base = h.cache_key(req(), doc)
    assert h.cache_key(req(kind="page_read"), doc) != base
    assert h.cache_key(req(rotation=90), doc) != base
    assert h.cache_key(req(document_subject="15/9-F-99"), doc) != base
    assert h.cache_key(req(page=2), doc) != base
    monkeypatch.setattr(harness_module, "EQUIPMENT_PROMPT_VERSION", "eq-prompt-3")
    assert h.cache_key(req(), doc) != base  # a new prompt never reuses a stored result
    monkeypatch.undo()
    # unchanged inputs reuse the stored result: no second provider call
    out1 = h.run_unit(req())
    out2 = h.run_unit(req())
    assert out1.state == "succeeded" and not out1.cache_hit and out2.cache_hit
    assert len(provider.calls) == 1
    assert eq_rows(world)[0]["prompt"] == EQUIPMENT_PROMPT_VERSION


def test_prompt_content() -> None:
    from fieldlens.candidates.equipment_prompt import EQUIPMENT_SYSTEM_PROMPT_TWO_PASS

    p = EQUIPMENT_SYSTEM_PROMPT
    for needle in ("never invent", '{"candidates":[]}', "untrusted"):
        assert needle in p, needle
    assert "rotation" not in p  # the plan supplies rotation; no invitation by default
    for needle in ("rotation", "90, 180 or 270"):  # the opt-in two-pass prompt keeps it
        assert needle in EQUIPMENT_SYSTEM_PROMPT_TWO_PASS, needle
    for category in EQUIPMENT_CATEGORIES:
        assert category in p
    assert "drill_bit" not in p and len(EQUIPMENT_CATEGORIES) == 10
    assert "no such equipment" in EQUIPMENT_QUESTION


def test_page_concurrency_default_three_and_run_is_fast(world: World) -> None:
    plan = PagePlan("big", _sha(world, world.big_doc), None, tuple(range(2, 14)))
    provider = FixtureProvider(lambda r, n: json_response([]), latency_s=0.05)
    ex = _extractor(world, provider, plans=(plan,))
    res = ex.run_document(world.project_id, world.revision_id, world.big_doc)
    assert res.summary is not None and res.summary.state == "succeeded"
    assert len(res.summary.pages) == 12 and 2 <= provider.max_in_flight <= 3
    assert res.summary.wall_s < 12 * 0.05 + 3  # parallel, not sequential, plus overhead
    assert ex._harness.config.effort == "low" and ex._harness.config.read_concurrency == 3

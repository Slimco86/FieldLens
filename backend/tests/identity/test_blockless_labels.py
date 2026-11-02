"""TASK-061 (owner decision D9): a block-less label is a wellbore named as written.

Resolver identity, exposure/start gate and merge-proposal eligibility against PostgreSQL with
synthetic records. Offline: scripted stub provider only; nothing here merges without acceptance."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fieldlens.assistant.stub import text_response
from fieldlens.identity.resolver import resolve_project
from fieldlens.merge_proposals.blocking import build_dataset
from fieldlens.merge_proposals.designator import designator_pattern, extract_designator
from fieldlens.persistence.session import session_scope
from tests.identity.test_wellbore_exposure import (
    _get,
    _header,
    _resolve,
    _stations,
    _subj,
    _surface,
)
from tests.merge_proposals.support import FakeSource, group, make_proposer
from tests.retrieval.support import World, attr, rec


def _gate(world: World, pid: str) -> dict[str, Any]:
    return _get(world, f"/api/v1/projects/{pid}/identity/start-gate")


def _statoil_like(world: World, pid: str, label: str, *, located: bool = True) -> None:
    records = [_header(label, label, None), *_stations(label, label)]
    if located:
        records.append(_surface(label, label, 435000.0, 6478000.0))
    world.add_doc(pid, f"{label.replace('/', '_').replace(' ', '_')}.txt", records)


def test_blockless_labels_alone_are_wellbores_named_as_written(world: World) -> None:
    pid = world.project()
    _statoil_like(world, pid, "F-12")
    _statoil_like(world, pid, "F-5")
    _resolve(world, pid)
    listing = _get(world, f"/api/v1/projects/{pid}/identity")
    assert [w["name"] for w in listing["wells"]] == ["F-12", "F-5"]
    names = sorted(b["name"] for w in listing["wells"] for b in w["wellbores"])
    assert names == ["F-12", "F-5"]
    assert listing["unresolved"] == [] and listing["unresolved_record_count"] == 0
    assert listing["resolved_current"] is True
    # records are linked; no block was invented anywhere
    assert (
        world.sql("SELECT count(*) FROM record_wellbore_link")[0][0]
        == listing["linked_record_count"]
    )
    assert all("/" not in str(r[0]) for r in world.sql("SELECT wellbore_key FROM wellbore"))
    # idempotent
    _resolve(world, pid)
    assert _get(world, f"/api/v1/projects/{pid}/identity")["wells"] == listing["wells"]


def test_blockless_trajectory_opens_the_gate_with_block_not_stated(world: World) -> None:
    pid = world.project()
    _statoil_like(world, pid, "F-12")
    _statoil_like(world, pid, "F-5", located=False)
    _resolve(world, pid)
    gate = _gate(world, pid)
    assert gate["can_start"] is True and gate["unmet"] == []
    assert len(gate["qualifying_wellbore_ids"]) == 2
    per = {w["wellbore_name"]: w for w in gate["wellbores"]}
    for name in ("F-12", "F-5"):
        codes = {x["code"] for x in per[name]["warnings"]}
        assert {"BLOCK_NOT_STATED", "SURVEY_STATUS_UNSTATED"} <= codes
        assert per[name]["trajectory_validated"] is True
    assert per["F-12"]["location_state"] == "located"
    assert per["F-5"]["unlocated"] is True
    assert "SURFACE_LOCATION_MISSING" in {x["code"] for x in per["F-5"]["warnings"]}
    assert "BLOCK_NOT_STATED" in {x["code"] for x in gate["warnings"]}


def test_qualified_wellbore_has_no_block_warning_and_nothing_identified_still_blocks(
    world: World,
) -> None:
    pid = world.project()
    assert _gate(world, pid)["unmet"][0]["code"] == "NO_WELLBORE_IDENTIFIED"
    _statoil_like(world, pid, "NO 15/9-F-12")
    _resolve(world, pid)
    gate = _gate(world, pid)
    assert gate["can_start"] is True
    assert "BLOCK_NOT_STATED" not in {x["code"] for w in gate["wellbores"] for x in w["warnings"]}


def _pair_project(world: World) -> tuple[str, UUID]:
    pid = world.project()
    doc = world.add_doc(
        pid,
        "both.txt",
        [
            *_stations("F-12", "F-12"),
            rec("note", _subj("NO 15/9-F-12", "15/9-F-12"), [attr("note.text", "x")]),
            rec("note", _subj("NO 15/9-F-14", "15/9-F-14"), [attr("note.text", "x")]),
            rec("note", _subj("F-12 A", "F-12 A"), [attr("note.text", "x")]),
        ],
    ).document_id
    _resolve(world, pid)
    return pid, doc


def test_unqualified_never_merges_silently_and_is_a_candidate(world: World) -> None:
    pid, _ = _pair_project(world)
    listing = _get(world, f"/api/v1/projects/{pid}/identity")
    bores = sorted(b["name"] for w in listing["wells"] for b in w["wellbores"])
    assert bores == ["15/9-F-12", "15/9-F-14", "F-12", "F-12 A"], "separate, not joined"
    with session_scope(world.factory) as s:
        ds = build_dataset(s, UUID(pid))
    pairs = {(b.target.key, c.party.key) for b in ds.blocks for c in b.members}
    # proposed once, qualified wellbore as the target; same-designator only
    assert ("15/9-F-12", "F-12") in pairs
    assert ("F-12", "15/9-F-12") not in pairs
    assert not any("F-14" in t + m for t, m in pairs if "F-12" in t + m)
    # the suffixed bore never pairs with the base bore (G4)
    assert ("15/9-F-12", "F-12 A") not in pairs and ("F-12", "F-12 A") not in pairs
    block = next(b for b in ds.blocks if b.target.key == "15/9-F-12")
    assert any(c.party.key == "F-12 A" for c in block.family)
    assert block.allow_short_target is True, "a block-less wellbore is not another block"


def test_blockless_designator_is_not_a_fragment_of_a_qualified_one() -> None:
    d = extract_designator("F-12")
    assert d is not None and d.block is None
    pattern = designator_pattern(d, allow_short=False)
    assert pattern.search("see f-12 here") and not pattern.search("see 15/9-f-12 here")
    assert not pattern.search("see 15/09-f-12 here")


def test_accept_unifies_and_revert_is_id_exact(world: World) -> None:
    from tests.merge_proposals.test_merge_proposals import _decide, _run, _url

    pid, doc = _pair_project(world)
    with session_scope(world.factory) as s:
        ds = build_dataset(s, UUID(pid))
    idx = next(i for i, b in enumerate(ds.blocks) if b.target.key == "15/9-F-12")
    block = ds.blocks[idx]
    ref = next(i + 1 for i, c in enumerate(block.members) if c.party.key == "F-12")
    quote = "Well F-12 is the same wellbore as 15/9-F-12."
    source = FakeSource(world, {doc: quote})
    proposer, provider = make_proposer(world, source, [])
    world.api.client.app.state.merge_proposer = proposer
    from tests.merge_proposals.test_merge_proposals import _ev

    provider._script.append(
        text_response(group(f"b{idx + 1}", "t", [f"m{ref}"], [_ev(doc, quote, f"m{ref}")]))
    )
    provider._script.extend([text_response('{"groups":[]}')] * 3)

    def rows() -> list[tuple[Any, ...]]:
        return world.sql(
            "SELECT w.well_key, w.well_id, b.wellbore_key, b.wellbore_id FROM wellbore b "
            "JOIN well w ON w.well_id = b.well_id ORDER BY b.wellbore_key"
        )

    before = rows()
    run = _run(world, pid)
    assert run["proposals_created"] == 1, run
    assert rows() == before, "a proposal alone merges nothing"
    proposal = _get(world, _url(pid))["items"][0]
    assert proposal["status"] == "pending"
    assert _decide(world, pid, proposal["proposal_id"], "accept").status_code == 200
    after = rows()
    assert "F-12" not in [r[2] for r in after] and len(after) == len(before) - 1
    gate = _gate(world, pid)
    assert "15/9-F-12" in {
        w["wellbore_name"] for w in gate["wellbores"] if w["trajectory_validated"]
    }
    assert _decide(world, pid, proposal["proposal_id"], "revert").status_code == 200
    assert rows() == before


def test_quote_naming_only_the_qualified_spelling_does_not_support_the_blockless_member(
    world: World,
) -> None:
    from tests.merge_proposals.test_merge_proposals import _ev, _run

    pid, doc = _pair_project(world)
    with session_scope(world.factory) as s:
        ds = build_dataset(s, UUID(pid))
    idx = next(i for i, b in enumerate(ds.blocks) if b.target.key == "15/9-F-12")
    block = ds.blocks[idx]
    ref = next(i + 1 for i, c in enumerate(block.members) if c.party.key == "F-12")
    quote = "Only 15/9-F-12 is named here."
    source = FakeSource(world, {doc: quote})
    proposer, provider = make_proposer(world, source, [])
    world.api.client.app.state.merge_proposer = proposer
    provider._script.append(
        text_response(group(f"b{idx + 1}", "t", [f"m{ref}"], [_ev(doc, quote, f"m{ref}")]))
    )
    provider._script.extend([text_response('{"groups":[]}')] * 3)
    assert _run(world, pid)["proposals_created"] == 0
    with session_scope(world.factory) as s:
        resolve_project(s, UUID(pid))
    assert world.sql("SELECT count(*) FROM identity_merge")[0][0] == 0

"""TASK-086 (EXPLORE_POLISH lane A, A-1..A-5): S3 short-name matching on deterministic content
evidence. Fixture mirrors VOLVE: block-less bores ``F-5/F-12/F-14`` whose surveys are identical to
those of ``15/9-F-5/-12/-14`` but whose names never co-occur in one passage. PostgreSQL, scripted
fake provider only: no network, no Meta call, no spend."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest

from fieldlens.assistant.messages import Usage
from fieldlens.assistant.stub import text_response, truncated_response
from fieldlens.config import Settings
from fieldlens.identity.resolver import resolve_project
from fieldlens.merge_proposals import guards, proposer
from fieldlens.merge_proposals.blocking import build_dataset
from fieldlens.merge_proposals.content import (
    SURFACE_CONTRADICTORY,
    SURVEY_EXACT,
    SURVEY_STATIONS_MD,
    PartyContent,
    pair_evidence,
    survey_print,
)
from fieldlens.merge_proposals.designator import extract_designator
from fieldlens.merge_proposals.guards import Party, evaluate, failed, surface_check
from fieldlens.persistence.session import session_scope
from fieldlens.reconstruction.matching import MatchWellboresExecutor
from fieldlens.reconstruction.stages import StageContext
from tests.merge_proposals.support import FakeSource, count, make_proposer, subj
from tests.retrieval.support import World, attr, rec

SLOTS = {"F-5": 5, "F-12": 12, "F-14": 14}
SURFACE = {
    "F-5": (435052.4, 6478562.3),
    "F-12": (435050.9, 6478558.9),
    "F-14": (435050.2, 6478566.2),
}


def _stations(
    who: dict[str, Any], slot: int, n: int = 12, *, tweak: int = 0
) -> list[dict[str, Any]]:
    out = []
    for i in range(n):
        md, incl, azi = 100.0 * i, 2.0 + i + (tweak if i == n - 1 else 0), 40.0 + slot
        out.append(
            rec(
                "trajectory_station",
                who,
                [
                    attr("trajectory_station.md", str(md), "m", number=md, reference="RKB"),
                    attr("trajectory_station.incl", str(incl), "deg", number=incl),
                    attr(
                        "trajectory_station.azi",
                        str(azi),
                        "deg",
                        number=azi,
                        reference="grid north",
                    ),
                    *([attr("trajectory_station.tvd", "0", "m", number=0.0)] if i == 0 else []),
                ],
            )
        )
    return out


def _surface(who: dict[str, Any], e: float, n: float) -> dict[str, Any]:
    return rec(
        "well_surface_location",
        who,
        [
            attr("well_surface_location.easting", str(e), "m", number=e),
            attr("well_surface_location.northing", str(n), "m", number=n),
        ],
    )


def _volve(
    world: World,
    *,
    different: tuple[str, ...] = (),
    angles: tuple[str, ...] = (),
    far: tuple[str, ...] = (),
    qualified_surface: tuple[str, ...] = (),
) -> str:
    """Short bore documents (text survey + surface) and qualified bore documents (PDF survey)."""
    pid = world.project("VOLVE")
    for short, slot in SLOTS.items():
        s_who = subj(short, None)
        e, n = SURFACE[short]
        world.add_doc(
            pid, f"Volve F_{short}_ACTUAL.txt", [*_stations(s_who, slot), _surface(s_who, e, n)]
        )
        q_who = subj(f"NO 15/9-{short}", f"15/9-{short}")
        recs = _stations(
            q_who, slot, 11 if short in different else 12, tweak=3 if short in angles else 0
        )
        if short in far:
            recs.append(_surface(q_who, e + 900.0, n))
        elif short in qualified_surface:
            recs.append(_surface(q_who, e + 1.0, n))
        world.add_doc(pid, f"Standard Survey Report_{short}.pdf", recs)
    with session_scope(world.factory) as s:
        resolve_project(s, UUID(pid))
    return pid


def _proposer(world: World, script: list[Any], **kw: Any) -> Any:
    source = FakeSource(world, {})
    prop, provider = make_proposer(world, source, script, **kw)
    world.api.client.app.state.merge_proposer = prop
    return prop, provider


def _survey_groups(blocks: dict[str, str]) -> str:
    return json.dumps(
        {
            "groups": [
                {
                    "block": b,
                    "target": "t",
                    "members": ["m1"],
                    "evidence": [{"member": "m1", "kind": "survey_match"}],
                    "rationale": f"{name}: identical survey, same slot",
                }
                for b, name in blocks.items()
            ]
        }
    )


def _url(pid: str, tail: str = "") -> str:
    return f"/api/v1/projects/{pid}/merge-proposals{tail}"


def _run(world: World, pid: str) -> dict[str, Any]:
    r = world.api.client.post(_url(pid, "/runs"), json={"confirm": True}, headers=world.api.headers)
    assert r.status_code == 200, r.text
    return dict(r.json())


# --- A-1 ----------------------------------------------------------------------------------------


def test_a1_candidate_table_and_three_pending_proposals_with_content_evidence(world: World) -> None:
    pid = _volve(world)
    with world.factory() as s:
        ds = build_dataset(s, UUID(pid))
    assert {b.target.key for b in ds.blocks} == {"15/9-F-12", "15/9-F-14", "15/9-F-5"}
    for b in ds.blocks:
        (cand,) = b.members
        assert cand.party.key == b.target.key.removeprefix("15/9-")
        assert cand.evidence is not None and cand.evidence.survey == SURVEY_EXACT
        assert cand.evidence.same_slot and cand.evidence.same_suffix
    _, provider = _proposer(
        world,
        [
            text_response(
                _survey_groups({"b1": "F-12", "b2": "F-14", "b3": "F-5"}),
                usage=Usage(input_tokens=2000, output_tokens=300),
            )
        ],
    )
    run = _run(world, pid)
    assert run["state"] == "succeeded" and run["proposals_created"] == 3, run
    prompt = json.dumps([p for m in provider.calls[0].messages for p in [str(m)]])
    assert "survey_match" in prompt and "stations_md" in prompt  # rules mention both kinds
    assert '\\"survey\\":\\"exact\\"' in prompt or '"survey":"exact"' in prompt
    items = world.api.client.get(_url(pid)).json()["items"]
    assert len(items) == 3 and {i["status"] for i in items} == {"pending"}
    for item in items:
        assert item["acceptable"] is True and item["decided_by"] is None
        (member,) = item["members"]
        kinds = {e["evidence_kind"] for e in member["evidence"]}
        assert kinds == {"survey_match"}
        assert any(
            "97" not in e["quote"] and "12 stations" in e["quote"] for e in member["evidence"]
        )
        assert {g["code"] for g in item["guard_results"]} >= {"g7_evidence", "g8_surface_location"}
    assert count(world, "identity_merge") == 0  # never auto-applied


def test_a1_survey_match_not_in_the_table_is_dropped(world: World) -> None:
    pid = _volve(world, different=("F-14",))
    with world.factory() as s:
        ds = build_dataset(s, UUID(pid))
    f14 = next(b for b in ds.blocks if b.target.key == "15/9-F-14")
    assert f14.members[0].evidence is not None and f14.members[0].evidence.survey == "different"
    _proposer(world, [text_response(_survey_groups({"b1": "F-12", "b2": "F-14", "b3": "F-5"}))])
    run = _run(world, pid)
    assert run["proposals_created"] == 2
    assert run["drop_reasons"] == {"survey_match_unsupported": 1}


def test_survey_print_is_stable_and_needs_enough_stations() -> None:
    who = subj("F-5", None)
    doc = UUID(int=1)
    rows = [list(r["attributes"]) for r in _stations(who, 5)]
    a, b = survey_print(doc, rows), survey_print(doc, list(reversed(rows)))
    assert a is not None and a == b and a.stations == 12 and (a.md_min, a.md_max) == (0.0, 1100.0)
    assert survey_print(doc, rows[:5]) is None
    assert survey_print(doc, [list(r["attributes"]) for r in _stations(who, 5, tweak=1)]) != a


# --- A-2 ----------------------------------------------------------------------------------------


def test_a2_pure_guards_still_block() -> None:
    target = Party.wellbore(UUID(int=1), "15/9-F-5")

    def blocked(member: Party) -> set[str]:
        checks = evaluate(target, [member], [], in_project_keys={"15/9-F-5", member.key})
        return {c.code for c in failed(checks)}

    assert guards.G3 in blocked(Party.wellbore(UUID(int=2), "F-14"))  # different slot
    assert guards.G3 in blocked(Party.wellbore(UUID(int=3), "15/9-F-14"))
    assert guards.G4 in blocked(Party.wellbore(UUID(int=4), "15/9-F-5 A"))  # other bore/sidetrack
    assert guards.G4 in blocked(Party.wellbore(UUID(int=5), "F-5 T2"))
    assert guards.G5 in blocked(Party.label("f-5 planned", "F-5 planned"))  # planned vs as-built
    assert not blocked(Party.wellbore(UUID(int=6), "F-5"))
    assert extract_designator("15/9-F-5").slot == "F-5"


def test_a2_contradictory_surface_location_blocks(world: World) -> None:
    pid = _volve(world, far=("F-5",))
    with world.factory() as s:
        ds = build_dataset(s, UUID(pid))
    by = {b.target.key: b for b in ds.blocks}
    assert "15/9-F-5" not in by  # a contradicting short bore is never offered as a candidate
    near = PartyContent(surface=[(10.0, 20.0, "grid")])
    far = PartyContent(surface=[(910.0, 20.0, "grid")])
    ev = pair_evidence(
        Party.wellbore(UUID(int=1), "15/9-F-5"), near, Party.wellbore(UUID(int=2), "F-5"), far
    )
    assert ev.surface == SURFACE_CONTRADICTORY and not surface_check([ev]).passed
    assert surface_check([None]).passed


def test_a2_model_forced_contradictory_pair_is_stored_blocked(world: World) -> None:
    pid = _volve(world, far=("F-5",))
    world.add_doc(
        pid, "alias.txt", [rec("note", subj("Well F5 (Volve)", None), [attr("note.text", "x")])]
    )
    with session_scope(world.factory) as s:
        resolve_project(s, UUID(pid))
    with world.factory() as s:
        ds = build_dataset(s, UUID(pid))
    f5 = next(b for b in ds.blocks if b.target.key == "15/9-F-5")
    assert [c.party.name for c in f5.members] == ["Well F5 (Volve)"]
    assert [c.party.key for c in f5.family] == ["F-5"]
    forced = json.dumps(
        {
            "groups": [
                {
                    "block": "b3",
                    "target": "t",
                    "members": ["d1"],
                    "evidence": [{"member": "d1", "kind": "survey_match"}],
                    "rationale": "same survey",
                }
            ]
        }
    )
    _proposer(world, [text_response(forced)])
    run = _run(world, pid)
    assert run["proposals_created"] == 1
    (item,) = world.api.client.get(_url(pid)).json()["items"]
    assert item["status"] == "blocked" and item["acceptable"] is False
    assert {g["code"] for g in item["guard_results"] if not g["passed"]} == {"g8_surface_location"}
    r = world.api.client.post(
        _url(pid, f"/{item['proposal_id']}/accept"),
        json={"decided_by": "reviewer"},
        headers=world.api.headers,
    )
    assert r.status_code == 409 and count(world, "identity_merge") == 0


# --- A-3 ----------------------------------------------------------------------------------------


def _ctx(world: World, pid: UUID) -> StageContext:
    from uuid import uuid4

    return StageContext(
        factory=world.factory,
        settings=Settings(),
        project_id=pid,
        run_id=uuid4(),
        well_id=uuid4(),
        wellbore_id=uuid4(),
        wellbore_name="x",
        source_revision="r",
        previous={},
        checkpoint=lambda: None,
    )


def test_a3_empty_success_is_replanned_when_evidence_guard_or_prompt_changes(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid = _volve(world)
    prop, provider = _proposer(world, [])
    provider._script.extend([text_response('{"groups":[]}')] * 4)
    ex = MatchWellboresExecutor(prop)
    first = ex.run(_ctx(world, UUID(pid)))
    assert first.state == "succeeded" and first.counts["proposed"] == 0
    assert "the model reviewed 3 name group(s) and found no matches" in (first.message or "")
    assert len(provider.calls) == 1
    # unchanged inputs: not asked again, and the message says the MODEL found none (not "reused")
    again = ex.run(_ctx(world, UUID(pid)))
    assert len(provider.calls) == 1
    assert again.message is not None and again.message.startswith("the model found no matches")
    assert "unchanged" in again.message and "reused" not in again.message
    assert prop.explain(UUID(pid)).kind == "none_found"
    # prompt version change
    monkeypatch.setattr(proposer, "PROMPT_VERSION", "merge-proposal-test")
    assert prop.explain(UUID(pid)).kind == "recheck"
    assert "model prompt" in prop.explain(UUID(pid)).text
    assert prop.estimate(UUID(pid)).calls == 1
    ex.run(_ctx(world, UUID(pid)))
    assert len(provider.calls) == 2
    # guard version change
    monkeypatch.setattr(guards, "GUARD_VERSION", "merge-guards-test")
    assert "guard rules" in prop.explain(UUID(pid)).text
    ex.run(_ctx(world, UUID(pid)))
    assert len(provider.calls) == 3
    # candidate evidence change (a stated surface location now agrees on one pair)
    world.add_doc(
        pid,
        "extra.txt",
        [_surface(subj("NO 15/9-F-5", "15/9-F-5"), SURFACE["F-5"][0] + 1.0, SURFACE["F-5"][1])],
    )
    with session_scope(world.factory) as s:
        resolve_project(s, UUID(pid))
    plan = prop.explain(UUID(pid))
    assert plan.kind == "recheck" and "candidate evidence" in plan.text
    ex.run(_ctx(world, UUID(pid)))
    assert len(provider.calls) == 4
    assert prop.explain(UUID(pid)).kind == "none_found"


def test_a3_reused_message_when_pairs_already_proposed(world: World) -> None:
    pid = _volve(world)
    prop, provider = _proposer(world, [text_response(_survey_groups({"b1": "F-12"}))])
    ex = MatchWellboresExecutor(prop)
    first = ex.run(_ctx(world, UUID(pid)))
    assert first.counts["proposed"] == 1 and "1 match(es) proposed" in (first.message or "")
    # the model reviewed all three groups and chose one: unchanged inputs are not re-asked
    second = ex.run(_ctx(world, UUID(pid)))
    assert len(provider.calls) == 1 and second.counts["proposed"] == 0
    assert second.message is not None and "earlier results were reused" in second.message
    assert "found no matches" not in second.message


# --- A-4 ----------------------------------------------------------------------------------------


def test_a4_output_bound_grows_with_blocks_and_truncation_retry_stays(world: World) -> None:
    assert proposer.output_bound(8192, 1) == 8192 and proposer.output_bound(8192, 2) == 8192
    assert proposer.output_bound(8192, 4) == 10240
    pid = _volve(world)
    prop, provider = _proposer(
        world,
        [
            truncated_response('{"groups":[', Usage(input_tokens=900, output_tokens=5120)),
            text_response(_survey_groups({"b1": "F-12", "b2": "F-14", "b3": "F-5"})),
        ],
    )
    est = prop.estimate(UUID(pid))
    assert est.blocks == 3 and est.calls == 1 and est.upper_bound_usd > 0  # shown before a run
    run = _run(world, pid)
    assert run["state"] == "succeeded" and run["proposals_created"] == 3
    first, second = provider.calls
    assert (first.effort, first.max_output_tokens) == (
        "medium",
        9216,
    )  # 8192 + 1024 for the third block
    assert (second.effort, second.max_output_tokens) == ("minimal", 18432)  # doubled
    assert count(world, "spend_reservation") == 1


# --- A-5 ----------------------------------------------------------------------------------------


def _wellbore_id(world: World, pid: str, name: str) -> str:
    r = world.api.client.get(f"/api/v1/projects/{pid}/identity")
    assert r.status_code == 200, r.text
    return str(
        next(
            b["wellbore_id"] for w in r.json()["wells"] for b in w["wellbores"] if b["name"] == name
        )
    )


def test_a5_accept_gives_the_qualified_bore_the_surface_location(world: World) -> None:
    pid = _volve(world)
    _proposer(world, [text_response(_survey_groups({"b1": "F-12", "b2": "F-14", "b3": "F-5"}))])
    _run(world, pid)
    qualified = _wellbore_id(world, pid, "15/9-F-5")
    url = f"/api/v1/projects/{pid}/wellbores/{qualified}/trajectory"
    r0 = world.api.client.get(url)
    assert r0.status_code == 200, r0.text
    assert r0.json()["surface_location"] is None
    items = world.api.client.get(_url(pid)).json()["items"]
    prop_id = next(i["proposal_id"] for i in items if i["target"]["key"] == "15/9-F-5")
    r = world.api.client.post(
        _url(pid, f"/{prop_id}/accept"), json={"decided_by": "reviewer"}, headers=world.api.headers
    )
    assert r.status_code == 200, r.text
    sl = world.api.client.get(url).json()["surface_location"]
    assert sl is not None and sl["easting"] == SURFACE["F-5"][0]
    assert count(world, "identity_merge") == 1


def test_stations_md_level_is_reported_when_angles_differ(world: World) -> None:
    pid = _volve(world, angles=("F-14",))
    with world.factory() as s:
        ds = build_dataset(s, UUID(pid))
    f14 = next(b for b in ds.blocks if b.target.key == "15/9-F-14").members[0].evidence
    # the tweak changes incl of the last station only: md grid equal, values differ
    assert f14 is not None and f14.survey == SURVEY_STATIONS_MD and f14.survey_match

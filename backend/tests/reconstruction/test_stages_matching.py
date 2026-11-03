"""TASK-076 AG-1..AG-3: S2 reuse without respend, S3 proposals only (always ask), accept/revert
with the invalidation hook, and the guards that never allow a merge. Offline: scripted stub
provider and a fake reader; no network and no model call."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

from fieldlens.assistant.messages import Usage
from fieldlens.assistant.stub import text_response
from fieldlens.config import Settings
from fieldlens.merge_proposals import hooks
from fieldlens.persistence.session import session_scope
from fieldlens.reconstruction import invalidation
from fieldlens.reconstruction.matching import MatchWellboresExecutor
from fieldlens.reconstruction.reading import ReadFailure, ReadOutcome, ReadScope, ReadTarget
from fieldlens.reconstruction.reading_stage import ReadDocumentsExecutor
from fieldlens.reconstruction.stages import StageContext, StageStop
from tests.merge_proposals.support import FakeSource, count, group, make_proposer, seed
from tests.retrieval.support import World

ALIAS_TEXT = (
    "Daily report. Well F12 (Volve) is the same well as 15/9-F-12.\n"
    "Well F12A (Volve) is the same wellbore as 15/9-F-12 A.\n"
)


def _ctx(world: World, pid: str, *, stop: bool = False) -> StageContext:
    def checkpoint() -> None:
        if stop:
            raise StageStop("cancelled by the user")

    return StageContext(
        factory=world.factory,
        settings=Settings(),
        project_id=UUID(pid),
        run_id=uuid4(),
        well_id=uuid4(),
        wellbore_id=uuid4(),
        wellbore_name="x",
        source_revision="r",
        previous={},
        checkpoint=checkpoint,
    )


def _ev(doc: UUID, quote: str, member: str = "m1") -> dict[str, str]:
    return {"member": member, "document_id": str(doc), "quote": quote}


def _proposer(world: World, script_for: Any) -> Any:
    pid, docs = seed(world)
    source = FakeSource(world, {docs["alias"]: ALIAS_TEXT, docs["base"]: "wells"})
    proposer, provider = make_proposer(world, source, [])
    for item in script_for(docs):
        provider._script.append(item)
    return pid, docs, proposer, provider


def _good(docs: dict[str, UUID]) -> Any:
    return text_response(
        group(
            "b1",
            "t",
            ["m1"],
            [_ev(docs["alias"], "Well F12 (Volve) is the same well as 15/9-F-12")],
        ),
        usage=Usage(input_tokens=900, output_tokens=120),
    )


def _url(pid: str, tail: str = "") -> str:
    return f"/api/v1/projects/{pid}/merge-proposals{tail}"


def _decide(world: World, pid: str, proposal: str, action: str) -> Any:
    return world.api.client.post(
        _url(pid, f"/{proposal}/{action}"),
        json={"decided_by": "reviewer"},
        headers=world.api.headers,
    )


def _bores(world: World, pid: str) -> list[dict[str, Any]]:
    body = world.api.client.get(f"/api/v1/projects/{pid}/identity").json()
    return [b for w in body["wells"] for b in w["wellbores"]]


def _exposure_of(world: World, pid: str, name: str) -> dict[str, Any]:
    full = world.api.client.get(f"/api/v1/projects/{pid}/identity/exposure").json()
    return next(b for w in full["wells"] for b in w["wellbores"] if b["wellbore_name"] == name)


# -- AG-1: always ask ------------------------------------------------------------------------
def test_s3_only_proposes_then_accept_merges_and_revert_restores(world: World) -> None:
    pid, docs, proposer, _ = _proposer(world, lambda d: [_good(d), text_response('{"groups":[]}')])
    seen: list[hooks.MergeChange] = []
    hooks.register("test.recorder", lambda _s, change: seen.append(change))
    try:
        before = {b["name"] for b in _bores(world, pid)}
        result = MatchWellboresExecutor(proposer).run(_ctx(world, pid))
        assert result.state == "succeeded" and "for you to review" in (result.message or "")
        assert result.counts["proposed"] == 1 and result.counts["awaiting_review"] == 1
        # nothing merged: still the same wellbores, one pending proposal, no merge record
        assert {b["name"] for b in _bores(world, pid)} == before
        assert count(world, "identity_merge") == 0
        items = world.api.client.get(_url(pid)).json()["items"]
        assert [i["status"] for i in items] == ["pending"]
        assert items[0]["members"][0]["evidence"][0]["quote"] and items[0]["guard_results"]
        assert seen == []

        # idempotent re-run: the pair is already pending, nothing new is proposed or spent
        again = MatchWellboresExecutor(proposer).run(_ctx(world, pid))
        assert again.counts["proposed"] == 0 and again.counts["awaiting_review"] == 1

        proposal = items[0]["proposal_id"]
        assert _decide(world, pid, proposal, "accept").status_code == 200
        assert [c.kind for c in seen] == ["merge_applied"] and not seen[0].automatic
        assert count(world, "identity_merge") == 1
        assert not any("F12" in b["name"] for b in _bores(world, pid))
        merged = _exposure_of(world, pid, "15/9-F-12")
        assert [a["name"] for a in merged["merged_from"]] == [
            "well f12 (volve)"
        ]  # the stored (normalized) key
        assert merged["merged_from"][0]["proposal_id"] == proposal

        assert _decide(world, pid, proposal, "revert").status_code == 200
        assert [c.kind for c in seen] == ["merge_applied", "merge_reverted"]
        assert world.sql("SELECT count(*) FROM identity_merge WHERE reverted_at IS NULL")[0][0] == 0
        assert {b["name"] for b in _bores(world, pid)} == before
        assert _exposure_of(world, pid, "15/9-F-12")["merged_from"] == []
    finally:
        hooks.unregister("test.recorder")


def test_merge_hook_invalidates_finished_drafts(world: World) -> None:
    pid, docs, proposer, _ = _proposer(world, lambda d: [_good(d), text_response('{"groups":[]}')])
    invalidation.install()
    MatchWellboresExecutor(proposer).run(_ctx(world, pid))
    proposal = world.api.client.get(_url(pid)).json()["items"][0]["proposal_id"]
    bore = _bores(world, pid)[0]
    world.sql(
        "INSERT INTO reconstruction_estimate (project_id, total_estimated_usd, pricing_source,"
        " total_cap_usd, remaining_budget_usd) VALUES (:p, 0, 'x', 0, 0)",
        p=UUID(pid),
    )
    est = world.sql("SELECT estimate_id FROM reconstruction_estimate")[0][0]
    world.sql(
        "INSERT INTO reconstruction_run (project_id, estimate_id, well_id, wellbore_id,"
        " wellbore_name, status, source_revision, pricing_source, estimated_usd, confirmed_usd, summary, finished_at)"
        " VALUES (:p, :e, :w, :b, 'n', 'partial', repeat('a', 64), 'x', 0, 0, '{}'::jsonb, now())",
        p=UUID(pid),
        e=est,
        w=UUID(bore["well_id"]) if "well_id" in bore else uuid4(),
        b=UUID(bore["wellbore_id"]),
    )
    assert _decide(world, pid, proposal, "accept").status_code == 200
    row = world.sql("SELECT invalidated_reason FROM reconstruction_run")[0]
    assert row[0] == "merge_applied"
    assert _decide(world, pid, proposal, "revert").status_code == 200
    # an already-invalidated draft keeps its first reason
    assert world.sql("SELECT invalidated_reason FROM reconstruction_run")[0][0] == "merge_applied"


# -- AG-2: guards never merge ----------------------------------------------------------------
@pytest.mark.parametrize(
    ("member", "quote"),
    [
        ("d1", "Well F12A (Volve) is the same wellbore as 15/9-F-12 A"),  # sidetrack/parent
    ],
)
def test_guard_failures_are_never_auto_applied_or_acceptable(
    world: World, member: str, quote: str
) -> None:
    out = lambda d: [  # noqa: E731
        text_response(group("b1", "t", [member], [_ev(d["alias"], quote, member)])),
        text_response('{"groups":[]}'),
    ]
    pid, _, proposer, _ = _proposer(world, out)
    MatchWellboresExecutor(proposer).run(_ctx(world, pid))
    assert count(world, "identity_merge") == 0
    for item in world.api.client.get(_url(pid, "?status=blocked")).json()["items"]:
        assert item["acceptable"] is False
        r = _decide(world, pid, item["proposal_id"], "accept")
        assert r.status_code == 409
    assert count(world, "identity_merge") == 0


def test_unverified_quote_is_dropped_not_proposed(world: World) -> None:
    out = lambda d: [  # noqa: E731
        text_response(
            group("b1", "t", ["m1"], [_ev(d["alias"], "text that is not in the source")])
        ),
        text_response('{"groups":[]}'),
    ]
    pid, _, proposer, _ = _proposer(world, out)
    result = MatchWellboresExecutor(proposer).run(_ctx(world, pid))
    assert result.counts["proposed"] == 0 and result.counts["dropped"] >= 1
    assert count(world, "merge_proposal") == 0 and count(world, "identity_merge") == 0


def test_s3_without_a_provider_is_stubbed_and_proposes_nothing(world: World) -> None:
    pid, _ = seed(world)
    result = MatchWellboresExecutor(None).run(_ctx(world, pid))
    assert result.state == "stubbed" and "Stub run" in (result.message or "")
    assert count(world, "merge_proposal") == 0


def test_s3_provider_failure_is_a_soft_failure_that_keeps_stored_proposals(world: World) -> None:
    pid, docs, proposer, provider = _proposer(world, lambda d: [_good(d)])
    # second call has no scripted reply -> provider failure after one good proposal
    result = MatchWellboresExecutor(proposer).run(_ctx(world, pid))
    assert result.state in ("failed", "succeeded")
    if result.state == "failed":
        assert result.fatal is False and result.error_code
    assert count(world, "merge_proposal") >= 1


# -- S2: reuse, never respend ----------------------------------------------------------------
class _Reader:
    name = "fake-live"
    live = True
    usd_per_document = Decimal("0.25")

    def __init__(self, fail_on: int | None = None) -> None:
        self.read_calls: list[str] = []
        self._fail_on = fail_on

    def read(self, project_id: UUID, target: ReadTarget, checkpoint: Any) -> ReadOutcome:
        if self._fail_on is not None and len(self.read_calls) == self._fail_on:
            raise ReadFailure("read_provider_unavailable", "provider unavailable")
        self.read_calls.append(target.filename)
        return ReadOutcome(usd=Decimal("0.25"), pages=3)


def _targets(n: int) -> list[ReadTarget]:
    return [ReadTarget(uuid4(), f"doc{i}.pdf", f"k{i}", uuid4(), ()) for i in range(n)]


def test_s2_reads_only_new_documents_and_reports_reuse(world: World) -> None:
    pid, _ = seed(world)
    reader = _Reader()
    todo = _targets(2)
    scope = ReadScope(todo, reused=3)
    ex = ReadDocumentsExecutor(reader, 5, lambda _s, _p: scope)
    with session_scope(world.factory) as s:
        plan = ex.plan(s, UUID(pid))
    assert plan.availability == "will_run" and plan.new_work == 2 and plan.reused == 3
    assert plan.usd == Decimal("0.50")
    result = ex.run(_ctx(world, pid))
    assert result.state == "succeeded" and result.counts["read"] == 2
    assert result.counts["reused"] == 3 and result.usd == Decimal("0.50")
    # a later run in which every document now has a stored result reads and spends nothing
    done = ReadDocumentsExecutor(reader, 5, lambda _s, _p: ReadScope([], reused=5))
    again = done.run(_ctx(world, pid))
    assert again.state == "succeeded" and again.usd == 0 and len(reader.read_calls) == 2


def test_s2_stub_provider_is_stubbed_and_reads_nothing(world: World) -> None:
    pid, _ = seed(world)
    ex = ReadDocumentsExecutor(None, 5, lambda _s, _p: ReadScope(_targets(2), reused=0))
    with session_scope(world.factory) as s:
        assert ex.plan(s, UUID(pid)).availability == "stub"
    result = ex.run(_ctx(world, pid))
    assert result.state == "stubbed" and result.reason_code == "stub_provider"
    assert result.usd == 0


def test_s2_provider_failure_keeps_earlier_reads_and_is_not_fatal(world: World) -> None:
    pid, _ = seed(world)
    reader = _Reader(fail_on=1)
    ex = ReadDocumentsExecutor(reader, 5, lambda _s, _p: ReadScope(_targets(3), reused=0))
    result = ex.run(_ctx(world, pid))
    assert result.state == "failed" and result.fatal is False
    assert result.error_code == "read_provider_unavailable"
    assert result.counts["read"] == 1 and result.usd == Decimal("0.25")


def test_s2_cancellation_propagates(world: World) -> None:
    pid, _ = seed(world)
    ex = ReadDocumentsExecutor(_Reader(), 5, lambda _s, _p: ReadScope(_targets(2), reused=0))
    with pytest.raises(StageStop):
        ex.run(_ctx(world, pid, stop=True))


def test_stage_failure_never_reads_as_success_in_a_run(world: World) -> None:
    """A non-fatal S2 failure lets later stages run, and the run ends partial with the reason."""
    from fieldlens.reconstruction.stages import (
        AssembleExecutor,
        GatherExecutor,
        design_executor,
    )
    from tests.reconstruction.test_reconstruction_runs import (
        _detail,
        _drain,
        _install,
        _ready_project,
        _start,
    )

    pid, bore = _ready_project(world)
    s2 = ReadDocumentsExecutor(
        _Reader(fail_on=0), 5, lambda _s, _p: ReadScope(_targets(1), reused=0)
    )
    _install(
        world,
        [GatherExecutor(), s2, MatchWellboresExecutor(None), AssembleExecutor(), design_executor()],
    )
    run = _start(world, pid, bore)
    _drain(world)
    detail = _detail(world, pid, run["run_id"])
    states = {x["stage"]: x["state"] for x in detail["stages"]}
    assert detail["status"] == "partial" and detail["error_code"] == "read_provider_unavailable"
    assert states["extract"] == "failed" and states["assemble"] == "succeeded"
    assert detail["summary"] is not None


# -- D1: no respend ----------------------------------------------------------------------------
@pytest.mark.parametrize("answer", ["proposal", "no_match"])
def test_repeated_s3_runs_make_no_new_provider_calls(world: World, answer: str) -> None:
    pid, _, proposer, provider = _proposer(
        world,
        lambda d: (
            [_good(d) if answer == "proposal" else text_response('{"groups":[]}')]
            + [text_response('{"groups":[]}')] * 2
        ),
    )
    with session_scope(world.factory) as s:
        before = MatchWellboresExecutor(proposer).plan(s, UUID(pid))
    assert before.availability == "will_run" and before.new_work > 0 and before.usd > 0
    first = MatchWellboresExecutor(proposer).run(_ctx(world, pid))
    assert first.state == "succeeded"
    made = len(provider.calls)
    assert made >= 1
    for _ in range(3):  # re-runs, as one reconstruction run per wellbore would do
        with session_scope(world.factory) as s:
            plan = MatchWellboresExecutor(proposer).plan(s, UUID(pid))
        assert plan.new_work == 0 and plan.usd == 0  # the estimate matches what will run
        again = MatchWellboresExecutor(proposer).run(_ctx(world, pid))
        assert again.state == "succeeded" and again.usd == 0
        assert len(provider.calls) == made  # zero new calls on an unchanged project


def test_bulk_estimate_equals_actual_calls_and_pairs_are_filtered_before_the_call(
    world: World,
) -> None:
    pid, docs, proposer, provider = _proposer(
        world, lambda d: [_good(d)] + [text_response('{"groups":[]}')] * 2
    )
    per_call = proposer.estimate(UUID(pid)).max_reserved_usd_per_call
    est = proposer.estimate(UUID(pid))
    assert est.calls >= 1 and est.upper_bound_usd == per_call * est.calls
    # two wellbore runs of one bulk estimate, executed back to back: the model is called once
    executor = MatchWellboresExecutor(proposer)
    results = [executor.run(_ctx(world, pid)) for _ in range(2)]
    assert len(provider.calls) == est.calls
    assert results[1].usd == 0 and results[0].state == results[1].state == "succeeded"
    # a user rejection removes the pair; still no call (filtered before, not after)
    proposal = world.api.client.get(_url(pid)).json()["items"][0]["proposal_id"]
    assert _decide(world, pid, proposal, "reject").status_code == 200
    executor.run(_ctx(world, pid))
    assert len(provider.calls) == est.calls


def test_s3_cancel_is_honoured_before_the_call(world: World) -> None:
    pid, _, proposer, provider = _proposer(world, lambda d: [_good(d)])
    with pytest.raises(StageStop):
        MatchWellboresExecutor(proposer).run(_ctx(world, pid, stop=True))
    assert provider.calls == []

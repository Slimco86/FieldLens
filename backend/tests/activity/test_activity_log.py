"""AX-10 (TASK-038): persisted, project-scoped agent activity log: write service + read API.

Requirement links: every test name below carries ``ax10``; ``test_activity_log_persisted`` is the
spec's named check. PostgreSQL only, offline, no provider calls."""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from fieldlens.activity.service import (
    ActivityLogError,
    FenceLost,
    ScopeError,
    StepLimitExceeded,
    StepUsage,
    UnitConflict,
    UnitFinalized,
)
from tests.activity.conftest import World


def _detail(world: World, project: Any, unit_id: Any) -> dict[str, Any]:
    r = world.api.client.get(f"/api/v1/projects/{project.project_id}/agent-units/{unit_id}")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _start(world: World, key: str = "u1", question: str = "Which unit is depth in?") -> Any:
    return world.log.start_unit(world.a.project_id, world.a.revisions[0], key, question)


def test_activity_log_persisted_ax10(world: World) -> None:
    h = _start(world)
    link = world.a.link()
    world.log.append_step(
        h,
        "tool_call",
        "read lines 1-1 of the source",
        step_key="tool:1",
        tool_name="read_span",
        outcome="ok",
        detail={"lines": [1, 1]},
        evidence=[link],
        usage=StepUsage(
            input_tokens=100, cached_input_tokens=10, output_tokens=20, cost_usd=Decimal("0.000250")
        ),
    )
    world.log.append_step(
        h,
        "candidate",
        "depth unit proposed: ft",
        step_key="cand:1",
        detail={"candidate_state": "candidate", "value": "ft"},
        evidence=[link],
        usage=StepUsage(output_tokens=5, cost_usd=Decimal("0.000050")),
    )
    world.log.append_step(
        h, "validator", "unit is in the allowlist", step_key="val:1", outcome="passed"
    )
    world.log.finalize(h, "succeeded", "completed")

    body = _detail(world, world.a, h.unit_id)
    unit = body["unit"]
    assert unit["state"] == "succeeded" and unit["stop_reason"] == "completed"
    assert unit["question"] == "Which unit is depth in?"
    assert unit["source_revision_id"] == str(world.a.revisions[0])
    assert (unit["step_count"], unit["tool_call_count"], unit["candidate_count"]) == (3, 1, 1)
    assert unit["usage"] == {
        "input_tokens": 100,
        "cached_input_tokens": 10,
        "output_tokens": 25,
        "cost_usd": "0.000300",
    }
    steps = body["steps"]
    assert [s["step_no"] for s in steps] == [1, 2, 3]
    assert [s["kind"] for s in steps] == ["tool_call", "candidate", "validator"]
    assert steps[0]["tool_name"] == "read_span" and steps[0]["outcome"] == "ok"
    assert steps[0]["evidence"][0]["locator"]["line_start"] == 1
    assert steps[2]["outcome"] == "passed"
    assert not any("reasoning" in s for s in steps)  # no hidden reasoning field exists


def test_list_is_project_revision_state_scoped_and_paged_ax10(world: World) -> None:
    keys = {}
    for i, rev in enumerate([0, 0, 1]):
        h = world.log.start_unit(world.a.project_id, world.a.revisions[rev], f"k{i}", f"q{i}")
        keys[i] = h
    world.log.finalize(keys[0], "failed", "provider_error")
    world.log.start_unit(world.b.project_id, world.b.revisions[0], "k0", "other project")

    def ids(**params: Any) -> list[str]:
        r = world.api.client.get(world.url(world.a), params=params)
        assert r.status_code == 200, r.text
        return [i["question"] for i in r.json()["items"]]

    assert ids() == ["q2", "q1", "q0"]  # newest first; project B's unit never appears
    assert ids(source_revision_id=str(world.a.revisions[1])) == ["q2"]
    assert ids(state="failed") == ["q0"]
    assert ids(state="running", source_revision_id=str(world.a.revisions[0])) == ["q1"]
    first = world.api.client.get(world.url(world.a), params={"limit": 2}).json()
    assert [i["question"] for i in first["items"]] == ["q2", "q1"]
    second = world.api.client.get(
        world.url(world.a), params={"limit": 2, "cursor": first["page"]["next_cursor"]}
    ).json()
    assert [i["question"] for i in second["items"]] == ["q0"]
    assert second["page"]["next_cursor"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"limit": "x"},
        {"cursor": "not-a-cursor"},
        {"state": "done"},
        {"source_revision_id": "nope"},
    ],
)
def test_malformed_listing_params_are_422_ax10(world: World, params: dict[str, Any]) -> None:
    r = world.api.client.get(world.url(world.a), params=params)
    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cross_project_and_unknown_ids_are_404_ax10(world: World) -> None:
    h = _start(world)
    client = world.api.client
    assert client.get(world.url(world.b, f"/{h.unit_id}")).status_code == 404
    assert client.get(world.url(world.a, f"/{uuid4()}")).status_code == 404
    assert client.get(f"/api/v1/projects/{uuid4()}/agent-units").status_code == 404
    assert client.get(world.url(world.a, "/not-a-uuid")).status_code == 422
    assert client.get(world.url(world.b)).json()["items"] == []
    # read-only surface: no mutation verbs
    assert client.post(world.url(world.a), json={}, headers=world.api.headers).status_code == 405


def test_write_scope_is_enforced_ax10(world: World) -> None:
    with pytest.raises(ScopeError):  # revision of another project
        world.log.start_unit(world.a.project_id, world.b.revisions[0], "x", "q")
    with pytest.raises(ScopeError):  # unknown project
        world.log.start_unit(uuid4(), world.a.revisions[0], "x", "q")
    h = _start(world)
    with pytest.raises(ScopeError):  # document from another project
        world.log.append_step(h, "note", "n", step_key="n1", evidence=[world.b.link()])
    with pytest.raises(ScopeError):  # same project, different revision than the unit's
        world.log.append_step(h, "note", "n", step_key="n2", evidence=[world.a.link(1)])
    with pytest.raises(ScopeError):  # same key, different revision
        world.log.start_unit(world.a.project_id, world.a.revisions[1], "u1", "q")
    assert _detail(world, world.a, h.unit_id)["unit"]["step_count"] == 0


def test_interrupted_failed_cancelled_are_not_successful_ax10(world: World) -> None:
    hf = _start(world, "f")
    world.log.finalize(hf, "failed", "provider_timeout", "attempt 2 timed out")
    hc = _start(world, "c")
    world.log.finalize(hc, "cancelled", "user_cancelled")
    hi = _start(world, "i")
    assert world.log.recover_interrupted(world.a.project_id) == [hi.unit_id]
    states = {i["unit_key"]: i for i in world.api.client.get(world.url(world.a)).json()["items"]}
    assert {k: v["state"] for k, v in states.items()} == {
        "f": "failed",
        "c": "cancelled",
        "i": "interrupted",
    }
    assert states["i"]["stop_reason"] == "process_interrupted"
    assert states["f"]["stop_detail"] == "attempt 2 timed out"
    assert all(v["finished_at"] and v["stop_reason"] for v in states.values())
    assert (
        world.api.client.get(world.url(world.a), params={"state": "succeeded"}).json()["items"]
        == []
    )


def test_interrupted_unit_is_completed_by_fenced_retry_without_duplicates_ax10(
    world: World,
) -> None:
    h1 = _start(world)
    world.log.append_step(
        h1,
        "tool_call",
        "read page",
        step_key="tool:1",
        tool_name="read_span",
        usage=StepUsage(input_tokens=10, cost_usd=Decimal("0.1")),
    )
    assert world.log.recover_interrupted() == [h1.unit_id]  # simulated kill + restart
    assert world.log.recover_interrupted() == []  # idempotent
    with pytest.raises(FenceLost):  # the old worker wakes up late
        world.log.append_step(h1, "note", "late", step_key="late")
    with pytest.raises(FenceLost):
        world.log.finalize(h1, "succeeded", "completed")

    h2 = _start(world)  # retry with the same key resumes the same unit
    assert h2.unit_id == h1.unit_id and h2.resumed and h2.fence > h1.fence
    with pytest.raises(UnitConflict):  # a third attempt while h2 runs
        _start(world)
    replay = world.log.append_step(
        h2,
        "tool_call",
        "read page",
        step_key="tool:1",
        tool_name="read_span",
        usage=StepUsage(input_tokens=10, cost_usd=Decimal("0.1")),
    )
    assert replay.created is False and replay.step_no == 1
    world.log.append_step(h2, "candidate", "proposal", step_key="cand:1")
    world.log.finalize(h2, "succeeded", "completed")

    body = _detail(world, world.a, h1.unit_id)
    assert body["unit"]["state"] == "succeeded" and body["unit"]["attempt_count"] == 2
    assert body["unit"]["usage"]["input_tokens"] == 10  # replay did not double-count
    assert [(s["step_no"], s["kind"]) for s in body["steps"]] == [
        (1, "tool_call"),
        (2, "lifecycle"),
        (3, "lifecycle"),
        (4, "candidate"),
    ]
    assert "interrupted" in body["steps"][1]["summary"]
    assert "resumed" in body["steps"][2]["summary"]


def test_finalize_twice_and_append_after_final_are_refused_ax10(world: World) -> None:
    h = _start(world)
    world.log.finalize(h, "succeeded", "completed")
    with pytest.raises(UnitFinalized):
        world.log.finalize(h, "failed", "late_error")
    with pytest.raises(UnitFinalized):
        world.log.append_step(h, "note", "x", step_key="x")
    with pytest.raises(UnitFinalized):  # a finished unit is not restarted by its key
        _start(world)
    with pytest.raises(ActivityLogError):
        world.log.finalize(_start(world, "other"), "running", "nope")
    assert _detail(world, world.a, h.unit_id)["unit"]["state"] == "succeeded"


def test_concurrent_appends_keep_total_gapless_order_ax10(world: World) -> None:
    h = _start(world)
    errors: list[BaseException] = []

    def work(i: int) -> None:
        try:
            # two threads share each key: exactly one row per key must exist
            world.log.append_step(h, "note", f"n{i // 2}", step_key=f"k{i // 2}")
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(24)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    steps = _detail(world, world.a, h.unit_id)["steps"]
    assert [s["step_no"] for s in steps] == list(range(1, 13))
    assert len({s["summary"] for s in steps}) == 12


def test_step_limit_and_payload_bounds_ax10(world: World) -> None:
    h = _start(world)
    for i in range(190):
        world.log.append_step(h, "note", "n", step_key=f"s{i}")
    with pytest.raises(StepLimitExceeded):
        world.log.append_step(h, "note", "n", step_key="s190")
    assert world.log.recover_interrupted() == [h.unit_id]  # lifecycle marks still fit
    assert _start(world).resumed


def test_oversize_payloads_are_truncated_with_marker_ax10(world: World) -> None:
    h = _start(world, question="q" * 9000)
    world.log.append_step(
        h,
        "tool_call",
        "s" * 5000,
        step_key="big",
        tool_name="read_span",
        detail={
            "excerpt": "page text " * 2000,
            "rows": list(range(500)),
            "deep": {"a": {"b": {"c": {"d": 1}}}},
        },
    )
    world.log.append_step(
        h,
        "tool_call",
        "huge",
        step_key="huge",
        tool_name="t",
        detail={f"k{i}": "v" * 400 for i in range(50)},
    )
    body = _detail(world, world.a, h.unit_id)
    assert len(body["unit"]["question"]) < 2100 and "[truncated" in body["unit"]["question"]
    big, huge = body["steps"]
    assert big["truncated"] and "[truncated 4000 chars]" in big["summary"]
    assert len(big["detail"]["excerpt"]) < 600 and "[truncated" in big["detail"]["excerpt"]
    assert big["detail"]["rows"][-1].startswith("[truncated")
    assert huge["truncated"] and huge["detail"]["_truncated"] is True
    assert huge["detail"]["original_bytes"] > 8192


def test_secrets_are_never_persisted_ax10(world: World) -> None:
    secrets = [
        "sk-live-ABCDEF0123456789abcdef",
        "Bearer abcdefghijklmnop1234",
        "api_key=hunter2hunter2",
        "AKIAABCDEFGHIJKLMNOP",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abc",
        "postgres://user:pa55word@host/db",
        "Zm9vYmFyMTIzNDU2Nzg5MGFiY2RlZjEyMzQ1Njc4OQ",
        "-----BEGIN PRIVATE KEY-----MIIEvQ-----END PRIVATE KEY-----",
    ]
    h = world.log.start_unit(
        world.a.project_id, world.a.revisions[0], "sec", f"why {secrets[0]} is {secrets[1]}"
    )
    world.log.append_step(
        h,
        "tool_call",
        " ; ".join(secrets),
        step_key="s",
        tool_name="read_span",
        detail={
            "note": secrets,
            "password": "plainpw",
            "nested": {"Authorization": "x"},
            f"key {secrets[0]}": 1,
        },
    )
    keep = f"{uuid4()} {'a1' * 32}"  # identifiers and sha256 hashes survive
    world.log.append_step(h, "note", keep, step_key="keep")
    with world.api.client.app.state.session_factory() as s:
        dump = " ".join(
            str(r)
            for r in s.execute(
                text(
                    "SELECT question, summary, detail::text FROM agent_step, agent_work_unit WHERE agent_step.unit_id = agent_work_unit.unit_id"
                )
            ).all()
        )
    for secret in secrets:
        core = secret.split("=")[-1].split(" ")[-1].split(":")[-1]
        assert core not in dump, secret
    assert "plainpw" not in dump and "[redacted]" in dump
    kept = _detail(world, world.a, h.unit_id)["steps"][1]["summary"]
    assert kept == keep


def test_nul_and_odd_values_do_not_break_persistence_ax10(world: World) -> None:
    h = _start(world)
    world.log.append_step(
        h,
        "note",
        "a\x00b",
        step_key="nul",
        detail={"x\x00": "y\x00", "inf": float("inf"), "obj": object, "t": (1, 2)},
    )
    step = _detail(world, world.a, h.unit_id)["steps"][0]
    assert step["summary"] == "ab" and step["detail"]["inf"] is None and step["truncated"]
    for bad in ({"kind": "lifecycle"}, {"kind": "bogus"}, {"kind": "tool_call"}):
        with pytest.raises((ActivityLogError, ValueError)):
            world.log.append_step(h, bad["kind"], "s", step_key="bad")
    with pytest.raises(ActivityLogError):
        world.log.append_step(h, "note", "s", step_key="x" * 121)
    with pytest.raises(ActivityLogError):
        world.log.append_step(h, "note", "s", step_key="neg", usage=StepUsage(input_tokens=-1))


def test_database_constraints_back_the_service_ax10(world: World) -> None:
    h = _start(world)
    factory = world.api.client.app.state.session_factory
    bad_updates = [
        "UPDATE agent_work_unit SET state='failed'",  # terminal without stop reason
        "UPDATE agent_work_unit SET state='nope'",
        "UPDATE agent_work_unit SET step_count=201",
        "UPDATE agent_work_unit SET cost_usd=-1",
    ]
    for sql in bad_updates:
        with pytest.raises(IntegrityError), factory.begin() as s:
            s.execute(text(sql))
    with pytest.raises(IntegrityError), factory.begin() as s:  # duplicate step number
        for key in ("a", "b"):
            s.execute(
                text(
                    "INSERT INTO agent_step (project_id, unit_id, step_no, step_key, kind, summary) "
                    "VALUES (:p, :u, 1, :k, 'note', 's')"
                ),
                {"p": h.project_id, "u": h.unit_id, "k": key},
            )
    with pytest.raises(IntegrityError), factory.begin() as s:  # wrong project scope
        s.execute(
            text(
                "INSERT INTO agent_step (project_id, unit_id, step_no, step_key, kind, summary) "
                "VALUES (:p, :u, 1, 'a', 'note', 's')"
            ),
            {"p": world.b.project_id, "u": h.unit_id},
        )
    with pytest.raises(IntegrityError), factory.begin() as s:  # oversize payload
        s.execute(
            text(
                "INSERT INTO agent_step (project_id, unit_id, step_no, step_key, kind, summary, detail) "
                "VALUES (:p, :u, 1, 'a', 'note', 's', jsonb_build_object('x', repeat('x', 13000)))"
            ),
            {"p": h.project_id, "u": h.unit_id},
        )


def _link(world: World, locator: dict[str, Any]) -> Any:
    from fieldlens.contracts.evidence import EvidenceLink

    base = {
        "document_id": world.a.documents[0],
        "source_revision_id": world.a.revisions[0],
    }
    return EvidenceLink.model_validate({**base, "locator": {**base, **locator}})


def _stored_evidence(world: World, unit_id: Any) -> list[dict[str, Any]]:
    return list(_detail(world, world.a, unit_id)["steps"][0]["evidence"])


LOCATOR_CASES = [
    ("xml", "element_path"),
    ("xml", "namespace_uri"),
    ("xml", "attribute_name"),
    ("xlsx", "sheet"),
    ("xlsx", "cell_range"),
    ("pdf", "table_id"),
    ("pdf", "cell_id"),
    ("text", "column_name"),
    ("text", "las_section"),
    ("text", "las_mnemonic"),
]
_REQUIRED = {
    "xml": {"element_path": "/a"},
    "xlsx": {"sheet": "S", "cell_range": "A1"},
    "pdf": {"page": 3},
    "text": {"line_start": 2, "line_end": 4},
}


@pytest.mark.parametrize(("kind", "field"), LOCATOR_CASES)
def test_locator_text_is_redacted_and_bounded_ax10(world: World, kind: str, field: str) -> None:
    h = _start(world)
    secret = "/a/sk-abcdefghijklmnop1234567890 password=hunter2"
    link = _link(world, {"kind": kind, **_REQUIRED[kind], field: secret})
    world.log.append_step(h, "note", "n", step_key="a", evidence=[link])
    loc = _stored_evidence(world, h.unit_id)[0]["locator"]
    assert "sk-abcdefghijklmnop" not in loc[field] and "hunter2" not in loc[field]
    assert "[redacted]" in loc[field]
    big = _link(world, {"kind": kind, **_REQUIRED[kind], field: "x" * 5000})
    world.log.append_step(h, "note", "n2", step_key="b", evidence=[big])
    steps = _detail(world, world.a, h.unit_id)["steps"]
    assert len(steps[1]["evidence"][0]["locator"][field]) < 260
    assert "[truncated" in steps[1]["evidence"][0]["locator"][field] and steps[1]["truncated"]


def test_locator_identity_fields_stay_intact_ax10(world: World) -> None:
    h = _start(world)
    link = _link(
        world, {"kind": "pdf", "page": 7, "table_id": "t" * 500, "rect": [0.1, 0.1, 0.5, 0.5]}
    )
    world.log.append_step(h, "note", "n", step_key="a", evidence=[link])
    ev = _stored_evidence(world, h.unit_id)[0]
    assert ev["document_id"] == str(world.a.documents[0])
    assert ev["source_revision_id"] == str(world.a.revisions[0])
    loc = ev["locator"]
    assert (loc["kind"], loc["page"], loc["rect"]) == ("pdf", 7, [0.1, 0.1, 0.5, 0.5])
    assert loc["document_id"] == str(world.a.documents[0])


def test_oversize_evidence_raises_typed_error_ax10(world: World) -> None:
    from fieldlens.activity.service import EvidenceTooLarge

    h = _start(world)
    links = [
        _link(
            world,
            {
                "kind": "xml",
                "element_path": "p" * 3000,
                "source_uids": [f"{i}-" + "u " * 1500 for i in range(60)],
                "namespace_uri": "n" * 3000,
                "attribute_name": "q" * 3000,
            },
        )
        for _ in range(8)
    ]
    with pytest.raises(EvidenceTooLarge):
        world.log.append_step(h, "note", "n", step_key="a", evidence=links)
    five = [_link(world, {"kind": "xml", "element_path": "e" * 3000}) for _ in range(5)]
    world.log.append_step(h, "note", "n", step_key="b", evidence=five)  # bounded, so it fits
    assert _detail(world, world.a, h.unit_id)["unit"]["step_count"] == 1

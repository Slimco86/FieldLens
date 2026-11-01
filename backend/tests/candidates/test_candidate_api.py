"""AX-7 backend read API and the activity-log trail (AX-10 data); project scoping."""

from __future__ import annotations

import json
from uuid import uuid4

from tests.candidates.conftest import World
from tests.candidates.helpers import meas, page_item, run_cands
from tests.candidates.support import FixtureProvider, call_response, json_response


def _seed(world: World) -> None:
    run_cands(
        world,
        [
            meas(world),  # accepted
            meas(world, value_text="4165.00", quote="4165.00"),  # flagged (parsed conflict)
            meas(world, quote="9999"),  # rejected
        ],
    )
    run_cands(
        world,
        [page_item(world.scan_doc, 1, quote=None)],
        doc=world.scan_doc,
        kind="page_read",
        page=1,
        line_range=None,
        question="scan",
    )


def test_candidates_read_api(world: World) -> None:
    _seed(world)
    c, pid = world.api.client, str(world.project_id)
    r = c.get(f"/api/v1/projects/{pid}/extraction-candidates")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    items = r.json()["items"]
    assert sorted(i["state"] for i in items) == ["accepted", "candidate", "flagged", "rejected"]
    by_state = {i["state"]: i for i in items}
    # state, reason, validator outcome, locator and label are all present
    flagged = by_state["flagged"]
    assert flagged["reason_codes"] == ["parsed_conflict"]
    assert flagged["validation_state"] == "conflicting" and flagged["conflicts_with_record_id"]
    assert any(v["outcome"] == "flagged" for v in flagged["validator_results"])
    assert flagged["evidence"]["locator"]["kind"] == "text"
    assert flagged["label"] == "model-proposed, not accepted"
    assert by_state["accepted"]["label"] == "model-proposed, rule-validated"
    read = by_state["candidate"]
    assert read["label"] == "model-read, unverified" and read["method"] == "model_read"
    assert (
        read["evidence"]["locator"]["kind"] == "pdf" and read["evidence_class"] == "model_proposal"
    )
    assert read["validation_state"] == "unverified"
    # filters and per-document listing
    only = c.get(f"/api/v1/projects/{pid}/extraction-candidates?state=accepted").json()["items"]
    assert [i["state"] for i in only] == ["accepted"]
    doc = c.get(f"/api/v1/projects/{pid}/documents/{world.scan_doc}/extraction-candidates").json()[
        "items"
    ]
    assert [i["state"] for i in doc] == ["candidate"]
    by_method = c.get(f"/api/v1/projects/{pid}/extraction-candidates?method=model_read").json()
    assert len(by_method["items"]) == 1
    # cursor paging
    first = c.get(f"/api/v1/projects/{pid}/extraction-candidates?limit=3").json()
    assert len(first["items"]) == 3 and first["page"]["next_cursor"]
    rest = c.get(
        f"/api/v1/projects/{pid}/extraction-candidates?limit=3&cursor={first['page']['next_cursor']}"
    ).json()
    ids = {i["candidate_id"] for i in first["items"]} | {i["candidate_id"] for i in rest["items"]}
    assert len(ids) == 4 and rest["page"]["next_cursor"] is None


def test_candidates_are_project_scoped(world: World) -> None:
    _seed(world)
    c = world.api.client
    other = world.api.project("Other")
    assert c.get(f"/api/v1/projects/{other}/extraction-candidates").json()["items"] == []
    miss = c.get(f"/api/v1/projects/{other}/documents/{world.perf_doc}/extraction-candidates")
    assert miss.status_code == 404  # a document of another project does not exist here
    assert c.get(f"/api/v1/projects/{uuid4()}/extraction-candidates").status_code == 404
    assert (
        c.get(f"/api/v1/projects/{world.project_id}/extraction-candidates?state=bogus").status_code
        == 422
    )
    assert (
        c.get(f"/api/v1/projects/{world.project_id}/extraction-candidates?limit=0").status_code
        == 422
    )


def test_activity_log_persisted(world: World) -> None:
    """Question, ordered steps, tool calls, candidates, validator outcomes, usage, stop reason."""
    me = str(world.perf_doc)

    def respond(req: object, n: int) -> object:
        if n == 1:
            return call_response("read_table", {"document_id": me, "start": 0, "count": 2})
        return json_response([meas(world)])

    out, _ = run_cands(world, [], provider=FixtureProvider(respond), question="What is top MD?")
    assert out.state == "succeeded"
    r = world.api.client.get(f"/api/v1/projects/{world.project_id}/agent-units/{out.unit_id}")
    detail = r.json()
    unit = detail["unit"]
    assert unit["question"] == "What is top MD?" and unit["state"] == "succeeded"
    assert unit["stop_reason"] == "completed" and unit["candidate_count"] == 1
    assert unit["tool_call_count"] >= 2 and unit["usage"]["input_tokens"] == 2400
    kinds = [s["kind"] for s in detail["steps"]]
    assert kinds[0] == "tool_call" and "model_turn" in kinds and kinds[-1] == "candidate"
    assert [s["step_no"] for s in detail["steps"]] == list(range(1, len(kinds) + 1))
    cand = detail["steps"][-1]
    assert cand["outcome"] == "passed" and "locator" in cand["evidence"][0]
    assert any("passed" in v for v in cand["detail"]["validators"])
    blob = json.dumps(detail)
    assert "reasoning" not in blob.lower() and "opaque" not in blob.lower()

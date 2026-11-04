"""Processing-run contract tests (PF-1, PF-2, PF-3, PF-10). Stub provider only: nothing here can
spend or reach a network (the suite's network guard is active)."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.engine import URL

from fieldlens.contracts.processing import ProcessingFailureCode
from fieldlens.processing.steps import PageFailure
from tests.processing.conftest import World, build_world


def _err(response: Any) -> dict[str, Any]:
    return dict(response.json()["error"])


def _label(world: World, name: str, categories: list[str]) -> None:
    doc = world.docs[name]
    item = next(d for d in world.api.documents(world.project_id) if str(d["document_id"]) == doc)
    r = world.api.client.patch(
        f"/api/v1/projects/{world.project_id}/documents/{doc}/classification",
        json={
            "categories": categories,
            "tags": [],
            "expected_metadata_version": item["classification"]["metadata_version"],
        },
        headers=world.api.headers,
    )
    assert r.status_code == 200, r.text


def test_processing_runs_start_without_label(world: World) -> None:
    states = world.states()
    scan = states["scan.pdf"]
    assert scan["no_native_parser"] is True
    assert scan["state_text"] == "no native parser; model processing available, not started"
    assert scan["processable"] is True and scan["page_count"] == 2
    assert scan["user_labels"] == [] and scan["processing_status"] == "not_started"
    assert states["notes.txt"]["processable"] is True  # TASK-115: text documents read as sections
    assert states["notes.txt"]["unit"] == "section" and states["notes.txt"]["page_count"] == 1

    _label(world, "other.pdf", ["trajectory"])
    r = world.estimate("scan.pdf", "other.pdf")
    assert r.status_code == 201, r.text
    run = r.json()
    hints = {d["original_filename"]: d["label_hints"] for d in run["documents"]}
    assert hints == {"scan.pdf": [], "other.pdf": ["trajectory"]}  # labels are only hints
    assert world.confirm(run).status_code == 202
    assert world.drain() == 1

    done = world.get(run["run_id"])
    assert done["status"] == "succeeded" and done["project_id"] == world.project_id
    assert [d["state"] for d in done["documents"]] == ["processed", "processed"]
    assert [d["pages_done"] for d in done["documents"]] == [2, 3]
    assert len(world.provider.calls) == 5
    after = world.states()["scan.pdf"]
    assert after["processing_status"] == "processed"
    assert "no data was extracted" in after["state_text"]  # a stub run never looks like real work


def test_wrong_root_runner_leaves_confirmed_run_queued(world: World) -> None:
    """TASK-066 follow-up: a process whose storage root holds none of the database's originals
    must not claim (and fail) a confirmed processing run; the right-root runner finishes it."""
    from fieldlens.evidence.storage import BlobStore
    from fieldlens.processing.runtime import build_runtime

    run = world.estimate("scan.pdf").json()
    assert world.confirm(run).status_code == 202
    app = world.api.client.app
    foreign = build_runtime(
        app.state.session_factory,
        BlobStore(world.api.storage.parent / "foreign-root"),
        app.state.settings,
    )
    assert foreign.runner.run_once() is False
    assert world.get(run["run_id"])["status"] == "queued"
    assert world.drain() == 1
    assert world.get(run["run_id"])["status"] == "succeeded"


def test_processing_estimate_confirm(world: World) -> None:
    r = world.estimate("scan.pdf", "report.pdf")
    assert r.status_code == 201
    run = r.json()
    est = run["estimate"]
    assert run["status"] == "estimated" and est["route"] == "model" and est["provider"] == "stub"
    assert est["pages"] == 7 and est["estimated_input_tokens"] == 7 * 1600
    assert est["estimated_output_tokens"] == 7 * 400
    assert float(est["estimated_usd"]) == 7 * (1600 * 0.30 + 400 * 2.50) / 1e6
    assert est["pricing_source"] == "stub_illustrative"
    assert float(est["total_cap_usd"]) == 5.0
    assert float(est["remaining_budget_usd"]) == 5.0
    assert est["fits_budget"] is True and est["confirmable"] is True

    # Nothing is queued, run or spent before the separate confirm.
    assert world.drain() == 0 and world.provider.calls == []
    assert world.get(run["run_id"])["status"] == "estimated"
    assert world.sql("SELECT count(*) FROM spend_reservation")[0][0] == 0

    stale = world.confirm(run, estimated_usd="0.000001")
    assert stale.status_code == 409 and _err(stale)["details"]["reason"] == "estimate_mismatch"
    queued = world.confirm(run)
    assert queued.status_code == 202 and queued.json()["status"] == "queued"
    assert float(queued.json()["confirmed_usd"]) == float(est["estimated_usd"])
    again = world.confirm(run)  # replay is idempotent, not a second queueing
    assert again.status_code == 202 and again.json()["status"] == "queued"
    # a queued run holds its estimate against the remaining budget
    second = world.estimate("other.pdf").json()
    held = float(second["estimate"]["remaining_budget_usd"])
    assert abs(held - (5.0 - float(est["estimated_usd"]))) < 1e-6
    assert world.drain() == 1
    assert world.get(run["run_id"])["status"] == "succeeded"


def test_processing_estimate_over_budget_cannot_confirm(migrated_url: URL, tmp_path: Path) -> None:
    from decimal import Decimal

    world = build_world(
        migrated_url, tmp_path, processing_stub_input_usd_per_mtok=Decimal("100000")
    )
    run = world.estimate("report.pdf").json()
    assert run["estimate"]["fits_budget"] is False and run["estimate"]["confirmable"] is False
    r = world.confirm(run)
    assert r.status_code == 409 and _err(r)["details"]["reason"] == "budget_exceeded"
    assert world.get(run["run_id"])["status"] == "estimated"
    assert world.drain() == 0 and world.provider.calls == []


def test_processing_page_cap(migrated_url: URL, tmp_path: Path) -> None:
    world = build_world(migrated_url, tmp_path, processing_max_pages=3)
    r = world.estimate("report.pdf")  # 5 pages, cap 3
    assert r.status_code == 422
    refusal = _err(r)["details"]["refusals"][0]
    assert refusal["reason"] == "page_cap_exceeded"
    assert refusal["page_count"] == 5 and refusal["max_pages"] == 3
    assert "page range" in refusal["hint"]
    assert world.sql("SELECT count(*) FROM processing_run")[0][0] == 0  # nothing half-created

    too_wide = world.estimate("report.pdf", pages={"report.pdf": (1, 4)})
    assert too_wide.status_code == 422
    assert _err(too_wide)["details"]["refusals"][0]["reason"] == "range_exceeds_cap"
    beyond = world.estimate("report.pdf", pages={"report.pdf": (4, 9)})
    assert _err(beyond)["details"]["refusals"][0]["reason"] == "invalid_page_range"

    ok = world.estimate("report.pdf", pages={"report.pdf": (3, 5)})
    assert ok.status_code == 201 and ok.json()["estimate"]["pages"] == 3
    assert world.states()["report.pdf"]["over_page_cap"] is True
    run = ok.json()
    world.confirm(run)
    world.drain()
    assert world.provider.calls and {p for _, p in world.provider.calls} == {3, 4, 5}
    doc = world.get(run["run_id"])["documents"][0]
    assert doc["pages"] == {"page_start": 3, "page_end": 5} and doc["page_count"] == 5


def test_processing_selection_validation_and_scope(world: World) -> None:
    other_project = world.api.project("Other")
    unknown = world.api.client.post(
        f"/api/v1/projects/{other_project}/processing/runs/estimates",
        json={"documents": [{"document_id": world.docs["scan.pdf"]}]},
        headers=world.api.headers,
    )
    assert unknown.status_code == 422  # documents never cross project scope
    assert _err(unknown)["details"]["refusals"][0]["reason"] == "unknown_document"
    # TASK-115: notes.txt is a text document, no longer refused (see the state test above)
    assert world.states()["notes.txt"]["processable"] is True
    dup = world.api.client.post(
        f"{world.base}/runs/estimates",
        json={"documents": [{"document_id": world.docs["scan.pdf"]}] * 2},
        headers=world.api.headers,
    )
    assert dup.status_code == 422

    run = world.estimate("scan.pdf").json()
    foreign = world.api.client.get(
        f"/api/v1/projects/{other_project}/processing/runs/{run['run_id']}"
    )
    assert foreign.status_code == 404
    no_token = world.api.client.post(
        f"{world.base}/runs/{run['run_id']}/confirm",
        json={"estimated_usd": run["estimate"]["estimated_usd"]},
    )
    assert no_token.status_code == 403
    listing = world.api.client.get(f"{world.base}/runs").json()["items"]
    assert [i["run_id"] for i in listing] == [run["run_id"]]


def test_processing_idempotency_and_single_active_run(world: World) -> None:
    a = world.estimate("scan.pdf", idempotency_key="k1")
    b = world.estimate("scan.pdf", idempotency_key="k1")
    assert a.json()["run_id"] == b.json()["run_id"]
    clash = world.estimate("other.pdf", idempotency_key="k1")
    assert clash.status_code == 409 and _err(clash)["details"]["reason"] == "idempotency_conflict"

    first = a.json()
    second = world.estimate("scan.pdf").json()  # a plain estimate does not lock the document
    assert world.confirm(first).status_code == 202
    blocked = world.confirm(second)
    assert blocked.status_code == 409
    assert _err(blocked)["details"]["reason"] == "document_already_processing"
    assert world.estimate("scan.pdf").status_code == 409  # and a new estimate says so early
    assert world.get(second["run_id"])["status"] == "estimated"  # failed confirm changed nothing
    world.drain()
    assert world.confirm(second).status_code == 202  # free again once the first finished


def test_processing_failure_states(world: World) -> None:
    scan, report, other = (world.docs[n] for n in ("scan.pdf", "report.pdf", "other.pdf"))
    from uuid import UUID

    world.provider.fail(
        UUID(scan), 2, PageFailure(ProcessingFailureCode.PROVIDER_REFUSED, "declined"), once=True
    )
    world.provider.fail(
        UUID(report), 3, PageFailure(ProcessingFailureCode.PROVIDER_TRUNCATED, "cut off")
    )
    world.provider.fail(
        UUID(other), 1, PageFailure(ProcessingFailureCode.PROVIDER_ERROR, "boom"), once=True
    )
    run = world.estimate("scan.pdf", "report.pdf", "other.pdf").json()
    world.confirm(run)
    world.drain()
    out = world.get(run["run_id"])
    by_name = {d["original_filename"]: d for d in out["documents"]}
    assert out["status"] == "failed"  # nothing was processed: never success-shaped
    assert by_name["scan.pdf"]["state"] == "failed"
    assert (
        by_name["scan.pdf"]["failure_code"] == "provider_refused"
        and by_name["scan.pdf"]["retryable"]
    )
    assert by_name["report.pdf"]["failure_code"] == "provider_truncated"
    assert by_name["report.pdf"]["pages_done"] == 2  # partial progress is recorded, not "done"
    assert by_name["other.pdf"]["failure_code"] == "provider_error"
    assert all(d["state"] != "processed" for d in out["documents"])
    assert world.states()["scan.pdf"]["processing_status"] == "failed"
    assert world.states()["scan.pdf"]["retryable"] is True

    # Retry is a NEW estimate; nothing runs or spends until it is confirmed.
    calls = len(world.provider.calls)
    retry = world.retry(run["run_id"])
    assert retry.status_code == 201
    redo = retry.json()
    assert redo["status"] == "estimated" and redo["retry_of_run_id"] == run["run_id"]
    assert world.drain() == 0 and len(world.provider.calls) == calls
    del world.provider.failures[(UUID(report), 3)]
    world.confirm(redo)
    world.drain()
    final = world.get(redo["run_id"])
    assert final["status"] == "succeeded"
    assert all(d["state"] == "processed" for d in final["documents"])


def test_processing_partial_run(world: World) -> None:
    from uuid import UUID

    world.provider.fail(
        UUID(world.docs["scan.pdf"]), 1, PageFailure(ProcessingFailureCode.PROVIDER_ERROR, "x")
    )
    run = world.estimate("scan.pdf", "other.pdf").json()
    world.confirm(run)
    world.drain()
    out = world.get(run["run_id"])
    assert out["status"] == "partial" and out["error_code"] == "provider_error"
    assert world.retry(run["run_id"]).json()["estimate"]["pages"] == 2  # only the failed document


def test_processing_cancel(world: World) -> None:
    # estimated and queued runs cancel immediately and free their documents
    e = world.estimate("scan.pdf").json()
    c = world.cancel(e["run_id"])
    assert c.status_code == 200 and c.json()["status"] == "cancelled"
    assert world.confirm(e).status_code == 409
    q = world.estimate("scan.pdf").json()
    world.confirm(q)
    assert world.cancel(q["run_id"]).json()["status"] == "cancelled"
    assert world.drain() == 0 and world.provider.calls == []
    assert world.cancel(q["run_id"]).status_code == 200  # idempotent

    # a running run stops at the next page; unfinished documents never read as processed
    run = world.estimate("report.pdf", "other.pdf").json()
    world.confirm(run)

    def hook(task: Any, page: int) -> None:
        if page == 2 and str(task.document_id) == world.docs["report.pdf"]:
            assert world.cancel(run["run_id"]).status_code == 200

    world.provider.on_page = hook
    world.drain()
    out = world.get(run["run_id"])
    assert out["status"] == "cancelled" and out["cancel_requested"] is True
    assert all(d["state"] != "processed" for d in out["documents"])
    report = next(d for d in out["documents"] if d["original_filename"] == "report.pdf")
    assert report["state"] == "cancelled" and report["pages_done"] < 5 and report["retryable"]
    assert world.retry(run["run_id"]).status_code == 201
    done = world.get(run["run_id"])
    assert world.cancel(done["run_id"]).status_code == 200  # terminal cancelled: replay is fine


def test_processing_cancel_of_finished_run_is_refused(world: World) -> None:
    run = world.estimate("scan.pdf").json()
    world.confirm(run)
    world.drain()
    assert world.cancel(run["run_id"]).status_code == 409
    assert world.retry(run["run_id"]).status_code == 409  # nothing to retry


def test_processing_budget_stop_when_usage_exceeds_confirmed_estimate(world: World) -> None:
    from decimal import Decimal

    world.provider.usage_multiplier = Decimal(3)  # actual usage far above the estimate
    run = world.estimate("report.pdf", "other.pdf").json()
    world.confirm(run)
    world.drain()
    out = world.get(run["run_id"])
    assert out["status"] == "failed"
    assert out["error_code"] == "confirmed_estimate_exceeded"
    assert all(d["state"] in ("cancelled", "failed") and d["retryable"] for d in out["documents"])
    assert all(d["state"] != "processed" for d in out["documents"])
    assert len(world.provider.calls) < 8  # it stopped; no automatic restart
    assert world.drain() == 0


def test_processing_interrupted_run_is_never_successful(world: World) -> None:
    run = world.estimate("report.pdf", "scan.pdf").json()
    world.confirm(run)
    claim = world.rt.runner._claim()  # a worker takes the run and then dies
    assert claim is not None
    world.sql(
        "UPDATE processing_run_document SET state='running' WHERE state='pending' AND ordinal=0"
    )
    world.sql("UPDATE processing_run SET lease_expires_at = now() - interval '1 minute'")
    assert world.rt.runner.recover_once() == [claim.run_id]
    out = world.get(run["run_id"])
    assert out["status"] == "interrupted" and out["error_code"] == "interrupted"
    assert all(d["state"] == "interrupted" and d["retryable"] for d in out["documents"])
    assert world.states()["scan.pdf"]["processing_status"] == "interrupted"
    assert "not completed" in world.states()["scan.pdf"]["state_text"]
    assert world.drain() == 0  # no automatic restart, no spend
    redo = world.retry(run["run_id"]).json()
    assert redo["status"] == "estimated"
    world.confirm(redo)
    world.drain()
    assert world.get(redo["run_id"])["status"] == "succeeded"


def test_processing_crashed_step_is_explicit_failure(world: World) -> None:
    from uuid import UUID

    world.provider.crash_on[(UUID(world.docs["scan.pdf"]), 1)] = RuntimeError("secret detail")
    run = world.estimate("scan.pdf").json()
    world.confirm(run)
    world.drain()
    out = world.get(run["run_id"])
    assert out["status"] == "failed"
    doc = out["documents"][0]
    assert doc["failure_code"] == "provider_error" and "secret detail" not in str(out)


def test_processing_document_concurrency_is_bounded(migrated_url: URL, tmp_path: Path) -> None:
    world = build_world(migrated_url, tmp_path, processing_document_concurrency=2)
    lock = threading.Lock()
    active = {"now": 0, "max": 0}

    def hook(task: Any, page: int) -> None:
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        time.sleep(0.05)
        with lock:
            active["now"] -= 1

    world.provider.on_page = hook
    run = world.estimate("scan.pdf", "report.pdf", "other.pdf", "fourth.pdf").json()
    world.confirm(run)
    world.drain()
    assert world.get(run["run_id"])["status"] == "succeeded"
    assert active["max"] == 2


def test_processing_confirm_rejects_hostile_amounts(world: World) -> None:
    run = world.estimate("scan.pdf").json()
    url = f"{world.base}/runs/{run['run_id']}/confirm"
    hostile = [
        '"1e400"',
        "1e400",
        '"NaN"',
        '"Infinity"',
        '"-Infinity"',
        '"sNaN"',
        '"1e-400"',
        '"' + "9" * 5000 + '"',
        '"0.' + "0" * 5000 + '1"',
        "0",
        "-1",
        '"abc"',
        "null",
        "[]",
        "true",
    ]
    for raw in hostile:
        r = world.api.client.post(
            url,
            content=f'{{"estimated_usd": {raw}}}'.encode(),
            headers={**world.api.headers, "content-type": "application/json"},
        )
        assert r.status_code in (409, 422), (raw[:20], r.status_code)
    assert world.get(run["run_id"])["status"] == "estimated"  # nothing was queued or spent
    assert world.confirm(run).status_code == 202


def test_processing_confirm_service_guard_rejects_non_finite(world: World) -> None:
    from decimal import Decimal

    import pytest

    from fieldlens.contracts.errors import ContractError
    from fieldlens.persistence.session import session_scope
    from fieldlens.processing import service

    run = world.estimate("scan.pdf").json()
    app = world.api.client.app
    for bad in (Decimal("NaN"), Decimal("Infinity"), Decimal("1e400"), Decimal("-1")):
        with session_scope(app.state.session_factory) as s, pytest.raises(ContractError) as caught:
            service.confirm_run(
                s, app.state.settings, UUID(world.project_id), UUID(run["run_id"]), bad
            )
        assert caught.value.status_code == 409
    assert world.get(run["run_id"])["status"] == "estimated"


def test_processing_confirm_refuses_document_removed_after_estimate(world: World) -> None:
    run = world.estimate("scan.pdf", "other.pdf").json()
    gone = world.docs["scan.pdf"]
    world.sql(
        "UPDATE document_processing SET storage_state = 'failed' WHERE document_id = :d",
        d=UUID(gone),
    )
    r = world.confirm(run)
    assert r.status_code == 409, r.text
    err = _err(r)
    assert err["details"]["reason"] == "document_unavailable"
    assert err["details"]["document_ids"] == [gone]
    still = world.get(run["run_id"])
    assert still["status"] == "estimated"  # nothing queued, nothing reserved
    assert world.drain() == 0

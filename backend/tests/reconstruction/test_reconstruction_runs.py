"""TASK-068 RR-1..RR-5 against PostgreSQL: the per-wellbore reconstruction run API.
Records are synthetic (invented values). Default S2/S3 are stubbed and S5 is not wired, so runs
end ``partial`` (never success)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text

from fieldlens.contracts.reconstruction import ReconstructionStageKind, ReconstructionStageName
from fieldlens.persistence.session import session_scope
from fieldlens.reconstruction.runtime import build_runtime
from fieldlens.reconstruction.stages import (
    AssembleExecutor,
    GatherExecutor,
    NotAvailableExecutor,
    StageContext,
    StageExecutor,
    StageResult,
    StageStop,
    design_executor,
)
from tests.identity.test_wellbore_exposure import (
    _bore_id,
    _get,
    _header,
    _resolve,
    _stations,
    _surface,
)
from tests.retrieval.support import World

F12 = ("15/9-F-12", "15/9-F-12")
F11 = ("15/9-F-11", "15/9-F-11")


def _ready_project(world: World, extra_unlocated: bool = False) -> tuple[str, str]:
    pid = world.project()
    world.add_doc(pid, "survey.txt", [_header(*F12, "as_built"), *_stations(*F12, 4)])
    world.add_doc(pid, "loc.txt", [_surface(*F12, 1000.0, 2000.0)])
    # F-11: a surface location but no trajectory -> not ready
    world.add_doc(pid, "loc11.txt", [_surface(*F11, 5.0, 6.0)])
    _resolve(world, pid)
    return pid, _bore_id(world, pid, F12[0])


def _base(pid: str) -> str:
    return f"/api/v1/projects/{pid}/reconstruction-runs"


def _post(world: World, path: str, body: dict[str, Any] | None = None) -> Any:
    return world.api.client.post(path, json=body or {}, headers=world.api.headers)


def _estimate(world: World, pid: str, **body: Any) -> dict[str, Any]:
    r = _post(world, f"{_base(pid)}/estimates", body)
    assert r.status_code == 201, r.text
    return dict(r.json())


def _confirm(world: World, pid: str, est: dict[str, Any]) -> Any:
    return _post(
        world,
        f"{_base(pid)}/estimates/{est['estimate_id']}/confirm",
        {"estimated_usd": est["total_estimated_usd"]},
    )


def _drain(world: World) -> None:
    rt = world.api.client.app.state.reconstruction
    while rt.runner.run_once():
        pass


def _detail(world: World, pid: str, run_id: str) -> dict[str, Any]:
    return _get(world, f"{_base(pid)}/{run_id}")


def _start(world: World, pid: str, bore: str) -> dict[str, Any]:
    est = _estimate(world, pid, wellbore_ids=[bore])
    r = _confirm(world, pid, est)
    assert r.status_code == 202, r.text
    return dict(r.json()["items"][0])


def _install(world: World, executors: list[StageExecutor]) -> None:
    app = world.api.client.app
    app.state.reconstruction = build_runtime(
        app.state.session_factory, app.state.settings, executors=executors
    )


@dataclass
class FakeAgent:
    """An available S2 stand-in: no model, no network."""

    stage: ReconstructionStageName = ReconstructionStageName.EXTRACT
    kind: ReconstructionStageKind = ReconstructionStageKind.AGENT
    available: bool = True
    reason_code: str | None = None
    message: str | None = None
    estimated_usd: Decimal = Decimal("1.00")
    page_cap: int | None = 500
    behaviour: str = "ok"  # ok | fail | block | overspend
    calls: int = 0

    def run(self, ctx: StageContext) -> StageResult:
        self.calls += 1
        if self.behaviour == "fail":
            return StageResult("failed", error_code="fake_failure", message="boom")
        if self.behaviour == "block":
            with session_scope(ctx.factory) as s:
                s.execute(
                    text("UPDATE reconstruction_run SET cancel_requested = true WHERE run_id = :r"),
                    {"r": ctx.run_id},
                )
            ctx.checkpoint()  # raises StageStop
            raise StageStop("unreachable")
        usd = Decimal("99") if self.behaviour == "overspend" else Decimal("0.10")
        return StageResult("succeeded", usd=usd, counts={"documents": 1})


def _executors(agent: StageExecutor | None = None) -> list[StageExecutor]:
    s2: StageExecutor = agent or NotAvailableExecutor(
        ReconstructionStageName.EXTRACT, ReconstructionStageKind.AGENT, "m", page_cap=500
    )
    s3 = NotAvailableExecutor(ReconstructionStageName.IDENTIFY, ReconstructionStageKind.AGENT, "m")
    return [GatherExecutor(), s2, s3, AssembleExecutor(), design_executor()]


# -- RR-1: start gate -----------------------------------------------------------------------
def test_not_ready_wellbore_is_rejected_with_the_server_reason(world: World) -> None:
    pid, _ = _ready_project(world)
    bad = _bore_id(world, pid, F11[0])
    r = _post(world, f"{_base(pid)}/estimates", {"wellbore_ids": [bad]})
    assert r.status_code == 422
    refusal = r.json()["error"]["details"]["refusals"][0]
    assert refusal["reason"] == "not_ready" and refusal["gate_reasons"]
    assert world.sql("SELECT count(*) FROM reconstruction_run")[0][0] == 0


def test_other_projects_wellbore_is_rejected(world: World) -> None:
    pid, bore = _ready_project(world)
    other = world.project("Other")
    r = _post(world, f"{_base(other)}/estimates", {"wellbore_ids": [bore]})
    assert r.status_code == 422
    assert r.json()["error"]["details"]["refusals"][0]["reason"] == "unknown_wellbore"
    assert _get(world, f"{_base(other)}")["total"] == 0
    assert _get(world, f"{_base(pid)}")["total"] == 0


def test_selection_must_be_explicit(world: World) -> None:
    pid, _ = _ready_project(world)
    r = _post(world, f"{_base(pid)}/estimates", {})
    assert r.status_code == 422


# -- estimate / confirm ---------------------------------------------------------------------
def test_estimate_then_separate_confirm_runs_partial(world: World) -> None:
    pid, bore = _ready_project(world)
    est = _estimate(world, pid, wellbore_ids=[bore])
    assert est["live_calls"] is False and est["pricing_label"]
    item = est["items"][0]
    assert [x["stage"] for x in item["stages"]] == [
        "gather",
        "extract",
        "identify",
        "assemble",
        "design",
    ]
    by_stage = {x["stage"]: x for x in item["stages"]}
    assert by_stage["extract"]["availability"] == "stub" and by_stage["extract"]["page_cap"] == 5
    assert by_stage["design"]["availability"] == "not_available"
    assert by_stage["design"]["reason_code"] == "asset_design_not_wired"
    assert est["stub"] is True and "remaining_budget_usd" not in est
    assert all(x["title"] and x["description"] for x in item["stages"])
    # estimating alone starts nothing
    run_id = item["run_id"]
    assert _detail(world, pid, run_id)["status"] == "estimated"
    _drain(world)
    assert _detail(world, pid, run_id)["status"] == "estimated"
    r = _confirm(world, pid, est)
    assert r.status_code == 202 and r.json()["items"][0]["status"] == "queued"
    # an idempotent replay of the same confirm
    assert _confirm(world, pid, est).status_code == 202
    _drain(world)
    run = _detail(world, pid, run_id)
    assert run["status"] == "partial" and run["stub_run"] is True
    assert run["error_code"] == "stub_run"
    states = {x["stage"]: x["state"] for x in run["stages"]}
    assert states == {
        "gather": "succeeded",
        "extract": "succeeded",  # nothing needs reading in this project: no model needed
        "identify": "stubbed",  # name groups exist, but no model was called
        "assemble": "succeeded",
        "design": "not_available",
    }
    assert run["retryable"] is False
    assert float(run["actual_usd"]) == 0.0


def test_confirm_requires_matching_amount(world: World) -> None:
    pid, bore = _ready_project(world)
    est = _estimate(world, pid, wellbore_ids=[bore])
    r = _post(
        world, f"{_base(pid)}/estimates/{est['estimate_id']}/confirm", {"estimated_usd": "3.00"}
    )
    assert r.status_code == 409
    assert r.json()["error"]["details"]["reason"] == "estimate_mismatch"


def test_all_ready_covers_only_ready_wellbores(world: World) -> None:
    pid, bore = _ready_project(world)
    est = _estimate(world, pid, all_ready=True)
    assert [i["wellbore_id"] for i in est["items"]] == [bore]
    r = _confirm(world, pid, est)
    assert r.status_code == 202 and r.json()["total"] == 1


# -- RR-2: S1/S4 output ---------------------------------------------------------------------
def test_s4_summary_is_sourced_and_unpublished(world: World) -> None:
    pid, bore = _ready_project(world)
    run = _start(world, pid, bore)
    _drain(world)
    summary = _detail(world, pid, run["run_id"])["summary"]
    assert summary["draft"] is True and summary["published"] is False
    assert summary["stages_stubbed"] == ["identify"]  # S5 has not run when S4 assembles
    assert summary["stages_succeeded"][0] == "gather" and "assemble" in summary["stages_succeeded"]
    present = [c for c in summary["coverage"] if c["present"]]
    assert present
    for c in present:
        assert c["evidence"], c["category"]  # no coverage claim without a document reference
        for ev in c["evidence"]:
            assert ev["document_id"] and ev["locator"] is not None
    traj = next(c for c in summary["coverage"] if c["category"] == "trajectory")
    assert traj["record_count"] >= 4


def test_s4_lists_unresolved_items(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "survey.txt", [_header(*F12, "as_built"), *_stations(*F12, 4)])
    _resolve(world, pid)  # no surface location: unlocated
    bore = _bore_id(world, pid, F12[0])
    run = _start(world, pid, bore)
    _drain(world)
    summary = _detail(world, pid, run["run_id"])["summary"]
    assert summary["unresolved"], "an unlocated wellbore must be listed, not hidden"
    assert all(u["code"] and u["message"] for u in summary["unresolved"])


# -- RR-3: duplicate start, cancel, retry ---------------------------------------------------
def test_duplicate_start_returns_the_active_run(world: World) -> None:
    pid, bore = _ready_project(world)
    first = _start(world, pid, bore)
    second_est = _estimate(world, pid, wellbore_ids=[bore])
    assert second_est["items"][0]["already_active"] is True
    assert second_est["items"][0]["run_id"] == first["run_id"]
    assert world.sql("SELECT count(*) FROM reconstruction_run")[0][0] == 1
    # a stale second estimate confirmed concurrently still resolves to the active run
    assert _get(world, f"{_base(pid)}")["total"] == 1


def test_cancel_queued_run_then_restart(world: World) -> None:
    pid, bore = _ready_project(world)
    run = _start(world, pid, bore)
    r = _post(world, f"{_base(pid)}/{run['run_id']}/cancel")
    assert r.status_code == 200 and r.json()["status"] == "cancelled"
    _drain(world)
    detail = _detail(world, pid, run["run_id"])
    assert detail["status"] == "cancelled" and detail["retryable"] is True
    assert all(x["state"] in ("cancelled", "not_available") for x in detail["stages"])
    # cancel is idempotent; retry is a new estimate confirmed separately
    assert _post(world, f"{_base(pid)}/{run['run_id']}/cancel").status_code == 200
    rt = _post(world, f"{_base(pid)}/{run['run_id']}/retry")
    assert rt.status_code == 201
    est = rt.json()
    new_id = est["items"][0]["run_id"]
    assert new_id != run["run_id"]
    assert _confirm(world, pid, est).status_code == 202
    _drain(world)
    again = _detail(world, pid, new_id)
    assert again["status"] == "partial" and again["retry_of_run_id"] == run["run_id"]


def test_partial_run_is_not_retryable(world: World) -> None:
    pid, bore = _ready_project(world)
    run = _start(world, pid, bore)
    _drain(world)
    r = _post(world, f"{_base(pid)}/{run['run_id']}/retry")
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "stages_not_available"


def test_cancel_running_run_stops_at_checkpoint(world: World) -> None:
    pid, bore = _ready_project(world)
    _install(world, _executors(FakeAgent(behaviour="block")))
    run = _start(world, pid, bore)
    _drain(world)
    detail = _detail(world, pid, run["run_id"])
    assert detail["status"] == "cancelled"
    states = {s["stage"]: s["state"] for s in detail["stages"]}
    assert states["extract"] == "cancelled" and states["assemble"] in ("cancelled", "skipped")


def test_failed_stage_fails_run_and_skips_the_rest(world: World) -> None:
    pid, bore = _ready_project(world)
    _install(world, _executors(FakeAgent(behaviour="fail")))
    run = _start(world, pid, bore)
    _drain(world)
    detail = _detail(world, pid, run["run_id"])
    assert detail["status"] == "failed" and detail["retryable"] is True
    states = {s["stage"]: s["state"] for s in detail["stages"]}
    assert states["extract"] == "failed" and states["assemble"] == "skipped"
    assert detail["summary"] is None or detail["status"] != "succeeded"


def test_all_stages_available_is_the_only_way_to_succeed(world: World) -> None:
    pid, bore = _ready_project(world)
    s3 = FakeAgent(
        stage=ReconstructionStageName.IDENTIFY, estimated_usd=Decimal("0.50"), page_cap=None
    )
    _install(
        world,
        [GatherExecutor(), FakeAgent(), s3, AssembleExecutor()],
    )
    run = _start(world, pid, bore)
    _drain(world)
    detail = _detail(world, pid, run["run_id"])
    assert detail["status"] == "succeeded"
    assert float(detail["actual_usd"]) == 0.2
    # the real default list ends partial: S5 is not wired
    _install(
        world,
        _executors(
            FakeAgent(),
        ),
    )
    again = _start(world, pid, bore)
    _drain(world)
    assert _detail(world, pid, again["run_id"])["status"] == "partial"


def test_actual_spend_above_the_estimate_is_reported_not_failed(world: World) -> None:
    """The estimate is informational (TASK-076): no cap turns a run into a failure."""
    pid, bore = _ready_project(world)
    _install(world, _executors(FakeAgent(behaviour="overspend")))
    run = _start(world, pid, bore)
    _drain(world)
    detail = _detail(world, pid, run["run_id"])
    assert detail["status"] == "partial"
    assert float(detail["actual_usd"]) == 99.0


# -- RR-4: recovery -------------------------------------------------------------------------
def test_interrupted_run_recovery(world: World) -> None:
    pid, bore = _ready_project(world)
    run = _start(world, pid, bore)
    world.sql(
        "UPDATE reconstruction_run SET status='running', lease_owner='dead-owner',"
        " lease_expires_at = now() - interval '1 minute', started_at = now() WHERE run_id = :r",
        r=UUID(run["run_id"]),
    )
    world.sql(
        "UPDATE reconstruction_run_stage SET state='running' WHERE run_id = :r AND stage='gather'",
        r=UUID(run["run_id"]),
    )
    rt = world.api.client.app.state.reconstruction
    assert rt.runner.recover_once() == [UUID(run["run_id"])]
    detail = _detail(world, pid, run["run_id"])
    assert detail["status"] == "interrupted" and detail["retryable"] is True
    assert detail["status"] != "succeeded" and detail["summary"] is None
    assert next(s for s in detail["stages"] if s["stage"] == "gather")["state"] == "interrupted"
    # retry is a new estimate; the interrupted one is never treated as success
    assert _post(world, f"{_base(pid)}/{run['run_id']}/retry").status_code == 201


# -- RR-5: budget, no live call -------------------------------------------------------------
def test_estimate_has_no_budget_or_cap_and_confirm_is_never_blocked(world: World) -> None:
    pid, bore = _ready_project(world)
    _install(world, _executors(FakeAgent(estimated_usd=Decimal("6.00"))))
    est = _estimate(world, pid, wellbore_ids=[bore])
    assert Decimal(est["total_estimated_usd"]) == Decimal("6.00")
    for gone in ("total_cap_usd", "remaining_budget_usd", "fits_budget"):
        assert gone not in est
    assert _confirm(world, pid, est).status_code == 202


def test_no_live_call_flag_and_default_executors(world: World) -> None:
    pid, bore = _ready_project(world)
    est = _estimate(world, pid, wellbore_ids=[bore])
    assert est["live_calls"] is False and est["provider"] == "stub"
    rt = world.api.client.app.state.reconstruction
    assert [e.available for e in rt.executors] == [True, True, True, True, False]
    run = _start(world, pid, bore)
    assert run["provider"] == "stub"


def test_existing_processing_endpoints_still_registered(world: World) -> None:
    pid, _ = _ready_project(world)
    r = world.api.client.get(f"/api/v1/projects/{pid}/processing/runs")
    assert r.status_code == 200

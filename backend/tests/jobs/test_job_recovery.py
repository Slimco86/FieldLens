"""IN-4: interrupted attempts, fenced retry, cancellation, single heavy stage."""

from __future__ import annotations

import socket
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from fieldlens.jobs import repository as repo
from fieldlens.persistence.session import session_scope
from tests.upload_support import CSV, PDF, Api, make_api, make_pdf


def _dead_owner() -> str:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])  # noqa: S603
    proc.wait()
    return f"{socket.gethostname()}:{proc.pid}:deadbeef"


def _claim(api: Api, owner: str = "other-host:1:abc") -> repo.Claim:
    with session_scope(api.worker._factory) as s:
        claim = repo.claim_next(s, owner, 600)
    assert claim is not None
    return claim


def _expire(engine: Engine) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "update ingest_job_attempt set lease_expires_at = now() - interval '1 second' "
                "where status = 'running'"
            )
        )


def test_interrupted_attempt_is_requeued_with_new_fence_and_old_fence_is_dead(
    migrated_url: URL, engine: Engine, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    stale = _claim(api)
    assert stale.fence == 1
    _expire(engine)
    assert api.worker.run_once() is True  # recovers, then runs attempt 2 to completion
    job = api.job(pid, r["job_id"])
    assert job["status"] == "succeeded"
    assert [(a["attempt_no"], a["status"], a["fencing_token"]) for a in job["attempts"]] == [
        (1, "interrupted", 1),
        (2, "succeeded", 2),
    ]
    assert job["attempts"][0]["error_code"] == "attempt_interrupted"
    with session_scope(api.worker._factory) as s, pytest.raises(repo.FenceLost):
        repo.publish(s, stale)
    with session_scope(api.worker._factory) as s, pytest.raises(repo.FenceLost):
        repo.record_document(s, stale, uuid.uuid4(), "stored", None)
    with session_scope(api.worker._factory) as s:
        assert repo.heartbeat(s, stale, 600) is False


def test_dead_owner_is_recovered_without_waiting_for_lease(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    _claim(api, _dead_owner())
    assert api.worker.recover_once() == [uuid.UUID(r["job_id"])]
    assert api.job(pid, r["job_id"])["status"] == "queued"
    assert api.latest(pid) is None  # interrupted work is never success-shaped


def test_live_owner_lease_is_not_stolen(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    _claim(api, f"{socket.gethostname()}:1:abc")  # pid 1 is alive
    assert api.worker.recover_once() == []
    assert api.job(pid, r["job_id"])["status"] == "running"


def test_exhausted_retries_leave_job_interrupted_and_publish_nothing(
    migrated_url: URL, engine: Engine, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    for _ in range(2):
        _claim(api)
        _expire(engine)
        api.worker.recover_once()
    job = api.job(pid, r["job_id"])
    assert job["status"] == "interrupted" and job["error"]["code"] == "attempt_interrupted"
    assert [a["status"] for a in job["attempts"]] == ["interrupted", "interrupted"]
    assert api.latest(pid) is None
    rev = api.revisions(pid)[0]
    assert rev["status"] == "failed" and "retries exhausted" in rev["coverage"]["reasons"][0]
    assert api.worker.run_once() is False
    assert api.upload(pid, [("b.csv", CSV)]).status_code == 202  # project unblocked


def test_only_one_heavy_attempt_runs_at_a_time(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    p1, p2 = api.project("one"), api.project("two")
    api.upload(p1, [("a.pdf", PDF)])
    api.upload(p2, [("b.pdf", make_pdf("b"))])
    first = _claim(api)
    with session_scope(api.worker._factory) as s:
        assert repo.claim_next(s, "x:2:y", 600) is None
    assert first.attempt_no == 1


def test_cancel_queued_job_publishes_nothing(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    url = f"/api/v1/projects/{pid}/jobs/{r['job_id']}/cancel"
    cancel = api.client.post(url, headers=api.headers)
    assert cancel.status_code == 202 and cancel.json()["status"] == "cancelled"
    assert api.latest(pid) is None and api.worker.run_once() is False
    assert api.revisions(pid)[0]["status"] == "failed"
    assert "import_cancelled" in api.revisions(pid)[0]["coverage"]["reasons"][0]


def test_cancel_running_job_is_honoured_before_publication(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF), ("b.csv", CSV)]).json()
    claim = _claim(api)
    url = f"/api/v1/projects/{pid}/jobs/{r['job_id']}/cancel"
    cancel = api.client.post(url, headers=api.headers)
    assert cancel.json()["status"] == "running" and cancel.json()["cancel_requested"] is True
    api.worker._verify_all(claim, threading.Event())
    job = api.job(pid, r["job_id"])
    assert job["status"] == "cancelled" and job["attempts"][0]["status"] == "cancelled"
    assert api.latest(pid) is None
    states = {d["storage_state"] for d in api.documents(pid, r["source_revision_id"])}
    assert states == {"pending_verification"}
    again = api.client.post(url, headers=api.headers)
    assert again.status_code == 202 and again.json()["status"] == "cancelled"  # terminal: no-op


def test_cancelling_a_finished_job_changes_nothing(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.run_once()
    url = f"/api/v1/projects/{pid}/jobs/{r['job_id']}/cancel"
    out = api.client.post(url, headers=api.headers)
    assert out.json()["status"] == "succeeded" and api.latest(pid) == r["source_revision_id"]


def test_worker_thread_processes_jobs_and_stops(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path, job_poll_seconds=0.05)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.start()
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and api.job(pid, r["job_id"])["status"] != "succeeded":
            time.sleep(0.1)
    finally:
        api.worker.stop()
    job = api.job(pid, r["job_id"])
    assert job["status"] == "succeeded"
    assert job["progress"] == {"processed": 1, "total": 1, "unit": "document"}

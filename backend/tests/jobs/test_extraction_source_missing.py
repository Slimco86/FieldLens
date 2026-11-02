"""TASK-064/066: a stored original that is later unreadable must not leave a 'hash-verified'
badge with a silent re-run loop, and a process with the wrong storage root must not poison
documents that another process can read."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from tests.jobs.test_extraction_flow import _drain, _ingest, _report
from tests.test_profiles_sources import LAS
from tests.upload_support import TEXT, Api, make_api


def _blob(api: Api, doc: dict[str, object]) -> Path:
    sha = str(doc["sha256"])
    project = next((api.storage / "projects").iterdir())
    return project / "blobs" / sha[:2] / sha


def _setup(migrated_url: URL, tmp_path: Path) -> tuple[Api, str, str, Path, Path]:
    """Two stored documents; only the LAS original is lost (a healthy sibling stays readable)."""
    api = make_api(migrated_url, tmp_path / "root")
    pid, docs = _ingest(api, [("log.las", LAS.encode()), ("notes.txt", TEXT)])
    las = next(d for d in docs if d["original_filename"] == "log.las")
    assert all(d["storage_state"] == "stored" for d in docs)
    blob = _blob(api, las)
    moved = tmp_path / "elsewhere"
    shutil.move(str(blob), str(moved))
    return api, pid, str(las["document_id"]), blob, moved


def _state(api: Api, pid: str, did: str) -> object:
    return next(d for d in api.documents(pid) if str(d["document_id"]) == did)["storage_state"]


def test_runner_source_missing_flips_badge_and_rerun_refuses_with_reupload_guidance(
    migrated_url: URL, tmp_path: Path
) -> None:
    api, pid, did, _, _ = _setup(migrated_url, tmp_path)
    url = f"/api/v1/projects/{pid}/documents/{did}/extraction"
    assert _drain(api) == 2
    rep = _report(api, pid, did)
    assert rep["status"] == "failed"
    assert any(
        "source_missing" in i["message"] and "re-upload" in i["message"] for i in rep["issues"]
    )
    assert _state(api, pid, did) == "failed", "must not keep saying hash-verified"

    r = api.client.post(url + "?retry=true", headers=api.headers)
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "CONFLICT" and err["request_id"]
    assert err["details"]["reason"] == "source_unreadable"
    assert "re-upload" in err["message"]
    assert _drain(api) == 0, "no silent retry loop"


def test_rerun_re_resolves_and_recovers_when_original_is_readable_again(
    migrated_url: URL, tmp_path: Path
) -> None:
    api, pid, did, blob, moved = _setup(migrated_url, tmp_path)
    url = f"/api/v1/projects/{pid}/documents/{did}/extraction"
    _drain(api)
    assert _state(api, pid, did) == "failed"
    shutil.move(str(moved), str(blob))
    r = api.client.post(url + "?retry=true", headers=api.headers)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "queued"
    assert _drain(api) == 1
    assert _report(api, pid, did)["status"] == "succeeded"
    assert _state(api, pid, did) == "stored"


def test_worker_with_wrong_storage_root_does_not_poison_documents(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    """TASK-066 root cause: another process on the same database with another storage root
    claimed extraction work, found every original 'missing' and flagged healthy documents."""
    writer = make_api(migrated_url, tmp_path / "root-a")
    pid, docs = _ingest(writer, [("log.las", LAS.encode()), ("notes.txt", TEXT)])
    assert all(d["storage_state"] == "stored" for d in docs)
    foreign = make_api(migrated_url, tmp_path / "root-b")  # same DB, empty storage
    assert foreign.worker.extraction.run_once() is False, "must not claim with the wrong root"
    assert foreign.worker.run_once() is False
    with engine.connect() as c:
        failed = c.execute(
            text("select count(*) from extraction_run where status='failed'")
        ).scalar_one()
        bad = c.execute(
            text("select count(*) from document_processing where storage_state<>'stored'")
        ).scalar_one()
    assert failed == 0 and bad == 0
    assert _drain(writer) == 2  # the process that can read the originals handles them
    assert all(
        _report(writer, pid, str(d["document_id"]))["status"] in ("succeeded", "unsupported")
        for d in docs
    )


def test_wrong_root_does_not_fail_new_upload_verification(
    migrated_url: URL, tmp_path: Path
) -> None:
    writer = make_api(migrated_url, tmp_path / "root-a")
    pid, _ = _ingest(writer, [("log.las", LAS.encode())])
    foreign = make_api(migrated_url, tmp_path / "root-b")
    rev = writer.client.get(f"/api/v1/projects/{pid}/source-revisions?limit=1").json()["items"][0]
    r = writer.upload(pid, [("more.txt", TEXT)], parent=rev["source_revision_id"])
    assert r.status_code == 202
    assert foreign.worker.run_once() is False  # verification left for the right process
    while writer.worker.run_once():
        pass
    assert {d["storage_state"] for d in writer.documents(pid)} == {"stored"}


def test_same_batch_duplicate_bytes_keep_one_stored_blob(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    same = b"%PDF-1.7\nsame\n%%EOF\n"
    pid, docs = _ingest(api, [("A B.PDF", same), ("a b copy.pdf", same)])
    assert {d["storage_state"] for d in docs} == {"stored"}
    assert all(_blob(api, d).is_file() for d in docs)

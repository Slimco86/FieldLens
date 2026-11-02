"""TASK-064: a stored original that is later unreadable (storage root differs per checkout,
blob moved/removed) must not leave a 'hash-verified' badge with a silent re-run loop."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy.engine import URL

from tests.jobs.test_extraction_flow import _drain, _ingest, _report
from tests.test_profiles_sources import LAS
from tests.upload_support import Api, make_api


def _setup(migrated_url: URL, tmp_path: Path) -> tuple[Api, str, str, Path, Path]:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("log.las", LAS.encode())])
    did = str(docs[0]["document_id"])
    assert docs[0]["storage_state"] == "stored"
    projects = api.storage / "projects"
    moved = tmp_path / "elsewhere"
    # Simulate another checkout's storage root: DB says stored, bytes are not where we look.
    shutil.move(str(projects), str(moved))
    return api, pid, did, projects, moved


def _storage_state(api: Api, pid: str) -> object:
    return api.documents(pid)[0]["storage_state"]


def test_runner_source_missing_flips_badge_and_rerun_refuses_with_reupload_guidance(
    migrated_url: URL, tmp_path: Path
) -> None:
    api, pid, did, _, _ = _setup(migrated_url, tmp_path)
    url = f"/api/v1/projects/{pid}/documents/{did}/extraction"
    assert _drain(api) == 1  # the queued run executes against the wrong root
    rep = _report(api, pid, did)
    assert rep["status"] == "failed"
    assert any(
        "source_missing" in i["message"] and "re-upload" in i["message"] for i in rep["issues"]
    )
    assert _storage_state(api, pid) == "quarantined", "must not keep saying hash-verified"

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
    api, pid, did, projects, moved = _setup(migrated_url, tmp_path)
    url = f"/api/v1/projects/{pid}/documents/{did}/extraction"
    assert _drain(api) == 1
    assert _storage_state(api, pid) == "quarantined"
    shutil.move(str(moved), str(projects))  # root corrected
    r = api.client.post(url + "?retry=true", headers=api.headers)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "queued"
    assert _drain(api) == 1
    assert _report(api, pid, did)["status"] == "succeeded"
    assert _storage_state(api, pid) == "stored"

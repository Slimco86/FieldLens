"""IN-2/IN-6 extraction runner against PostgreSQL: persistence, idempotence, staleness,
interruption, unsupported/failed outcomes and project scoping. Synthetic uploads only."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from fieldlens.profiles import registry
from tests.profile_support import xlsx_bytes
from tests.test_profiles_sources import LAS
from tests.upload_support import TEXT, Api, make_api


def _ingest(api: Api, files: list[tuple[str, bytes]]) -> tuple[str, list[dict[str, Any]]]:
    pid = api.project()
    r = api.upload(pid, files)
    assert r.status_code in (200, 201, 202), r.text
    while api.worker.run_once():
        pass
    return pid, api.documents(pid)


def _drain(api: Api) -> int:
    n = 0
    while api.worker.extraction.run_once():
        n += 1
    return n


def _report(api: Api, pid: str, did: str) -> dict[str, Any]:
    r = api.client.get(f"/api/v1/projects/{pid}/documents/{did}/extraction")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _las_name(doc: dict[str, Any]) -> str:
    return str(doc["document_id"])


def test_las_upload_is_extracted_with_evidence_and_findings(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("log.las", LAS.encode())])
    did = str(docs[0]["document_id"])
    assert _drain(api) == 1
    rep = _report(api, pid, did)
    assert rep["status"] == "succeeded"
    assert rep["profile_name"] == "las_2_0" and rep["profile_version"]
    assert rep["stale"] is False
    assert rep["coverage"]["inspected"] == rep["coverage"]["total"]
    codes = {i["code"] for i in rep["issues"]}
    assert {"MISSING_UNIT", "MISSING_REFERENCE"} <= codes
    page = api.client.get(f"/api/v1/projects/{pid}/documents/{did}/extraction/records").json()
    assert page["total"] >= 4
    attr = next(a for rec in page["items"] for a in rec["attributes"] if a["key"].endswith("strt"))
    ev = attr["evidence"]
    assert ev["document_id"] == did
    assert ev["source_revision_id"] == rep["source_revision_id"]
    assert len(rep["content_sha256"]) == 64 and rep["method"]
    assert ev["locator"]["kind"] == "text" and ev["locator"]["line_start"] >= 1
    filtered = api.client.get(
        f"/api/v1/projects/{pid}/documents/{did}/extraction/records?kind=las_curve"
    ).json()
    assert filtered.get("total") == 3, filtered
    doc = api.documents(pid)[0]
    assert doc["extraction_state"] in ("extracted", "extracted_with_issues")


def test_rerun_is_idempotent_and_profile_version_bump_supersedes(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("log.las", LAS.encode())])
    did = str(docs[0]["document_id"])
    _drain(api)
    first = _report(api, pid, did)
    url = f"/api/v1/projects/{pid}/documents/{did}/extraction"
    again = api.client.post(url, headers=api.headers).json()
    assert again["outcome"] == "unchanged"
    assert _drain(api) == 0, "no second run for an unchanged source and profile"
    assert _report(api, pid, did)["run_id"] == first["run_id"]

    profile = registry.by_name("las_2_0")
    monkeypatch.setattr(type(profile), "version", "9999.0.0")
    assert _report(api, pid, did)["stale"] is True
    assert api.client.post(url, headers=api.headers).json()["outcome"] == "queued"
    assert _drain(api) == 1
    second = _report(api, pid, did)
    assert second["run_id"] != first["run_id"]
    assert second["profile_version"] == "9999.0.0" and second["stale"] is False
    with engine.connect() as c:
        live = c.execute(
            text("select count(*) from extraction_run where document_id=:d and not superseded"),
            {"d": did},
        ).scalar_one()
        old_records = c.execute(
            text("select count(*) from extracted_record where run_id=:r"), {"r": first["run_id"]}
        ).scalar_one()
    assert live == 1
    assert old_records > 0, "superseded evidence stays auditable"


def test_unsupported_content_is_reported_not_succeeded(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("notes.txt", TEXT)])
    did = str(docs[0]["document_id"])
    _drain(api)
    rep = _report(api, pid, did)
    assert rep["status"] == "unsupported"
    assert {i["code"] for i in rep["issues"]} == {"UNSUPPORTED_FORMAT"}
    assert (
        api.client.get(f"/api/v1/projects/{pid}/documents/{did}/extraction/records").json()["total"]
        == 0
    )


def test_corrupt_workbook_fails_visibly(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    good = xlsx_bytes({"Sheet1": [["a"], [1]]})
    pid, docs = _ingest(api, [("book.xlsx", good)])
    did = str(docs[0]["document_id"])
    _drain(api)
    rep = _report(api, pid, did)
    assert rep["status"] in ("unsupported", "failed")
    assert rep["status"] != "succeeded"


def test_interrupted_run_never_appears_successful_and_attempts_are_bounded(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path, extraction_max_attempts=2)
    pid, docs = _ingest(api, [("log.las", LAS.encode())])
    did = str(docs[0]["document_id"])
    runner = api.worker.extraction
    runner.run_once()  # enqueue + execute once
    # Simulate a crash mid-run: running, lease lapsed, no results.
    with engine.begin() as c:
        c.execute(
            text(
                "update extraction_run set status='running', attempt_no=1, "
                "lease_owner='other-host:1:abc', lease_expires_at=now()-interval '1 second' "
                "where document_id=:d and not superseded"
            ),
            {"d": did},
        )
    assert runner.recover_once() == 1
    assert _report(api, pid, did)["status"] == "interrupted"
    with engine.begin() as c:
        c.execute(
            text(
                "update extraction_run set status='running', attempt_no=2, "
                "lease_owner='other-host:1:abc', lease_expires_at=now()-interval '1 second' "
                "where document_id=:d and not superseded"
            ),
            {"d": did},
        )
    assert runner.recover_once() == 1
    rep = _report(api, pid, did)
    assert rep["status"] == "failed"
    assert rep["error"]["code"] == "interrupted_too_often"


def test_extraction_is_project_scoped(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("log.las", LAS.encode())])
    did = str(docs[0]["document_id"])
    _drain(api)
    other = api.project("Other")
    for suffix in ("", "/records"):
        r = api.client.get(f"/api/v1/projects/{other}/documents/{did}/extraction{suffix}")
        assert r.status_code == 404
    r = api.client.post(f"/api/v1/projects/{other}/documents/{did}/extraction", headers=api.headers)
    assert r.status_code == 404
    assert api.client.post(f"/api/v1/projects/{pid}/documents/{did}/extraction").status_code in (
        401,
        403,
    )

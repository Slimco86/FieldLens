"""TASK-070 acceptance: root identity, Stored/Failed semantics, repair, retry, heal, attribution."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from fieldlens.evidence import root_guard
from tests.jobs.test_extraction_flow import _drain, _ingest, _report
from tests.jobs.test_extraction_source_missing import _blob, _state
from tests.test_profiles_sources import LAS
from tests.upload_support import TEXT, Api, make_api


def _doc(api: Api, pid: str, name: str = "log.las") -> dict[str, object]:
    return next(d for d in api.documents(pid) if d["original_filename"] == name)


def _force_failed(engine: Engine, did: str, reason: str = "missing") -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "update document_processing set storage_state='failed',"
                " storage_failure_reason=cast(:r as varchar), storage_failed_by='stale-server',"
                " detail='verification_' || cast(:r as varchar) where document_id=:d"
            ),
            {"r": reason, "d": did},
        )


def _retry(api: Api, pid: str, did: str):  # type: ignore[no-untyped-def]
    return api.client.post(
        f"/api/v1/projects/{pid}/documents/{did}/storage/retry", headers=api.headers
    )


def test_ac1_foreign_root_claims_nothing_and_readiness_reports_mismatch(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    writer = make_api(migrated_url, tmp_path / "root-a")
    pid, docs = _ingest(writer, [("log.las", LAS.encode())])
    foreign = make_api(migrated_url, tmp_path / "root-b")
    assert foreign.worker.run_once() is False
    assert foreign.worker.extraction.run_once() is False
    r = foreign.client.get("/ready")
    assert r.status_code == 503 and "storage_root_mismatch" in r.text
    up = foreign.upload(pid, [("n.txt", TEXT)])
    assert up.status_code == 503 and up.json()["error"]["details"]["reason"] == (
        "storage_root_mismatch"
    )
    with engine.connect() as c:
        bad = c.execute(
            text("select count(*) from document_processing where storage_state<>'stored'")
        ).scalar_one()
    assert bad == 0
    assert docs[0]["storage_state"] == "stored"


def test_ac1_missing_marker_is_a_mismatch(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    _ingest(api, [("log.las", LAS.encode())])
    (tmp_path / "root" / root_guard.MARKER_NAME).unlink()
    other = make_api(migrated_url, tmp_path / "root")
    assert other.client.get("/ready").status_code == 503


def test_ac2_fresh_bind_and_second_start(migrated_url: URL, tmp_path: Path, engine: Engine) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    assert api.client.get("/ready").status_code == 200
    assert (tmp_path / "root" / root_guard.MARKER_NAME).is_file()
    with engine.connect() as c:
        assert c.execute(text("select count(*) from storage_root_identity")).scalar_one() == 1
    again = make_api(migrated_url, tmp_path / "root")
    assert again.client.get("/ready").status_code == 200


def test_ac3_genuinely_missing_blob_is_failed_with_reason(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    pid = api.project()
    api.upload(pid, [("log.las", LAS.encode()), ("n.txt", TEXT)])
    while api.worker.run_once():
        pass
    doc = _doc(api, pid)
    _blob(api, doc).unlink()
    r = api.client.get(f"/api/v1/projects/{pid}/documents/{doc['document_id']}/extraction")
    assert r.status_code == 200
    _drain(api)
    row = _doc(api, pid)
    assert row["storage_state"] == "failed"
    assert row["storage_failure_reason"] == "missing"
    assert "quarantin" not in str(row).lower()
    assert _doc(api, pid, "n.txt")["storage_state"] == "stored"
    with engine.connect() as c:
        by = c.execute(
            text("select storage_failed_by from document_processing where document_id=:d"),
            {"d": str(doc["document_id"])},
        ).scalar_one()
    assert by and "pid=" in by


def test_ac4_reupload_repairs_failed_document_and_intact_stays_deduplicated(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    pid, _ = _ingest(api, [("log.las", LAS.encode())])
    doc = _doc(api, pid)
    blob = _blob(api, doc)
    ir = api.upload(pid, [("log.las", LAS.encode())], parent=api.latest(pid))
    assert ir.status_code == 200, ir.text
    intact = ir.json()
    assert intact["deduplicated"] is True and not intact.get("repaired_document_ids")
    blob.unlink()
    api.client.post(
        f"/api/v1/projects/{pid}/documents/{doc['document_id']}/extraction?retry=true",
        headers=api.headers,
    )
    _drain(api)
    assert _state(api, pid, str(doc["document_id"])) == "failed"
    fixed = api.upload(pid, [("log.las", LAS.encode())], parent=api.latest(pid)).json()
    assert fixed["deduplicated"] is False
    assert fixed["repaired_document_ids"] == [str(doc["document_id"])]
    assert blob.is_file()
    assert _state(api, pid, str(doc["document_id"])) == "stored"
    assert _drain(api) == 1
    assert _report(api, pid, str(doc["document_id"]))["status"] == "succeeded"


def test_ac5_retry_restores_when_bytes_verify_else_conflict(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    pid, _ = _ingest(api, [("log.las", LAS.encode())])
    did = str(_doc(api, pid)["document_id"])
    _drain(api)
    _force_failed(engine, did)
    r = _retry(api, pid, did)
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "restored" and r.json()["storage_state"] == "stored"
    assert _state(api, pid, did) == "stored"
    assert _retry(api, pid, did).json()["outcome"] == "already_stored"
    blob = _blob(api, _doc(api, pid))
    moved = tmp_path / "gone"
    shutil.move(str(blob), str(moved))
    _force_failed(engine, did)
    r = _retry(api, pid, did)
    assert r.status_code == 409
    assert "re-upload" in r.json()["error"]["message"].lower()
    assert _state(api, pid, did) == "failed"


def test_ac6_incident_documents_are_healed_once_and_idempotently(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    pid, docs = _ingest(api, [("log.las", LAS.encode()), ("n.txt", TEXT)])
    _drain(api)
    for d in docs:
        _force_failed(engine, str(d["document_id"]))
    first = api.worker.heal_once()
    assert first.ran and first.restored == 2
    assert {d["storage_state"] for d in api.documents(pid)} == {"stored"}
    second = api.worker.heal_once()
    assert second.restored == 0
    with engine.connect() as c:
        runs = c.execute(
            text("select count(*) from extraction_run where superseded=false")
        ).scalar_one()
    assert runs == 2


def test_ac7_attribution_and_application_name(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path / "root", lane="lane-x")
    pid, _ = _ingest(api, [("log.las", LAS.encode()), ("n.txt", TEXT)])
    doc = _doc(api, pid)
    _blob(api, doc).unlink()
    _drain(api)
    with engine.connect() as c:
        err = c.execute(
            text("select error from extraction_run where document_id=:d"),
            {"d": str(doc["document_id"])},
        ).scalar_one()
    assert err["code"] == "source_missing" and "lane=lane-x" in err["process"]
    with engine.connect() as c:
        names = (
            c.execute(
                text(
                    "select application_name from pg_stat_activity where application_name like 'fieldlens:%'"
                )
            )
            .scalars()
            .all()
        )
    assert any(n.startswith("fieldlens:lane-x:") for n in names)


def test_d1_all_failed_unbound_database_is_healed_without_adopt(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    """Incident shape: every document failed, no identity row, no marker on the root."""
    api = make_api(migrated_url, tmp_path / "root")
    pid, docs = _ingest(api, [("log.las", LAS.encode()), ("n.txt", TEXT)])
    for d in docs:
        _force_failed(engine, str(d["document_id"]))
    with engine.begin() as c:
        c.execute(text("delete from extraction_run"))
        c.execute(text("delete from storage_root_identity"))
    (tmp_path / "root" / root_guard.MARKER_NAME).unlink()
    fresh = make_api(migrated_url, tmp_path / "root")
    first = fresh.worker.heal_once()
    assert first.ran and first.restored == 2
    assert {d["storage_state"] for d in fresh.documents(pid)} == {"stored"}
    assert fresh.client.get("/ready").status_code == 200
    again = fresh.worker.heal_once()
    assert again.restored == 0
    with engine.connect() as c:
        runs = c.execute(text("select count(*) from extraction_run")).scalar_one()
    assert runs == 2


def test_d1_empty_root_never_binds_on_zero_evidence(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    pid, docs = _ingest(api, [("n.txt", TEXT)])
    _force_failed(engine, str(docs[0]["document_id"]))
    with engine.begin() as c:
        c.execute(text("delete from storage_root_identity"))
    other = make_api(migrated_url, tmp_path / "empty")
    assert other.worker.heal_once().ran is False
    assert other.client.get("/ready").status_code == 503


def test_d5_mismatch_log_is_throttled_process_wide(
    migrated_url: URL, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    writer = make_api(migrated_url, tmp_path / "root-a")
    _ingest(writer, [("n.txt", TEXT)])
    foreign = make_api(migrated_url, tmp_path / "root-b")
    root_guard._last_logged = float("-inf")
    with caplog.at_level("ERROR", logger="fieldlens.evidence.root_guard"):
        foreign.worker.run_once()
        foreign.worker.extraction.run_once()
        foreign.client.get("/ready")
        foreign.upload(writer.project(), [("m.txt", TEXT)])
    assert sum("storage_root_mismatch" in r.getMessage() for r in caplog.records) == 1

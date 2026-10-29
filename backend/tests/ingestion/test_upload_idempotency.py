"""IN-1 / PW-3/4/6/7: idempotent upload, project isolation, no active-model movement."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from tests.upload_support import CSV, LAS, PDF, TEXT, make_api, make_pdf

MISSING = "00000000-0000-0000-0000-000000000000"


def test_upload_stores_immutable_original_outside_db_and_moves_no_pointer(
    migrated_url: URL, engine: Engine, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("report.pdf", PDF), ("well.las", LAS), ("notes.txt", TEXT)])
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "staging" and body["job_id"] and not body["deduplicated"]
    assert api.latest(pid) is None  # only a verified job publishes

    blobs = api.blob_files()
    assert len(blobs) == 3
    assert {b.name for b in blobs} == {hashlib.sha256(x).hexdigest() for x in (PDF, LAS, TEXT)}
    assert all((b.stat().st_mode & 0o222) == 0 for b in blobs)  # read-only originals
    assert not list((tmp_path / "staging").iterdir())  # staging is cleaned
    with engine.connect() as c:  # bytes are not in database rows
        assert c.execute(text("select count(*) from source_document")).scalar_one() == 3
        cols = c.execute(
            text(
                "select column_name from information_schema.columns "
                "where table_name='source_document' and data_type='bytea'"
            )
        ).all()
        assert cols == []

    assert api.worker.run_once() is True
    job = api.job(pid, body["job_id"])
    assert job["status"] == "succeeded" and job["result"]["extraction_performed"] is False
    assert api.latest(pid) == body["source_revision_id"]
    project = api.client.get(f"/api/v1/projects/{pid}").json()
    assert project["active_model_revision_id"] is None  # never moved by upload

    docs = {d["original_filename"]: d for d in api.documents(pid)}
    assert docs["report.pdf"]["extraction_state"] == "pending_extraction"
    assert docs["notes.txt"]["extraction_state"] == "unsupported"
    assert docs["well.las"]["classification"]["suggested_categories"] == ["well_logs"]
    assert docs["well.las"]["classification"]["user_categories"] == []
    assert all(d["storage_state"] == "stored" for d in docs.values())
    assert docs["report.pdf"]["sha256"] == hashlib.sha256(PDF).hexdigest()
    revision = api.revisions(pid)[0]
    assert revision["status"] == "ready" and revision["coverage"]["status"] == "unknown"
    with engine.connect() as c:
        assert c.execute(text("select count(*) from model_revision")).scalar_one() == 0


def test_idempotency_key_replay_and_reuse(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    first = api.upload(pid, [("a.pdf", PDF)], key="k-1")
    again = api.upload(pid, [("a.pdf", PDF)], key="k-1")
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["replayed"] is True
    assert again.json()["job_id"] == first.json()["job_id"]
    assert again.json()["document_ids"] == first.json()["document_ids"]
    assert len(api.revisions(pid)) == 1
    different = api.upload(pid, [("a.pdf", make_pdf("x"))], key="k-1")
    assert different.status_code == 409
    assert different.json()["error"]["details"]["reason"] == "idempotency_key_reuse"
    api.worker.run_once()
    replay_after = api.upload(pid, [("a.pdf", PDF)], key="k-1")
    assert replay_after.status_code == 200 and replay_after.json()["status"] == "ready"


def test_same_bytes_again_is_a_noop_without_new_revision(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    first = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.run_once()
    dup = api.upload(pid, [("renamed.pdf", PDF)], parent=first["source_revision_id"])
    assert dup.status_code == 200 and dup.json()["deduplicated"] is True
    assert dup.json()["job_id"] is None and dup.json()["document_ids"] == first["document_ids"]
    assert len(api.revisions(pid)) == 1 and len(api.blob_files()) == 1
    assert [d["original_filename"] for d in api.documents(pid)] == ["a.pdf"]  # filename is a hint


def test_duplicate_files_in_one_request_share_a_document(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF), ("b.pdf", PDF), ("c.csv", CSV)])
    ids = r.json()["document_ids"]
    assert ids[0] == ids[1] != ids[2]
    assert len(r.json()["created_document_ids"]) == 2


def test_hash_match_in_another_project_does_not_dedupe_or_leak(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    a, b = api.project("A"), api.project("B")
    ra = api.upload(a, [("secret.pdf", PDF)], hints=[{"categories": ["trajectory"]}]).json()
    api.worker.run_once()
    rb = api.upload(b, [("other.pdf", PDF)]).json()
    assert rb["deduplicated"] is False and rb["created_document_ids"] == rb["document_ids"]
    assert rb["document_ids"] != ra["document_ids"]
    api.worker.run_once()
    assert [d["original_filename"] for d in api.documents(b)] == ["other.pdf"]
    assert api.documents(b)[0]["classification"]["user_categories"] == []  # A's hints not copied
    assert len(api.blob_files()) == 2  # one blob per project, not shared
    doc_a = ra["document_ids"][0]
    r = api.client.patch(
        f"/api/v1/projects/{b}/documents/{doc_a}/classification",
        json={"categories": [], "tags": [], "expected_metadata_version": 1},
        headers=api.headers,
    )
    assert r.status_code == 404
    assert api.client.get(f"/api/v1/projects/{b}/jobs/{ra['job_id']}").status_code == 404
    r = api.client.get(
        f"/api/v1/projects/{b}/documents", params={"source_revision_id": ra["source_revision_id"]}
    )
    assert r.status_code == 404
    cancel = api.client.post(
        f"/api/v1/projects/{b}/jobs/{ra['job_id']}/cancel", headers=api.headers
    )
    assert cancel.status_code == 404


def test_stale_parent_and_concurrent_staging_are_409(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    first = api.upload(pid, [("a.pdf", PDF)]).json()
    busy = api.upload(pid, [("b.pdf", make_pdf("b"))])
    assert busy.status_code == 409
    assert busy.json()["error"]["details"]["reason"] in {"import_in_progress", "stale_parent"}
    api.worker.run_once()
    stale = api.upload(pid, [("b.pdf", make_pdf("b"))], parent=None)
    assert stale.status_code == 409 and stale.json()["error"]["details"]["reason"] == "stale_parent"
    ok = api.upload(pid, [("b.pdf", make_pdf("b"))], parent=first["source_revision_id"])
    assert ok.status_code == 202
    assert api.upload(MISSING, [("a.pdf", PDF)]).status_code == 404


def test_mutations_require_session_token(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)], headers={})
    assert r.status_code == 403
    assert api.blob_files() == []


def test_classification_hints_override_and_audit(
    migrated_url: URL, engine: Engine, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(
        pid, [("a.pdf", PDF)], hints=[{"categories": ["trajectory"], "tags": ["t1", "t1"]}]
    ).json()
    doc = r["document_ids"][0]
    api.worker.run_once()
    item = api.documents(pid)[0]["classification"]
    assert item["categories_origin"] == "upload_hint" and item["tags"] == ["t1"]
    url = f"/api/v1/projects/{pid}/documents/{doc}/classification"
    ok = api.client.patch(
        url,
        json={"categories": ["general_report"], "tags": [], "expected_metadata_version": 1},
        headers=api.headers,
    )
    assert ok.status_code == 200
    cls = ok.json()["classification"]
    assert cls["categories_origin"] == "user_override" and cls["metadata_version"] == 2
    stale = api.client.patch(
        url,
        json={"categories": [], "tags": [], "expected_metadata_version": 1},
        headers=api.headers,
    )
    assert stale.status_code == 409
    bad = api.client.patch(
        url,
        json={"categories": ["nonsense"], "tags": [], "expected_metadata_version": 2},
        headers=api.headers,
    )
    assert bad.status_code == 422
    with engine.connect() as c:
        versions = c.execute(
            text(
                "select metadata_version, origin from document_classification_event "
                "order by metadata_version"
            )
        ).all()
    assert [tuple(v) for v in versions] == [(1, "upload_hint"), (2, "user_override")]

"""IN-5: corrected sources create new immutable revisions; failures never replace good results."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from fieldlens.evidence.storage import blob_key
from tests.upload_support import CSV, PDF, TEXT, Api, make_api, make_pdf


def _remove_blob(api: Api, project_id: str, data: bytes) -> None:
    import hashlib

    sha = hashlib.sha256(data).hexdigest()
    (api.storage / blob_key(__import__("uuid").UUID(project_id), sha)).unlink()


def test_incremental_import_creates_new_revision_and_keeps_old_one_intact(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    first = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.run_once()
    second = api.upload(pid, [("b.csv", CSV)], parent=first["source_revision_id"]).json()
    api.worker.run_once()
    assert api.latest(pid) == second["source_revision_id"]
    names = sorted(d["original_filename"] for d in api.documents(pid))
    assert names == ["a.pdf", "b.csv"]
    old = [d["original_filename"] for d in api.documents(pid, first["source_revision_id"])]
    assert old == ["a.pdf"]  # the earlier revision is immutable
    revisions = api.revisions(pid)
    assert [r["is_latest"] for r in revisions] == [True, False]
    assert revisions[0]["parent_source_revision_id"] == first["source_revision_id"]
    assert revisions[0]["member_count"] == 2 and revisions[0]["stored_count"] == 2


def test_replacement_is_explicit_and_old_revision_keeps_old_document(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    first = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.run_once()
    old_doc = first["document_ids"][0]
    fixed = make_pdf("corrected")
    second = api.upload(
        pid,
        [("a.pdf", fixed)],
        parent=first["source_revision_id"],
        hints=[{"replaces_document_id": old_doc}],
    ).json()
    api.worker.run_once()
    docs = api.documents(pid)
    assert [d["document_id"] for d in docs] == second["document_ids"]
    assert docs[0]["replaces_document_id"] == old_doc
    assert api.documents(pid, first["source_revision_id"])[0]["document_id"] == old_doc
    assert len(api.blob_files()) == 2  # the original bytes are never overwritten or removed


def test_replacement_validation(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    first = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.run_once()
    parent = first["source_revision_id"]
    doc = first["document_ids"][0]
    unknown = api.upload(
        pid,
        [("b.pdf", make_pdf("b"))],
        parent=parent,
        hints=[{"replaces_document_id": "11111111-1111-1111-1111-111111111111"}],
    )
    assert unknown.status_code == 422
    same = api.upload(pid, [("a.pdf", PDF)], parent=parent, hints=[{"replaces_document_id": doc}])
    assert same.status_code == 422
    assert len(api.revisions(pid)) == 1


def test_partial_revision_exposes_quarantine_counts(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF), ("b.txt", TEXT)]).json()
    _remove_blob(api, pid, TEXT)  # simulate storage damage after upload
    api.worker.run_once()
    job = api.job(pid, r["job_id"])
    assert job["status"] == "partial"
    assert job["result"]["stored"] == 1 and job["result"]["quarantined"] == 1
    rev = api.revisions(pid)[0]
    assert rev["status"] == "ready_with_issues" and rev["quarantined_count"] == 1
    assert "quarantined_documents" in rev["coverage"]["reasons"][1]
    assert api.latest(pid) == r["source_revision_id"]
    states = {d["original_filename"]: d for d in api.documents(pid)}
    assert states["b.txt"]["storage_state"] == "quarantined"
    assert states["b.txt"]["processing_detail"] == "verification_missing"
    assert states["a.pdf"]["storage_state"] == "stored"


def test_failed_replacement_keeps_previous_results_labelled(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    first = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.run_once()
    bad = make_pdf("bad")
    second = api.upload(
        pid,
        [("a.pdf", bad)],
        parent=first["source_revision_id"],
        hints=[{"replaces_document_id": first["document_ids"][0]}],
    ).json()
    _remove_blob(api, pid, bad)
    api.worker.run_once()
    assert api.job(pid, second["job_id"])["status"] == "failed"
    assert api.latest(pid) == first["source_revision_id"]  # old results stay current
    assert [d["document_id"] for d in api.documents(pid)] == first["document_ids"]
    failed = next(r for r in api.revisions(pid) if r["status"] == "failed")
    assert failed["source_revision_id"] == second["source_revision_id"] and not failed["is_latest"]
    assert "all_documents_quarantined" in failed["coverage"]["reasons"][0]
    # the project can import again after the failed attempt
    retry = api.upload(pid, [("c.csv", CSV)], parent=first["source_revision_id"])
    assert retry.status_code == 202


def test_published_records_are_immutable(migrated_url: URL, engine: Engine, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF)]).json()
    api.worker.run_once()
    with engine.begin() as c:
        statements = [
            "update source_document set size_bytes = size_bytes + 1",
            "delete from source_document",
            "update source_revision set manifest_hash = repeat('a', 64)",
            "delete from source_revision",
            "delete from source_revision_document",
        ]
        for sql in statements:
            with pytest.raises(DBAPIError):
                with c.begin_nested():
                    c.execute(text(sql))
    assert r["document_ids"]

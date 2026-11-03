"""TASK-087 B-1: original PDF content route on PostgreSQL (synthetic bytes, no model call)."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy.engine import URL

from fieldlens.ingestion.content import content_disposition, safe_filename
from tests.upload_support import CSV, Api, make_api, make_pdf

BIG = make_pdf("range-test") + bytes(range(256)) * 40


def _upload(api: Api, pid: str, name: str, data: bytes) -> str:
    r = api.upload(pid, [(name, data)], parent=api.latest(pid))
    assert r.status_code == 202, r.text
    api.worker.run_once()
    return str(r.json()["created_document_ids"][0])


def _url(pid: str, doc: str) -> str:
    return f"/api/v1/projects/{pid}/documents/{doc}/content"


def test_pdf_bytes_and_headers(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    doc = _upload(api, pid, "Survey Report.pdf", BIG)
    r = api.client.get(_url(pid, doc))
    assert r.status_code == 200 and r.content == BIG
    h = r.headers
    assert h["content-type"] == "application/pdf"
    assert h["content-disposition"].startswith('inline; filename="Survey Report.pdf"')
    assert h["x-content-type-options"] == "nosniff"
    assert "default-src 'none'" in h["content-security-policy"]
    assert "frame-ancestors" not in h["content-security-policy"]
    assert "x-frame-options" not in h
    assert h["cache-control"].startswith("private") and "no-store" not in h["cache-control"]
    assert h["accept-ranges"] == "bytes" and h["content-length"] == str(len(BIG))
    etag = h["etag"]
    assert len(etag) == 66 and etag.startswith('"') and etag.endswith('"')  # the stored sha256
    again = api.client.get(_url(pid, doc), headers={"If-None-Match": etag})
    assert again.status_code == 304 and again.content == b""


def test_range_returns_206_with_exact_slice(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    doc = _upload(api, pid, "r.pdf", BIG)
    r = api.client.get(_url(pid, doc), headers={"Range": "bytes=10-99"})
    assert r.status_code == 206 and r.content == BIG[10:100]
    assert r.headers["content-range"] == f"bytes 10-99/{len(BIG)}"
    assert r.headers["x-content-type-options"] == "nosniff"
    tail = api.client.get(_url(pid, doc), headers={"Range": "bytes=-16"})
    assert tail.status_code == 206 and tail.content == BIG[-16:]
    bad = api.client.get(_url(pid, doc), headers={"Range": f"bytes={len(BIG) + 5}-"})
    assert bad.status_code == 416
    multi = api.client.get(_url(pid, doc), headers={"Range": "bytes=0-1,5-6"})
    assert multi.status_code in (200, 400)  # never a multipart amplification
    assert multi.status_code == 400 or "multipart" not in multi.headers["content-type"]


def test_other_project_unknown_and_non_pdf(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    p1, p2 = api.project("one"), api.project("two")
    pdf = _upload(api, p1, "a.pdf", make_pdf("a"))
    csv = _upload(api, p1, "a.csv", CSV)
    assert api.client.get(_url(p2, pdf)).status_code == 404  # another project's document
    missing = api.client.get(_url(p1, "00000000-0000-4000-8000-000000000000"))
    assert missing.status_code == 404
    r = api.client.get(_url(p1, csv))
    assert r.status_code == 415
    assert r.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert api.client.get(_url(p1, pdf)).status_code == 200


def test_missing_and_tampered_blobs_are_typed_errors(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    doc = _upload(api, pid, "t.pdf", make_pdf("tamper"))
    assert api.client.get(_url(pid, doc)).status_code == 200  # verified (and remembered)
    (blob,) = api.blob_files()
    os.chmod(blob, 0o644)
    original = blob.read_bytes()
    blob.write_bytes(original[:-1] + b"X")  # same size, different bytes
    os.utime(blob, ns=(1, 1))  # a different file identity
    r = api.client.get(_url(pid, doc))
    assert r.status_code == 409
    assert r.json()["error"]["details"]["reason"] == "hash_mismatch"
    blob.write_bytes(original[:-3])
    os.utime(blob, ns=(2, 2))
    r = api.client.get(_url(pid, doc))
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "size_mismatch"
    blob.unlink()
    r = api.client.get(_url(pid, doc))
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "missing"
    assert "body" not in r.text.lower() or r.headers["content-type"].startswith("application/json")


def test_filename_is_header_safe() -> None:
    assert safe_filename('../../etc/pa"ss\r\nwd.pdf') == "pa_ss__wd.pdf"
    header = content_disposition('a"b\r\n/Ünï.pdf')
    assert "\r" not in header and "\n" not in header and header.startswith("inline;")
    assert 'filename="Ünï' not in header and "filename*=UTF-8''" in header

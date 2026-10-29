"""IN-3: hostile uploads are rejected before anything is published or executed."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from fieldlens.contracts.errors import ContractError
from fieldlens.ingestion.inspect import validate_filename
from tests.upload_support import (
    PDF,
    make_api,
    minimal_xlsx,
    zip_bytes,
    zip_with_symlink,
)


def _encrypted_zip() -> bytes:
    """A structurally valid ZIP whose entry carries the 'encrypted' general-purpose flag."""
    raw = bytearray(zip_bytes([("xl/workbook.xml", b"x")]))
    local = raw.index(b"PK\x03\x04")
    central = raw.index(b"PK\x01\x02")
    raw[local + 6] |= 0x1
    raw[central + 8] |= 0x1
    return bytes(raw)


def test_control_characters_in_filenames_are_refused() -> None:
    for bad in ("a\x01b.pdf", "a\nb.pdf", "x\x00.pdf", " lead.pdf"):
        with pytest.raises(ContractError):
            validate_filename(bad)


XXE = b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">]><d>&x;</d>'
XXE_UTF16 = "<?xml version='1.0'?><!DOCTYPE d><d/>".encode("utf-16")

CASES: list[tuple[str, str, bytes, int, str]] = [
    ("traversal_name", "../evil.pdf", PDF, 422, "unsafe_filename"),
    ("absolute_name", "/etc/passwd.pdf", PDF, 422, "unsafe_filename"),
    ("backslash_name", "..\\evil.pdf", PDF, 422, "unsafe_filename"),
    ("dotdot_name", "..", PDF, 422, "unsafe_filename"),
    ("zip_traversal", "t.xlsx", zip_bytes([("../../evil", b"x")]), 422, "path_traversal"),
    ("zip_absolute", "t.xlsx", zip_bytes([("/etc/evil", b"x")]), 422, "absolute_entry_path"),
    ("symlink_entry", "t.xlsx", zip_with_symlink(), 422, "symlink_entry"),
    ("encrypted_entry", "t.xlsx", _encrypted_zip(), 422, "encrypted_entry"),
    (
        "zip_nested",
        "t.xlsx",
        zip_bytes([("xl/inner.zip", zip_bytes([("a", b"b")]))]),
        422,
        "nested_archive",
    ),
    ("xxe_doctype", "d.xml", XXE, 422, "xml_dtd_forbidden"),
    ("xxe_utf16", "d.xml", XXE_UTF16, 422, "xml_dtd_forbidden"),
    ("elf", "x.pdf", b"\x7fELF\x02\x01\x01" + b"\x00" * 64, 415, "executable_content"),
    ("pe", "x.pdf", b"MZ" + b"\x00" * 64, 415, "executable_content"),
    ("script", "x.csv", b"#!/bin/sh\nrm -rf /\n", 415, "executable_content"),
    ("unknown_binary", "x.dat", bytes(range(256)) * 4, 415, "unsupported_signature"),
    ("empty", "e.pdf", b"", 422, "empty_file"),
]


@pytest.mark.parametrize(
    ("name", "filename", "data", "status", "reason"), CASES, ids=[c[0] for c in CASES]
)
def test_hostile_upload_rejected_without_side_effects(
    migrated_url: URL,
    engine: Engine,
    tmp_path: Path,
    name: str,
    filename: str,
    data: bytes,
    status: int,
    reason: str,
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    # a good sibling file must not be published when any file in the batch is rejected
    r = api.upload(pid, [("ok.pdf", PDF), (filename, data)])
    assert r.status_code == status, r.text
    assert r.json()["error"]["details"]["reason"] == reason
    assert api.blob_files() == []
    assert not any((tmp_path / "staging").iterdir())
    outside = {p.name for p in tmp_path.parent.iterdir() if p.name.startswith("evil")}
    assert outside == set() and not (tmp_path / "evil.pdf").exists()
    with engine.connect() as c:
        for table in ("source_document", "source_revision", "ingest_job", "import_batch"):
            assert c.execute(text(f"select count(*) from {table}")).scalar_one() == 0
    assert api.latest(pid) is None


def test_clean_xlsx_container_is_accepted_but_never_extracted(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(pid, [("book.xlsx", minimal_xlsx())])
    assert r.status_code == 202, r.text
    api.worker.run_once()
    doc = api.documents(pid)[0]
    assert doc["format_family"] == "xlsx" and doc["extraction_state"] == "pending_extraction"


def test_zip_expanded_size_is_bounded(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path, upload_max_file_bytes=64 * 1024)
    pid = api.project()
    bomb = zip_bytes([("xl/workbook.xml", b"<a/>"), ("xl/big.xml", b"0" * (200 * 1024))])
    assert len(bomb) < 64 * 1024
    r = api.upload(pid, [("bomb.xlsx", bomb)])
    assert r.status_code == 413 and r.json()["error"]["details"]["reason"] in {"expanded_size"}
    assert api.blob_files() == []


@pytest.mark.parametrize(
    "body_fn",
    ["no_metadata", "bad_json", "unknown_part", "count_mismatch", "files_first"],
)
def test_malformed_multipart_is_422(migrated_url: URL, tmp_path: Path, body_fn: str) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    url = f"/api/v1/projects/{pid}/imports"
    good = (
        None,
        b'{"expected_parent_source_revision_id": null, "files": [{}]}',
        "application/json",
    )
    f = ("a.pdf", PDF, "application/pdf")
    forms = {
        "no_metadata": [("files", f)],
        "bad_json": [("metadata", (None, b"{", "application/json")), ("files", f)],
        "unknown_part": [("metadata", good), ("extra", (None, b"x", "text/plain")), ("files", f)],
        "count_mismatch": [("metadata", good), ("files", f), ("files", f)],
        "files_first": [("files", f), ("metadata", good)],
    }[body_fn]
    r = api.client.post(url, files=forms, headers=api.headers)
    assert r.status_code == 422, r.text
    assert api.blob_files() == []


def test_non_multipart_is_415(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.client.post(f"/api/v1/projects/{pid}/imports", json={}, headers=api.headers)
    assert r.status_code == 415

"""IN-10: a refused batch names every refused file and stores nothing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from tests.upload_support import LAS, PDF, TEXT, Api, make_api

ELF = b"\x7fELF\x02\x01\x01" + b"\x00" * 64
BINARY = bytes(range(256)) * 4


def _assert_nothing_stored(api: Api, engine: Engine, tmp_path: Path, pid: str) -> None:
    assert api.blob_files() == []
    assert not any((tmp_path / "staging").iterdir())
    with engine.connect() as c:
        for table in ("source_document", "source_revision", "ingest_job", "import_batch"):
            assert c.execute(text(f"select count(*) from {table}")).scalar_one() == 0
    assert api.latest(pid) is None


def _details(r: Any) -> dict[str, Any]:
    return dict(r.json()["error"]["details"])


def test_upload_rejection_names_files(migrated_url: URL, engine: Engine, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    r = api.upload(
        pid,
        [
            ("good.pdf", PDF),
            ("tool.exe", ELF),
            ("blob.bin", BINARY),
            ("empty.txt", b""),
            ("notes.txt", TEXT),
            ("../evil.pdf", PDF),
        ],
    )
    # status/code/reason of the first refusal keep the pre-IN-10 envelope
    assert r.status_code == 415 and r.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    d = _details(r)
    assert d["reason"] == "executable_content"
    assert d["scope"] == "files" and d["batch_outcome"] == "nothing_stored"
    assert d["refusals_complete"] is True and d["file_count"] == 6
    got = [(f["position"], f["filename"], f["reason"]) for f in d["refused_files"]]
    assert got == [
        (1, "tool.exe", "executable_content"),
        (2, "blob.bin", "unsupported_signature"),
        (3, "empty.txt", "empty_file"),
        (5, "../evil.pdf", "unsafe_filename"),
    ]
    for f in d["refused_files"]:
        assert f["message"] and f["error_code"] and isinstance(f["status_code"], int)
    _assert_nothing_stored(api, engine, tmp_path, pid)


def test_all_good_batch_after_refusal_is_still_accepted(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    assert api.upload(pid, [("a.pdf", PDF), ("x.bin", BINARY)]).status_code == 415
    r = api.upload(pid, [("a.pdf", PDF), ("w.las", LAS)])  # retry without the refused file
    assert r.status_code == 202, r.text


def test_oversize_file_is_refused_per_file_and_others_still_listed(
    migrated_url: URL, engine: Engine, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path, upload_max_file_bytes=64 * 1024)
    pid = api.project()
    big = PDF + b"0" * (100 * 1024)
    r = api.upload(pid, [("big.pdf", big), ("ok.pdf", PDF), ("x.bin", BINARY), ("big2.pdf", big)])
    assert r.status_code == 413
    d = _details(r)
    assert d["reason"] == "file_bytes" and d["scope"] == "files"
    assert [(f["position"], f["filename"], f["reason"]) for f in d["refused_files"]] == [
        (0, "big.pdf", "file_bytes"),
        (2, "x.bin", "unsupported_signature"),
        (3, "big2.pdf", "file_bytes"),
    ]
    assert d["refused_files"][0]["limit"] == 64 * 1024
    _assert_nothing_stored(api, engine, tmp_path, pid)


def test_batch_level_refusal_is_labelled_batch(
    migrated_url: URL, engine: Engine, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path, upload_max_files=2)
    pid = api.project()
    r = api.upload(pid, [("a.pdf", PDF), ("b.pdf", PDF + b"1"), ("c.pdf", PDF + b"2")])
    assert r.status_code == 413
    d = _details(r)
    assert d["reason"] == "file_count" and d["scope"] == "batch"
    assert d["batch_outcome"] == "nothing_stored" and d["refusals_complete"] is False
    assert d["refused_files"] == []
    _assert_nothing_stored(api, engine, tmp_path, pid)


def test_batch_size_refusal_keeps_earlier_file_refusals(
    migrated_url: URL, engine: Engine, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path, upload_max_batch_bytes=64 * 1024)
    pid = api.project()
    r = api.upload(pid, [("x.bin", BINARY), ("a.pdf", PDF + b"0" * 70_000)])
    assert r.status_code == 413
    d = _details(r)
    assert d["reason"] == "batch_bytes" and d["scope"] == "batch"
    assert [f["filename"] for f in d["refused_files"]] == ["x.bin"]
    _assert_nothing_stored(api, engine, tmp_path, pid)

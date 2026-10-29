"""QA D1-D3: rejected imports leave nothing behind; staging sweep; quiet client disconnect."""

from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from starlette.requests import ClientDisconnect

from fieldlens.evidence.storage import BlobStore
from fieldlens.ingestion import repository
from tests.upload_support import BASE, PDF, make_api, make_pdf


def _no_rows(engine: Engine) -> None:
    with engine.connect() as c:
        for table in ("source_document", "source_revision", "ingest_job", "import_batch"):
            assert c.execute(text(f"select count(*) from {table}")).scalar_one() == 0, table  # noqa: S608


def _staging_left(storage: Path) -> list[Path]:
    root = storage / "staging"
    return sorted(root.rglob("*")) if root.exists() else []


def test_stale_parent_rejection_leaves_no_new_blob(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    assert api.upload(pid, [("a.pdf", make_pdf("a"))]).status_code == 202
    api.worker.run_once()
    before = api.blob_files()
    r = api.upload(pid, [("b.pdf", make_pdf("b"))], parent=None)  # QA repro
    assert r.status_code == 409, r.text
    assert api.blob_files() == before
    assert _staging_left(tmp_path) == []


def test_in_progress_rejection_leaves_no_new_blob(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    assert api.upload(pid, [("a.pdf", make_pdf("a"))]).status_code == 202  # still staging
    before = api.blob_files()
    r = api.upload(pid, [("b.pdf", make_pdf("b"))])
    assert r.status_code == 409, r.text
    assert api.blob_files() == before
    assert _staging_left(tmp_path) == []


def test_rejection_keeps_blob_referenced_by_a_document(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    assert api.upload(pid, [("a.pdf", make_pdf("a"))]).status_code == 202
    api.worker.run_once()
    before = api.blob_files()
    r = api.upload(pid, [("a.pdf", make_pdf("a")), ("b.pdf", make_pdf("b"))], parent=None)
    assert r.status_code == 409
    assert api.blob_files() == before  # a's blob stays; b's never appeared


def test_database_failure_after_blob_publish_discards_new_blobs(
    migrated_url: URL, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    real = repository.publish_import

    def failing(*args: Any, publish_blobs: Callable[[], None] | None = None, **kw: Any) -> Any:
        assert publish_blobs is not None
        publish_blobs()  # blobs exist, then the transaction dies
        raise OperationalError("insert", {}, Exception("boom"))

    monkeypatch.setattr(repository, "publish_import", failing)
    r = api.upload(pid, [("a.pdf", PDF)])
    assert r.status_code == 503, r.text
    monkeypatch.setattr(repository, "publish_import", real)
    assert api.blob_files() == []
    assert _staging_left(tmp_path) == []
    _no_rows(engine)
    assert api.upload(pid, [("a.pdf", PDF)]).status_code == 202  # still usable afterwards


def test_database_failure_keeps_blob_referenced_by_another_import(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid = api.project()
    assert api.upload(pid, [("a.pdf", PDF)]).status_code == 202
    api.worker.run_once()
    before = api.blob_files()

    def failing(*args: Any, publish_blobs: Callable[[], None] | None = None, **kw: Any) -> Any:
        assert publish_blobs is not None
        publish_blobs()
        raise OperationalError("insert", {}, Exception("boom"))

    monkeypatch.setattr(repository, "publish_import", failing)
    assert api.upload(pid, [("a2.pdf", PDF + b"x")], parent=api.latest(pid)).status_code == 503
    assert api.blob_files() == before


def test_sweep_removes_only_old_unowned_staging(tmp_path: Path) -> None:
    store = BlobStore(tmp_path)
    staging = tmp_path / "staging"
    old = staging / "old"
    old.mkdir(parents=True)
    (old / "x.part").write_bytes(b"x")
    fresh = staging / "fresh"
    fresh.mkdir()
    (fresh / "y.part").write_bytes(b"y")
    live = store.new_staging_dir(__import__("uuid").uuid4())
    (live / "z.part").write_bytes(b"z")
    past = time.time() - 7200
    for p in (old, old / "x.part", live, live / "z.part"):
        os.utime(p, (past, past))

    assert store.sweep_staging(3600) == ["old"]
    assert not old.exists() and fresh.exists() and live.exists()  # live in-flight is protected
    store.remove_staging(live)
    assert store.sweep_staging(0.5, now=time.time() + 10) == ["fresh"]


def test_sweep_does_not_follow_symlinks(tmp_path: Path) -> None:
    store = BlobStore(tmp_path / "storage")
    staging = tmp_path / "storage" / "staging"
    staging.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    os.utime(outside, (1, 1))
    (staging / "link").symlink_to(outside, target_is_directory=True)
    (staging / "file-link").symlink_to(outside / "keep.txt")
    assert store.sweep_staging(0.5, now=time.time() + 100000) == []
    assert (outside / "keep.txt").read_text() == "keep"


def test_startup_sweep_removes_orphaned_staging_after_crash(
    migrated_url: URL, tmp_path: Path
) -> None:
    orphan = tmp_path / "staging" / "crashed"
    orphan.mkdir(parents=True)
    (orphan / "f.part").write_bytes(b"partial")
    past = time.time() - 86400
    for p in (orphan, orphan / "f.part"):
        os.utime(p, (past, past))
    young = tmp_path / "staging" / "young"
    young.mkdir()
    api = make_api(migrated_url, tmp_path)
    with TestClient(api.client.app, base_url=BASE):  # runs lifespan startup
        pass
    assert not orphan.exists() and young.exists()


def test_client_disconnect_is_quiet_and_cleans_up(
    migrated_url: URL,
    engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from fieldlens.ingestion import routes

    api = make_api(migrated_url, tmp_path)
    pid = api.project()

    async def disconnect(*args: Any, **kw: Any) -> Any:
        staging: Path = args[2]
        (staging / "partial.part").write_bytes(b"half")
        raise ClientDisconnect

    monkeypatch.setattr(routes, "receive_upload", disconnect)
    with caplog.at_level(logging.INFO, logger="fieldlens.ingestion"):
        r = api.upload(pid, [("secret-name.pdf", PDF)])
    assert r.status_code == 400
    assert _staging_left(tmp_path) == [] and api.blob_files() == []
    _no_rows(engine)
    messages = " ".join(rec.getMessage() for rec in caplog.records)
    assert "aborted" in messages and "secret-name" not in messages
    assert all(rec.exc_info is None for rec in caplog.records)

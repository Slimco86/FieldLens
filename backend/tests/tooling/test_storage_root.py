"""scripts/storage_root.py adopt: typed confirmation, explicit re-pointing (TASK-070)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from tests.conftest import settings_for
from tests.jobs.test_extraction_flow import _ingest
from tests.upload_support import TEXT, make_api

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "scripts"))

import storage_root  # noqa: E402


def test_adopt_requires_typed_confirmation_then_rebinds(
    migrated_url: URL, tmp_path: Path, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = make_api(migrated_url, tmp_path / "root-a")
    _ingest(writer, [("n.txt", TEXT)])
    new_root = tmp_path / "root-b"
    new_root.mkdir()
    monkeypatch.setattr(
        storage_root, "get_settings", lambda: settings_for(migrated_url, storage_root=new_root)
    )
    lines: list[str] = []
    assert storage_root.run(["status"], out=lines.append) == 1
    assert storage_root.run(["adopt"], prompt=lambda _p: "wrong", out=lines.append) == 1
    with engine.connect() as c:
        before = c.execute(text("select root_id from storage_root_identity")).scalar_one()
    database = str(migrated_url.database)
    assert storage_root.run(["adopt"], prompt=lambda _p: database, out=lines.append) == 0
    with engine.connect() as c:
        after = c.execute(text("select root_id from storage_root_identity")).scalar_one()
    assert before != after
    assert storage_root.run(["status"], out=lines.append) == 0
    assert (new_root / ".fieldlens-root-id").is_file()
    assert "password" not in " ".join(lines).lower()


def test_adopt_aborts_cleanly_on_stdin_eof(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        storage_root, "get_settings", lambda: settings_for(migrated_url, storage_root=tmp_path)
    )

    def eof(_p: str) -> str:
        raise EOFError

    lines: list[str] = []
    assert storage_root.run(["adopt"], prompt=eof, out=lines.append) == 1
    assert any("aborted" in line for line in lines)

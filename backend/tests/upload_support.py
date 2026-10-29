"""Synthetic upload fixtures and API helpers shared by ingestion/job tests (no real data)."""

from __future__ import annotations

import io
import json
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from fieldlens.app import create_app
from fieldlens.jobs import JobWorker
from tests.conftest import settings_for

BASE = "http://127.0.0.1:8101"

PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\n%%EOF\n"
LAS = b"~Version\n VERS. 2.0 :\n~Well\n WELL. SYNTH-1 :\n~Curve\n DEPT.M : Depth\n"
TEXT = b"plain synthetic notes, not a recognised engineering format\n"
CSV = b"md,tvd\n1,1\n"


def make_pdf(tag: str) -> bytes:
    return PDF + tag.encode()


@dataclass
class Api:
    client: TestClient
    headers: dict[str, str]
    worker: JobWorker
    storage: Path

    def project(self, name: str = "P") -> str:
        r = self.client.post("/api/v1/projects", json={"name": name}, headers=self.headers)
        assert r.status_code == 201, r.text
        return str(r.json()["project_id"])

    def upload(
        self,
        project_id: str,
        files: list[tuple[str, bytes]],
        *,
        parent: str | None = None,
        hints: list[dict[str, Any]] | None = None,
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        meta: dict[str, Any] = {
            "expected_parent_source_revision_id": parent,
            "files": hints or [{} for _ in files],
        }
        if key is not None:
            meta["idempotency_key"] = key
        multipart: list[tuple[str, tuple[str | None, bytes, str]]] = [
            ("metadata", (None, json.dumps(meta).encode(), "application/json"))
        ]
        multipart += [("files", (n, b, "application/octet-stream")) for n, b in files]
        return self.client.post(
            f"/api/v1/projects/{project_id}/imports",
            files=multipart,
            headers=self.headers if headers is None else headers,
        )

    def latest(self, project_id: str) -> str | None:
        value = self.client.get(f"/api/v1/projects/{project_id}").json()[
            "latest_source_revision_id"
        ]
        return None if value is None else str(value)

    def documents(self, project_id: str, revision: str | None = None) -> list[dict[str, Any]]:
        q = f"?source_revision_id={revision}" if revision else ""
        r = self.client.get(f"/api/v1/projects/{project_id}/documents{q}")
        assert r.status_code == 200, r.text
        return list(r.json()["items"])

    def revisions(self, project_id: str) -> list[dict[str, Any]]:
        r = self.client.get(f"/api/v1/projects/{project_id}/source-revisions")
        assert r.status_code == 200, r.text
        return list(r.json()["items"])

    def job(self, project_id: str, job_id: str) -> dict[str, Any]:
        r = self.client.get(f"/api/v1/projects/{project_id}/jobs/{job_id}")
        assert r.status_code == 200, r.text
        return dict(r.json())

    def blob_files(self) -> list[Path]:
        return sorted(p for p in (self.storage / "projects").rglob("*") if p.is_file())


def make_api(url: URL, storage: Path, **overrides: Any) -> Api:
    settings = settings_for(url, storage_root=storage, job_worker_enabled=False, **overrides)
    app = create_app(settings)
    client = TestClient(app, base_url=BASE)  # no lifespan: the worker is driven explicitly
    token = client.get("/api/v1/session").json()["csrf_token"]
    return Api(client, {"X-FieldLens-Token": token}, app.state.job_worker, storage)


def zip_bytes(entries: list[tuple[str, bytes]], *, compress: bool = True) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED) as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


def zip_with_symlink() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        info = zipfile.ZipInfo("xl/link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def minimal_xlsx() -> bytes:
    return zip_bytes(
        [
            ("[Content_Types].xml", b"<Types/>"),
            ("xl/workbook.xml", b"<workbook/>"),
            ("xl/worksheets/sheet1.xml", b"<worksheet/>"),
        ]
    )


def uid(value: str) -> UUID:
    return UUID(value)

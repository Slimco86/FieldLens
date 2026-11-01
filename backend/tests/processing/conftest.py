"""Processing-run test world: synthetic PDFs through the real upload pipeline, stub provider only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL

from fieldlens.persistence.session import session_scope
from fieldlens.processing.runtime import ProcessingRuntime
from fieldlens.processing.steps import StubProvider, StubStep
from tests.candidates.pdfs import PdfPage, make_pdf
from tests.upload_support import Api, make_api

FILLER = ["Daily drilling report", "Mud weight 1.25 sg", "Rig crew on shift"]


def pdf_of(pages: int, tag: str) -> bytes:
    return make_pdf([PdfPage(lines=[f"{tag} page {i}", *FILLER]) for i in range(1, pages + 1)])


@dataclass
class World:
    api: Api
    project_id: str
    docs: dict[str, str]

    @property
    def rt(self) -> ProcessingRuntime:
        runtime: ProcessingRuntime = self.api.client.app.state.processing
        return runtime

    @property
    def provider(self) -> StubProvider:
        assert isinstance(self.rt.provider, StubProvider)
        return self.rt.provider

    @property
    def step(self) -> StubStep:
        assert isinstance(self.rt.step, StubStep)
        return self.rt.step

    @property
    def base(self) -> str:
        return f"/api/v1/projects/{self.project_id}/processing"

    def estimate(
        self, *names: str, pages: dict[str, tuple[int, int]] | None = None, **extra: Any
    ) -> Any:
        selection = []
        for name in names:
            item: dict[str, Any] = {"document_id": self.docs[name]}
            if pages and name in pages:
                item["pages"] = {"page_start": pages[name][0], "page_end": pages[name][1]}
            selection.append(item)
        return self.api.client.post(
            f"{self.base}/runs/estimates",
            json={"documents": selection, **extra},
            headers=self.api.headers,
        )

    def confirm(self, run: dict[str, Any], **override: Any) -> Any:
        body = {"estimated_usd": run["estimate"]["estimated_usd"], **override}
        return self.api.client.post(
            f"{self.base}/runs/{run['run_id']}/confirm", json=body, headers=self.api.headers
        )

    def get(self, run_id: str) -> dict[str, Any]:
        r = self.api.client.get(f"{self.base}/runs/{run_id}")
        assert r.status_code == 200, r.text
        return dict(r.json())

    def cancel(self, run_id: str) -> Any:
        return self.api.client.post(f"{self.base}/runs/{run_id}/cancel", headers=self.api.headers)

    def retry(self, run_id: str) -> Any:
        return self.api.client.post(f"{self.base}/runs/{run_id}/retry", headers=self.api.headers)

    def states(self) -> dict[str, dict[str, Any]]:
        r = self.api.client.get(f"{self.base}/documents")
        assert r.status_code == 200, r.text
        return {i["original_filename"]: i for i in r.json()["items"]}

    def drain(self) -> int:
        handled = 0
        while self.rt.runner.run_once():
            handled += 1
        return handled

    def sql(self, sql: str, **params: Any) -> Any:
        with session_scope(self.api.client.app.state.session_factory) as s:
            result = s.execute(text(sql), params)
            return result.all() if result.returns_rows else []


def build_world(migrated_url: URL, tmp_path: Path, **settings: Any) -> World:
    api = make_api(migrated_url, tmp_path, **settings)
    pid = api.project("Processing")
    files = [
        ("scan.pdf", pdf_of(2, "scan")),
        ("report.pdf", pdf_of(5, "report")),
        ("other.pdf", pdf_of(3, "other")),
        ("fourth.pdf", pdf_of(1, "fourth")),
        ("notes.txt", b"plain synthetic notes, not a recognised engineering format\n"),
    ]
    assert api.upload(pid, files, hints=[{"categories": []} for _ in files]).status_code in (
        200,
        201,
        202,
    )
    while api.worker.run_once():
        pass
    while api.worker.extraction.run_once():
        pass
    while api.worker.run_once():
        pass
    revision = api.latest(pid)
    assert revision is not None
    docs = {d["original_filename"]: str(d["document_id"]) for d in api.documents(pid, revision)}
    return World(api, pid, docs)


@pytest.fixture
def world(migrated_url: URL, tmp_path: Path) -> World:
    return build_world(migrated_url, tmp_path)


def uid(value: str) -> UUID:
    return UUID(value)

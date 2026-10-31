"""Fixtures for the activity-log tests: two real projects with imported revisions (PostgreSQL)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy.engine import URL

from fieldlens.activity import ActivityLog
from fieldlens.contracts.evidence import EvidenceLink
from tests.upload_support import LAS, TEXT, Api, make_api


@dataclass
class Project:
    project_id: UUID
    revisions: list[UUID]
    documents: list[UUID]  # one document per revision, same order

    def link(self, index: int = 0, line: int = 1) -> EvidenceLink:
        return EvidenceLink.model_validate(
            {
                "document_id": self.documents[index],
                "source_revision_id": self.revisions[index],
                "locator": {
                    "kind": "text",
                    "document_id": self.documents[index],
                    "source_revision_id": self.revisions[index],
                    "line_start": line,
                    "line_end": line,
                },
            }
        )


@dataclass
class World:
    api: Api
    log: ActivityLog
    a: Project
    b: Project

    def url(self, project: Project, suffix: str = "") -> str:
        return f"/api/v1/projects/{project.project_id}/agent-units{suffix}"


def _project(api: Api, name: str, payloads: list[bytes]) -> Project:
    pid = api.project(name)
    revisions: list[UUID] = []
    documents: list[UUID] = []
    for payload in payloads:
        parent = api.latest(pid)
        assert api.upload(pid, [("src.txt", payload)], parent=parent).status_code in (200, 201, 202)
        while api.worker.run_once():
            pass
        latest = api.latest(pid)
        assert latest is not None
        revisions.append(UUID(latest))
        documents.append(UUID(api.documents(pid, latest)[0]["document_id"]))
    return Project(UUID(pid), revisions, documents)


@pytest.fixture
def world(migrated_url: URL, tmp_path: Path) -> World:
    api = make_api(migrated_url, tmp_path)
    a = _project(api, "A", [TEXT, LAS])
    b = _project(api, "B", [TEXT + b"b"])
    return World(api, ActivityLog(api.client.app.state.session_factory), a, b)

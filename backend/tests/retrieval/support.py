"""Seeding helpers for retrieval tests: real projects/uploads/revisions in PostgreSQL, with
extracted records inserted directly so every fixture value is controlled (synthetic, invented).

Records are written exactly like ``ExtractionRunner._finalize_ok`` writes them, so the index
runner, eligibility rules and search exercise the production tables."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import insert, text, update
from sqlalchemy.engine import URL

from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope
from fieldlens.retrieval.embedder import Embedder, EmbedderProvider
from tests.upload_support import Api, make_api


def attr(
    key: str,
    original: str | None,
    unit: str | None = None,
    *,
    number: float | None = None,
    state: str = "unreviewed",
    unknown: str | None = None,
    reference: str | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "locator": {"kind": "text", "line_start": 1, "line_end": 1},
        "original_text": original,
        "number": number,
        "unit": unit,
        "unit_status": "stated" if unit else "missing" if number is not None else "not_applicable",
        "reference": reference,
        "text": original if number is None and original is not None else None,
        "unknown_reason": unknown,
        "normalized_number": None,
        "normalized_unit": None,
        "validation_state": state,
    }


def rec(
    kind: str,
    subject: dict[str, str],
    attrs: list[dict[str, Any]],
    *,
    locator: dict[str, Any] | None = None,
    state: str = "unreviewed",
    when: str | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "subject": subject,
        "locator": locator or {"kind": "text", "line_start": 1, "line_end": 1},
        "attributes": attrs,
        "validation_state": state,
        "effective_time": {"literal": when, "precision": "day", "timezone": None} if when else None,
    }


@dataclass
class Doc:
    document_id: UUID
    run_id: UUID
    revision_id: UUID
    name: str


@dataclass
class World:
    api: Api
    url: URL
    docs: dict[str, Doc] = field(default_factory=dict)

    @property
    def factory(self) -> Any:
        return self.api.client.app.state.session_factory

    @property
    def provider(self) -> EmbedderProvider:
        provider: EmbedderProvider = self.api.client.app.state.embedders
        return provider

    def set_embedder(self, embedder: Embedder | None) -> None:
        self.provider._embedder = embedder
        self.provider._failure = None

    def project(self, name: str = "P") -> str:
        return self.api.project(name)

    def add_doc(
        self,
        pid: str,
        name: str,
        records: list[dict[str, Any]],
        *,
        run_status: str = "succeeded",
        coverage: dict[str, Any] | None = None,
        replaces: UUID | None = None,
        summary: dict[str, Any] | None = None,
    ) -> Doc:
        payload = f"{name}:{len(records)}:{hashlib.sha1(repr(records).encode()).hexdigest()}"  # noqa: S324
        hints = [{"replaces_document_id": str(replaces)}] if replaces else None
        parent = self.api.latest(pid)
        r = self.api.upload(pid, [(name, payload.encode())], parent=parent, hints=hints)
        assert r.status_code in (200, 201, 202), r.text
        while self.api.worker.run_once():
            pass
        revision = UUID(self.api.latest(pid) or "")
        document_id = UUID(str(r.json()["created_document_ids"][0]))
        with session_scope(self.factory) as session:
            sha = session.execute(
                text("SELECT sha256 FROM source_document WHERE document_id = :d"),
                {"d": document_id},
            ).scalar_one()
            run_id = session.execute(
                insert(m.extraction_run)
                .values(
                    project_id=UUID(pid),
                    document_id=document_id,
                    source_revision_id=revision,
                    profile_name="synthetic",
                    profile_version="1",
                    method="test",
                    content_sha256=sha,
                    status=run_status,
                    coverage=coverage
                    or {"unit": "record", "inspected": len(records), "total": len(records)},
                    summary=summary or {},
                )
                .returning(m.extraction_run.c.run_id)
            ).scalar_one()
            if records:
                session.execute(
                    insert(m.extracted_record),
                    [
                        {
                            "project_id": UUID(pid),
                            "run_id": run_id,
                            "document_id": document_id,
                            "ordinal": i,
                            **rec_,
                        }
                        for i, rec_ in enumerate(records)
                    ],
                )
            session.execute(
                update(m.document_processing)
                .where(m.document_processing.c.document_id == document_id)
                .values(extraction_state="extracted")
            )
        doc = Doc(document_id, run_id, revision, name)
        self.docs[name] = doc
        return doc

    def index(self, limit: int = 200) -> int:
        """Drain the index runner (chunks first, then embeddings)."""
        done = 0
        self.api.worker.indexing.cleanup_interval_s = 0.0  # sweep stale data on every poll
        while done < limit and self.api.worker.indexing.run_once():
            done += 1
        return done

    def search(self, pid: str, q: str, **params: Any) -> dict[str, Any]:
        r = self.api.client.get(
            f"/api/v1/projects/{pid}/retrieval/search", params={"q": q, **params}
        )
        assert r.status_code == 200, r.text
        return dict(r.json())

    def coverage(self, pid: str, **params: Any) -> dict[str, Any]:
        r = self.api.client.get(f"/api/v1/projects/{pid}/retrieval/coverage", params=params)
        assert r.status_code == 200, r.text
        return dict(r.json())

    def sql(self, statement: str, **params: Any) -> list[Any]:
        with session_scope(self.factory) as session:
            result = session.execute(text(statement), params)
            return list(result.all()) if result.returns_rows else []


def make_world(url: URL, tmp_path: Path, **overrides: Any) -> World:
    overrides.setdefault("embedding_provider", "fake")
    overrides.setdefault("retrieval_vector_support_floor", 0.3)  # fake-embedder test value
    return World(make_api(url, tmp_path, **overrides), url)

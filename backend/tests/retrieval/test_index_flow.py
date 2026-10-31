"""End-to-end: upload -> native-profile extraction -> index job -> API search/coverage, plus the
read API contract (bounds, scoping, no-store). Synthetic LAS/XLSX uploads, PostgreSQL."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.engine import URL

from fieldlens.profiles import registry
from tests.profile_support import xlsx_bytes
from tests.retrieval.support import make_world
from tests.test_profiles_sources import LAS
from tests.upload_support import TEXT


def _run_everything(api: Any) -> None:
    api.worker.indexing.cleanup_interval_s = 0.0  # stale derived data is swept on every poll
    for _ in range(100):
        handled = api.worker.run_once() or api.worker.extraction.run_once()
        handled = api.worker.indexing.run_once() or handled
        if not handled:
            return
    raise AssertionError("worker never went idle")


def test_uploaded_las_is_extracted_indexed_and_searchable_with_locators(
    migrated_url: URL, tmp_path: Path
) -> None:
    world = make_world(migrated_url, tmp_path, retrieval_min_vector_similarity=0.3)
    api = world.api
    pid = api.project()
    wb = xlsx_bytes({"Sheet1": [["well", "depth_m"], ["15/9-F-77", 1234.5]]})
    assert api.upload(
        pid, [("log.las", LAS.encode()), ("notes.txt", TEXT), ("b.xlsx", wb)]
    ).status_code in (
        200,
        201,
        202,
    )
    _run_everything(api)
    cov = world.coverage(pid)
    by_name = {d["filename"]: d for d in cov["documents"]}
    assert by_name["log.las"]["text_index"] == "complete" and by_name["log.las"]["chunk_count"] >= 1
    assert by_name["log.las"]["vector_index"] == "complete"
    assert by_name["notes.txt"]["text_index"] == "not_indexable"
    assert any("no native profile" in x for x in by_name["notes.txt"]["not_indexed"])
    out = world.search(pid, "RHOB density curve")
    assert out["mode"] == "hybrid"
    hit = out["hits"][0]
    assert "las_curve" in hit["text"] and "RHOB" in hit["text"]
    assert hit["evidence"][0]["locator"]["kind"] == "text"
    assert hit["evidence"][0]["locator"]["line_start"] >= 1
    assert hit["label"] == "source_observation" and hit["resolved_entity_id"] is None
    # the original record remains the authority: ids resolve through the extraction API
    doc = hit["document_id"]
    records = api.client.get(f"/api/v1/projects/{pid}/documents/{doc}/extraction/records").json()[
        "items"
    ]
    assert set(hit["record_ids"]) <= {r["record_id"] for r in records}
    assert out["unmatched_identifiers"] == []
    exact = world.search(pid, "15/9-F-99")
    assert exact["exact_matches"] and exact["hits"][0]["document_id"] == doc


def test_profile_version_bump_supersedes_the_run_and_reindexes(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = make_world(migrated_url, tmp_path, retrieval_min_vector_similarity=0.3)
    api = world.api
    pid = api.project()
    api.upload(pid, [("log.las", LAS.encode())])
    _run_everything(api)
    old = world.sql("SELECT DISTINCT run_id FROM evidence_chunk")
    assert len(old) == 1
    did = api.documents(pid)[0]["document_id"]
    monkeypatch.setattr(type(registry.by_name("las_2_0")), "version", "9999.0.0")
    api.client.post(f"/api/v1/projects/{pid}/documents/{did}/extraction", headers=api.headers)
    _run_everything(api)
    new = world.sql("SELECT DISTINCT run_id FROM evidence_chunk")
    assert len(new) == 1 and new[0][0] != old[0][0]  # stale chunks deleted, new run indexed
    assert world.search(pid, "RHOB density")["hits"]


def test_read_api_contract_and_bounds(migrated_url: URL, tmp_path: Path) -> None:
    world = make_world(migrated_url, tmp_path)
    api = world.api
    pid = api.project()
    base = f"/api/v1/projects/{pid}/retrieval"
    empty = api.client.get(f"{base}/coverage").json()
    assert empty["source_revision_id"] is None and empty["documents"] == []
    nothing = api.client.get(f"{base}/search", params={"q": "anything"})
    assert nothing.status_code == 200 and nothing.headers["cache-control"] == "no-store"
    assert nothing.json()["status"] == "unavailable" and nothing.json()["hits"] == []
    for bad in ({"q": ""}, {"q": "x" * 501}, {"q": "x", "limit": 0}, {"q": "x", "limit": "ten"}):
        assert api.client.get(f"{base}/search", params=bad).status_code == 422
    assert api.client.get(f"{base}/search").status_code == 422
    unknown_rev = api.client.get(
        f"{base}/search",
        params={"q": "x", "source_revision_id": "00000000-0000-4000-8000-0000000000aa"},
    )
    assert unknown_rev.status_code == 404
    assert api.client.get(f"/api/v1/projects/{pid}x/retrieval/coverage").status_code in (404, 422)
    # read-only: no mutation verbs are routed
    assert api.client.post(f"{base}/search", headers=api.headers).status_code == 405

"""TASK-087 B-2: readable evidence composed at read time from stored records (PostgreSQL).

No model call, no document file I/O and no S5 rerun: an already-stored spec (quote only) gains
filename, locator and statement when read; the number of queries does not grow with components."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import event, text

from fieldlens.assetspec.live_designer import design_without_model
from fieldlens.assetspec.readable import compose_statement, human_locator
from tests.assetspec.test_structured import F5_LIKE, A, T, _seeded, seed_records
from tests.candidates.conftest import World


def _read(world: World, wb: UUID) -> Any:
    r = world.api.client.get(f"/api/v1/projects/{world.project_id}/wellbores/{wb}/asset-spec")
    assert r.status_code == 200, r.text
    return r.json()


def test_stored_structured_spec_reads_with_filename_locator_and_statement(world: World) -> None:
    pid, wb = _seeded(world)
    assert design_without_model(world.factory, pid, wb, "run-1").ok
    spec = _read(world, wb)["spec"]
    shoe = next(c for c in spec["components"] if "20 in" in c["label"])
    ev = shoe["evidence"][0]
    assert ev["quote"].startswith("extracted_record ")  # stored data is unchanged
    assert ev["filename"] and ev["filename"] == world.scalar(
        "select original_filename from source_document where document_id = :d",
        d=world.imageonly_doc,
    )
    assert ev["locator"] == "page 3"
    assert ev["statement"] == "Casing 0.508 m at 400 m MD (20 in shoe)"
    assert all(
        e.get("filename") and e.get("locator") is not None or e.get("locator") is None
        for c in spec["components"]
        for e in c["evidence"]
    )
    xml = next(c for c in spec["components"] if c["label"] and c["kind"] == "tubing")
    assert xml["evidence"][0]["statement"].startswith("Tubular:")
    # history enriches too
    h = world.api.client.get(f"/api/v1/projects/{pid}/wellbores/{wb}/asset-spec/history").json()
    assert h["items"][0]["spec"]["components"][0]["evidence"][0]["filename"]


def test_enrichment_is_stored_nowhere_and_old_specs_improve_without_rerun(world: World) -> None:
    pid, wb = _seeded(world)
    assert design_without_model(world.factory, pid, wb, "run-1").ok
    stored = world.scalar("select spec::text from wellbore_asset_spec limit 1")
    assert "statement" not in stored and "filename" not in stored
    assert "statement" in str(_read(world, wb))


def _count_queries(world: World, wb: UUID) -> int:
    engine = world.factory.kw["bind"]
    seen: list[str] = []

    def hook(*args: Any) -> None:
        seen.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", hook)
    try:
        _read(world, wb)
    finally:
        event.remove(engine, "before_cursor_execute", hook)
    return len(seen)


def test_query_count_is_bounded_regardless_of_component_count(world: World) -> None:
    pid, wb = _seeded(world)
    assert design_without_model(world.factory, pid, wb, "run-1").ok
    small = _count_queries(world, wb)
    many = [
        (
            "casing_point",
            [
                T("casing_point.name", f"Shoe {i}"),
                A("casing_point.md", 100.0 + i),
                A("casing_point.casing_diameter", 0.2 + i / 1000),
            ],
            {"page": 3 + i % 5},
        )
        for i in range(60)
    ]
    seed_records(world, world.imageonly_doc, wb, [*F5_LIKE, *many])
    assert design_without_model(world.factory, pid, wb, "run-2").ok
    spec = _read(world, wb)["spec"]
    assert len(spec["components"]) > 30
    assert all("filename" in c["evidence"][0] for c in spec["components"] if c["evidence"])
    assert _count_queries(world, wb) == small  # O(1) batched queries, not per component


def test_missing_record_still_gets_filename_and_page_locator(world: World) -> None:
    pid, wb = _seeded(world)
    assert design_without_model(world.factory, pid, wb, "run-1").ok
    with world.factory.begin() as s:  # the record is gone: degrade, never fail
        s.execute(text("delete from record_wellbore_link"))
        s.execute(text("delete from extracted_record"))
    spec = _read(world, wb)["spec"]
    ev = next(c for c in spec["components"] if "20 in" in c["label"])["evidence"][0]
    assert ev["filename"] and ev["locator"] == "page 3" and ev["statement"] is None


def test_composers_are_readable_and_bounded() -> None:
    assert human_locator({"page": 3, "table_id": "2", "row": 5}) == "page 3, table 2, row 5"
    assert human_locator({"line": 14}) == "line 14"
    assert human_locator({"kind": "xml", "element_path": "/a/b"}) == "/a/b"
    assert human_locator({}, 7) == "page 7" and human_locator({}) is None
    stmt = compose_statement(
        "casing_point",
        [
            {"key": "casing_point.casing_diameter", "original_text": '9 5/8"'},
            {"key": "casing_point.md", "original_text": "2,431", "unit": "m"},
        ],
    )
    assert stmt == 'Casing 9 5/8" at 2,431 m MD'
    assert compose_statement("bha_run", []) is None

"""TASK-085 (spec §16 F2): S5 designs from the wellbore's structured records, deterministically.

Synthetic ``extracted_record`` rows in PostgreSQL (shapes of the native parsers); no model call."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from fieldlens.assetspec import service
from fieldlens.assetspec.live_designer import NO_DATA, design_without_model
from fieldlens.reconstruction.design_stage import DesignAssetExecutor
from tests.assetspec.test_api import _seed
from tests.assetspec.test_live_designer import GOOD, _comps, _ctx, _current, _designer, _reply
from tests.candidates.conftest import World


def A(key: str, number: float, unit: str = "m", **over: Any) -> dict[str, Any]:
    """Native attribute with a printed number already normalized to metres."""
    base = {
        "key": key,
        "original_text": f"{number:g}",
        "number": number,
        "unit": unit,
        "normalized_number": number,
        "normalized_unit": "m",
        "validation_state": "valid",
        "reference": "MD",
    }
    base.update(over)
    return base


def T(key: str, value: str) -> dict[str, Any]:
    return {"key": key, "original_text": value, "text": value, "validation_state": "valid"}


def f99(world: World) -> UUID:
    return UUID(str(world.scalar("select wellbore_id from wellbore where name = '15/9-F-99'")))


def seed_records(
    world: World,
    doc: UUID,
    wb: UUID,
    records: list[tuple[str, list[dict[str, Any]], dict[str, Any]]],
    profile: str = "witsml_tubular",
) -> None:
    """One current native run for ``doc`` (any earlier run is superseded) with the records linked
    to ``wb``."""
    run = uuid4()
    with world.factory.begin() as s:
        s.execute(
            text("update extraction_run set superseded = true where document_id = :d"), {"d": doc}
        )
        s.execute(
            text(
                "insert into extraction_run (run_id, project_id, document_id, source_revision_id, "
                "profile_name, profile_version, method, content_sha256, status) values "
                "(:r, :p, :d, :rev, cast(:prof as text), '1', 'native_xml', :sha, 'succeeded')"
            ),
            {
                "r": run,
                "p": world.project_id,
                "d": doc,
                "rev": world.revision_id,
                "sha": "a" * 64,
                "prof": profile,
            },
        )
        for ordinal, (kind, attrs, locator) in enumerate(records, start=1):
            s.execute(
                text(
                    "insert into extracted_record (project_id, run_id, document_id, ordinal, kind, "
                    "subject, locator, validation_state, attributes) values (:p, :r, :d, :o, :k, "
                    "'{}'::jsonb, cast(:loc as jsonb), 'valid', cast(:a as jsonb))"
                ),
                {
                    "p": world.project_id,
                    "r": run,
                    "d": doc,
                    "o": ordinal,
                    "k": kind,
                    "loc": json.dumps(locator),
                    "a": json.dumps(attrs),
                },
            )
            s.execute(
                text(
                    "insert into record_wellbore_link (run_id, ordinal, project_id, wellbore_id, "
                    "basis) values (:r, :o, :p, :w, 'document_subject')"
                ),
                {"r": run, "o": ordinal, "p": world.project_id, "w": wb},
            )


F5_LIKE: list[tuple[str, list[dict[str, Any]], dict[str, Any]]] = [
    ("casing_point", [T("casing_point.name", "20 in shoe"), A("casing_point.md", 400.0),
                      A("casing_point.casing_diameter", 0.508)], {"page": 3}),
    ("casing_point", [T("casing_point.name", "13 3/8 in shoe"), A("casing_point.md", 1200.0),
                      A("casing_point.casing_diameter", 0.340)], {"page": 3}),
    ("casing_point", [T("casing_point.name", "9 5/8 in shoe"), A("casing_point.md", 2700.0)],
     {"page": 3}),  # no printed diameter
    ("tubular_component", [T("tubular_component.type_tubular_comp", "tubing"),
                           A("tubular_component.od", 0.114), A("tubular_component.id", 0.100),
                           A("tubular_component.len", 2000.0)], {"source_uids": ["asm", "c1"]}),
    ("wb_geometry_section", [T("wb_geometry_section.type_hole_casing", "casing"),
                             A("wb_geometry_section.od_section", 0.244),
                             A("wb_geometry_section.id_section", 0.220),
                             A("wb_geometry_section.md_top", 0.0),
                             A("wb_geometry_section.md_bottom", 2500.0)], {}),
    ("wb_geometry_section", [T("wb_geometry_section.type_hole_casing", "hole"),
                             A("wb_geometry_section.od_section", 0.216),
                             A("wb_geometry_section.md_top", 2500.0),
                             A("wb_geometry_section.md_bottom", 2900.0)], {}),
    ("bha_run", [T("bha_run.name", "BHA 1")], {}),
]  # fmt: skip


def _seeded(world: World) -> tuple[UUID, UUID]:
    wb = f99(world)
    seed_records(world, world.imageonly_doc, wb, F5_LIKE)
    return world.project_id, wb


def test_f5_like_records_give_a_validated_labelled_spec_without_a_model(world: World) -> None:
    pid, wb = _seeded(world)
    out = design_without_model(world.factory, pid, wb, "run-1")
    assert out.ok and out.record is not None, out.message
    assert "from structured records" in out.message
    rec = _current(world, pid, wb)
    assert rec.revision == 1 and rec.spec.generator.provider == "structured"
    comps = {c.label: c for c in rec.spec.components}
    assert all(c.label.strip() for c in rec.spec.components)
    shoe = next(c for c in rec.spec.components if "20 in" in c.label)
    assert shoe.placement.state == "located" and shoe.placement.md_bottom == 400.0
    assert shoe.representation == "source_dimensioned" and shoe.params is not None
    assert shoe.evidence[0].document_id == world.imageonly_doc
    assert "witsml_tubular" in shoe.evidence[0].quote and "page=3" in shoe.evidence[0].quote
    nodia = next(c for c in rec.spec.components if "9 5/8" in c.label)
    assert nodia.representation == "generic_illustrative" and nodia.params is None  # not invented
    assert "Missing" in (nodia.confidence_note or "")
    section = next(
        c
        for c in rec.spec.components
        if c.placement.state == "located"
        and c.placement.md_top == 0.0
        and c.placement.md_bottom == 2500.0
    )
    assert section.representation == "source_dimensioned"
    assert any(
        c.placement.md_top == 2500.0 and c.placement.md_bottom == 2900.0
        for c in rec.spec.components
        if c.placement.state == "located"
    )  # hole section
    assert any(c.kind.value == "perforation_interval" for c in rec.spec.components)
    assert not any("BHA" in label for label in comps)  # a BHA run is an intervention tool
    assert out.counts["intervention_tools_skipped"] == 1
    assert out.counts["structured"] >= 7 and out.counts["model_read"] == 0


def test_rerun_with_unchanged_inputs_makes_no_new_revision(world: World) -> None:
    pid, wb = _seeded(world)
    first = design_without_model(world.factory, pid, wb, "run-1")
    again = design_without_model(world.factory, pid, wb, "run-2")
    assert first.ok and again.ok and "unchanged" in again.message
    rec = _current(world, pid, wb)
    assert rec.revision == 1 and again.counts["unchanged"] == 1
    with (
        world.factory.begin() as s
    ):  # a merge invalidation is respected: next run is a new revision
        assert service.invalidate_current(s, pid, wb)
    design_without_model(world.factory, pid, wb, "run-3")
    assert _current(world, pid, wb).revision == 2


def test_conflicting_or_out_of_range_dimensions_are_left_generic(world: World) -> None:
    wb = f99(world)
    seed_records(
        world,
        world.imageonly_doc,
        wb,
        [
            ("casing_point", [T("casing_point.name", "Huge"), A("casing_point.md", 900.0),
                              A("casing_point.casing_diameter", 99.0)], {}),
            ("casing_point", [T("casing_point.name", "Bad"), A("casing_point.md", 950.0),
                              A("casing_point.casing_diameter", 0.3, validation_state="conflicting")],
             {}),
        ],
    )  # fmt: skip
    out = design_without_model(world.factory, world.project_id, wb, "run-1")
    assert out.ok
    rec = _current(world, world.project_id, wb)
    for label in ("Huge", "Bad"):
        c = next(c for c in rec.spec.components if label in c.label)
        assert c.representation == "generic_illustrative" and c.params is None
        assert "Missing" in (c.confidence_note or "")


def test_no_equipment_data_only_when_both_sources_are_empty(world: World) -> None:
    out = design_without_model(world.factory, world.project_id, uuid4(), "run-1")
    assert out.ok and out.message == NO_DATA and out.counts == {"designed": 0}


def test_stage_without_model_stores_the_structured_spec(world: World) -> None:
    pid, wb = _seeded(world)
    ex = DesignAssetExecutor(None)
    with world.factory() as s:
        plan = ex.plan(s, pid)
    assert plan.availability == "will_run" and plan.new_work >= 1
    res = ex.run(_ctx(world, pid, wb))
    assert res.state == "succeeded" and "from structured records" in (res.message or "")
    assert _current(world, pid, wb).spec.components
    empty = ex.run(_ctx(world, pid, uuid4()))
    assert empty.state == "stubbed" and "No equipment data" in (empty.message or "")


def test_live_model_is_not_called_when_nothing_needs_labelling(world: World) -> None:
    pid, wb = _seeded(world)
    d, provider = _designer(world, [])
    out = d.design(pid, wb, "run-1")
    assert out.ok and not provider.calls and out.usd == 0
    assert _current(world, pid, wb).spec.generator.provider == "structured"


def test_structured_and_model_read_items_both_appear(world: World) -> None:
    pid_s, wb_s = _seed(world)  # model-read candidates for F-99
    wb = UUID(wb_s)
    seed_records(world, world.imageonly_doc, wb, F5_LIKE)
    d, provider = _designer(world, [_reply(*GOOD)])
    out = d.design(UUID(pid_s), wb, "run-1")
    assert out.ok and len(provider.calls) == 1, out.message
    labels = {c.label for c in _current(world, UUID(pid_s), wb).spec.components}
    assert "Production packer" in labels and "Test separator" in labels  # model-read
    assert any("20 in" in label for label in labels)  # structured
    assert out.counts["structured"] >= 7 and out.counts["model_read"] >= 3
    assert "from model-read items" in out.message
    assert _comps(_current(world, UUID(pid_s), wb))


def _section(top: float, bottom: float, od: float, name: str = "casing") -> Any:
    return (
        "wb_geometry_section",
        [
            T("wb_geometry_section.type_hole_casing", name),
            A("wb_geometry_section.od_section", od),
            A("wb_geometry_section.md_top", top),
            A("wb_geometry_section.md_bottom", bottom),
        ],
        {},
    )


def _shoe(md: float, od: float | None, name: str = '9 5/8" casing') -> Any:
    attrs = [T("casing_point.name", name), A("casing_point.md", md)]
    if od is not None:
        attrs.append(A("casing_point.casing_diameter", od))
    return ("casing_point", attrs, {})


def test_shoe_is_folded_into_its_string_keeping_both_evidences(world: World) -> None:
    wb = f99(world)
    seed_records(
        world,
        world.imageonly_doc,
        wb,
        [_section(0.0, 2921.0, 0.2445), _shoe(2921.0, 0.2445), _shoe(5000.0, 0.508, "30 in")],
    )
    out = design_without_model(world.factory, world.project_id, wb, "run-1")
    assert out.ok and out.counts["structured_merged"] == 1
    comps = _current(world, world.project_id, wb).spec.components
    string = [c for c in comps if c.placement.state == "located" and c.placement.md_top == 0.0]
    assert len(string) == 1 and "shoe 2921" in string[0].label
    assert len(string[0].evidence) == 2  # section + shoe records
    bare = [c for c in comps if "30 in" in c.label]  # no covering section: the marker stays
    assert len(bare) == 1 and bare[0].placement.md_bottom == 5000.0
    assert not [c for c in comps if c.placement.md_bottom == 2921.0 and c is not string[0]]  # type: ignore[union-attr]


def test_shoe_and_string_with_different_ods_are_both_kept_and_reported(world: World) -> None:
    wb = f99(world)
    seed_records(
        world,
        world.imageonly_doc,
        wb,
        [_section(0.0, 2921.0, 0.340), _shoe(2921.0, 0.2445)],
    )
    out = design_without_model(world.factory, world.project_id, wb, "run-1")
    assert out.ok and out.counts["structured_conflicts"] == 1
    assert "OD conflict" in out.message
    comps = _current(world, world.project_id, wb).spec.components
    assert sum(1 for c in comps if "Conflict" in (c.confidence_note or "")) == 2


def test_intervention_tools_are_not_permanent_equipment(world: World) -> None:
    wb = f99(world)
    seed_records(
        world,
        world.imageonly_doc,
        wb,
        [
            ("bha_run", [T("bha_run.name", "Spear run")], {}),
            ("bha_run", [T("bha_run.name", "Installed liner hanger")], {}),
            _shoe(900.0, 0.34),
        ],
    )
    out = design_without_model(world.factory, world.project_id, wb, "run-1")
    labels = [c.label for c in _current(world, world.project_id, wb).spec.components]
    assert out.counts["intervention_tools_skipped"] == 1
    assert not any("Spear" in label for label in labels)
    assert any("Installed liner hanger" in label for label in labels)

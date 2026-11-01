"""TASK-041 hardening of the shared validators (TASK-036 QA follow-ups a-d): a unit written away
from its value, item-to-depth association, a page that names a different well, `95/8`."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fieldlens.candidates.textmatch import parse_quantity, unit_words
from fieldlens.candidates.validators import association_text
from tests.candidates.conftest import World
from tests.candidates.helpers import loc, meas, page_item, rows, run_cands


def _hard(w: World, key: str, value: str, unit: str | None, quote: str, a: int, b: int) -> dict:
    return meas(
        w,
        attribute_key=key,
        value_text=value,
        unit=unit,
        quote=quote,
        locator=loc(w.hard_doc, a, b),
        subject={"wellbore_label": "15/9-F-99"},
    )


def _one(w: World, cand: dict[str, Any], q: str) -> dict[str, Any]:
    out, _ = run_cands(w, [cand], doc=w.hard_doc, line_range=(1, 5), question=q)
    assert out.state == "succeeded"
    r = rows(w)[-1]
    r["attrs"] = json.loads(r["attributes"])
    return r


def test_unit_away_from_value_is_flagged_not_defaulted(world: World) -> None:
    # (a) "Set 3000 MD ft" claimed as metres: the quote writes ft, not next to the value
    r = _one(
        world,
        _hard(world, "perforation.top_md", "3000", "m", "15/9-F-99 Set 3000 MD ft", 1, 1),
        "a1",
    )
    assert r["state"] == "flagged" and "unit_away_from_value" in r["reasons"]
    assert r["attrs"]["normalized_number"] is None and not r["attrs"]["unit_defaulted"]
    # no claim at all: still no unambiguous association
    r = _one(
        world,
        _hard(world, "perforation.top_md", "3000", None, "15/9-F-99 Set 3000 MD ft", 1, 1),
        "a2",
    )
    assert r["state"] == "flagged" and "unit_away_from_value" in r["reasons"]
    assert not r["attrs"]["unit_defaulted"]
    # two different units in the quote and none next to the value
    r = _one(
        world,
        _hard(
            world, "perforation.top_md", "4160", "m", "Packer 4160 m MD ; liner 2000 ft MD", 2, 2
        ),
        "a3",
    )
    assert r["attrs"]["unit_source"] == "quote"  # 4160 m: the unit IS next to the value
    r = _one(
        world,
        _hard(
            world, "perforation.top_md", "2000", "ft", "Packer 4160 m MD ; liner 2000 ft MD", 2, 2
        ),
        "a4",
    )
    assert r["attrs"]["unit_source"] == "quote" and r["attrs"]["unit_as_written"] == "ft"


def test_unit_away_agreeing_single_unit_is_used_as_written(world: World) -> None:
    r = _one(
        world,
        _hard(world, "perforation.top_md", "3000", "ft", "15/9-F-99 Set 3000 MD ft", 1, 1),
        "a5",
    )
    assert "unit_away_from_value" not in r["reasons"]
    assert r["attrs"]["unit_as_written"] == "ft" and r["attrs"]["unit_source"] == "quote"
    assert r["attrs"]["normalized_number"] == pytest.approx(914.4)


def test_unit_words_ignore_ordinary_words_and_header_units() -> None:
    assert unit_words("Packer set in 3000 ft MD") == ["ft"]  # "in" is a word, not inches
    assert unit_words("Depth (ft) table: top 2000") == []  # header unit is context
    assert unit_words("a c e") == []


def test_page_item_depth_of_another_item_does_not_validate(world: World) -> None:
    # (b) page 2 text: "Production packer 3064.39 ..." and "Liner hanger 3095 ..." are separate
    # lines; the packer must not take the liner hanger's depth
    wrong = page_item(
        world.pdf_doc,
        2,
        depth_text="3095 m MD",
        quote="Production packer 3064.39 m MD Baker",
    )
    right = page_item(world.pdf_doc, 2, depth_text="3064.39 m MD")
    out, _ = run_cands(
        world, [wrong, right], doc=world.pdf_doc, kind="page_read", page=2, line_range=None
    )
    assert out.state == "succeeded"
    bad, good = rows(world)
    bad_attrs, good_attrs = json.loads(bad["attributes"]), json.loads(good["attributes"])
    assert bad["state"] == "flagged" and "field_not_associated" in bad["reasons"]
    assert bad_attrs["depth_text"] is None and "depth_text" in bad_attrs["dropped_fields"]
    assert good_attrs["depth_text"] == "3064.39 m MD" and good_attrs["dropped_fields"] == []


def test_association_scope_is_the_label_lines() -> None:
    text = "Production packer 3064.39 m MD\nLiner hanger 3095 m MD\n"
    assert association_text(text, "Liner hanger") == "Liner hanger 3095 m MD"
    assert association_text(text, "Nipple") == ""  # label on no line: nothing associates
    assert association_text(text, None) == text


def test_page_naming_a_different_well_overrides_the_cover_rule(world: World) -> None:
    # (c) other.pdf page 1 (cover) names F-99, but page 2 explicitly names 15/9-F-98
    item = page_item(world.other_doc, 2, name="Production packer", depth_text="3064.39 m MD")
    out, _ = run_cands(
        world, [item], doc=world.other_doc, kind="page_read", page=2, line_range=None
    )
    assert out.state == "succeeded"
    (r,) = rows(world)
    assert r["wellbore_id"] is None
    assert "subject_page_names_other_well" in r["reasons"] and r["state"] == "flagged"
    # the same claim about the page's own well attaches (cover rule not needed)
    ok = page_item(
        world.other_doc,
        2,
        name="Production packer",
        depth_text="3064.39 m MD",
        subject={"wellbore_label": "15/9-F-98"},
    )
    run_cands(
        world, [ok], doc=world.other_doc, kind="page_read", page=2, line_range=None, question="c2"
    )
    assert rows(world)[-1]["wellbore_id"] is not None


def test_glued_size_fraction_is_ambiguous(world: World) -> None:
    # (d) "95/8" is not 11.875 in
    assert parse_quantity("95/8", allow_fraction=True).value is None
    assert parse_quantity("9 5/8", allow_fraction=True).value == pytest.approx(9.625)
    assert parse_quantity("5/8", allow_fraction=True).value == pytest.approx(0.625)
    r = _one(
        world, _hard(world, "casing.od", "95/8", "in", "Casing OD 95/8 in at shoe", 3, 3), "d1"
    )
    assert r["state"] == "flagged" and "size_ambiguous" in r["reasons"]
    assert r["attrs"]["normalized_number"] is None
    r = _one(
        world, _hard(world, "casing.od", "9 5/8", "in", "Casing OD 9 5/8 in at shoe", 4, 4), "d2"
    )
    assert r["attrs"]["normalized_number"] == pytest.approx(0.244475, abs=1e-6)

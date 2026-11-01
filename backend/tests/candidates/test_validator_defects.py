"""Repair round (QA RETURN on def5083): D1..D8. The validators decide, never the model:
whole-token values, units consistent with the quote, strict number parsing, subjects supported
by the source, verified page-item fields, parsed-set conflicts, no coordinate accept path,
settlement of finished units. Synthetic text only; offline stub provider."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import pytest

from fieldlens.candidates import validators as val
from fieldlens.candidates.harness import UnitRequest
from fieldlens.candidates.reconcile import settle_finished_units
from fieldlens.candidates.textmatch import parse_quantity, supported_in, unit_after
from tests.candidates.conftest import World
from tests.candidates.helpers import loc, meas, page_item, rows, run_cands
from tests.candidates.support import FixtureProvider, json_response

F98 = {"wellbore_label": "15/9-F-98"}


def X(
    w: World,
    key: str,
    value: str,
    unit: str | None,
    quote: str,
    *,
    a: int = 1,
    b: int = 9,
    **over: Any,
) -> dict[str, Any]:
    """Candidate on extra.txt; lines 1-9 by default (line 9 names 15/9-F-98 as the source does)."""
    return meas(
        w,
        attribute_key=key,
        value_text=value,
        unit=unit,
        quote=quote,
        locator=loc(w.extra_doc, a, b),
        subject=over.pop("subject", F98),
        **over,
    )


def one(w: World, cand: dict[str, Any], q: str = "q") -> dict[str, Any]:
    out, _ = run_cands(w, [cand], doc=w.extra_doc, line_range=(1, 9), question=q)
    assert out.state == "succeeded"
    r = rows(w)[-1]
    r["attrs"] = json.loads(r["attributes"])
    return r


# --- D1 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "quote"),
    [
        ("3000", "TD 13000 ft MD reached"),
        ("9.625", "OD 19.625 in"),
        ("2500", "Datum TVDSS −2500 m"),
        ("5/8", "Casing OD 9 5/8 in at shoe"),
        ("9", "Casing OD 9 5/8 in at shoe"),
    ],
)
def test_value_must_be_a_whole_token_of_the_quote(world: World, value: str, quote: str) -> None:
    r = one(world, X(world, "casing.od", value, "in", quote))
    assert r["state"] == "rejected" and "value_not_in_quote" in r["reasons"]


def test_whole_token_matching_unit() -> None:
    assert supported_in("13000", "TD 13000 ft MD reached")
    assert supported_in("4165.00", "4160.00-4165.00 m")  # a range separator is not a sign
    assert supported_in("−2500", "Datum TVDSS -2500 m")
    assert not supported_in("3000", "TD 13000 ft") and not supported_in("3000", "TD 3000.5 ft")
    assert not supported_in("3000", "TD 3000,5 ft") and not supported_in("3000", "1,3000")
    assert supported_in("3000", "TD 3000.") and supported_in("3000", "TD 3000, then")


# --- D2 ------------------------------------------------------------------------------------


def test_unit_must_match_the_quote(world: World) -> None:
    wrong = one(world, X(world, "packer.md", "3000", "m", "Packer set at 3000 ft MD"))
    assert wrong["state"] == "rejected" and "unit_conflicts_with_quote" in wrong["reasons"]
    wrong2 = one(world, X(world, "packer.md", "3000", "ft", "TD 3000 m"), "q2")
    assert "unit_conflicts_with_quote" in wrong2["reasons"] and wrong2["state"] == "rejected"
    # no claimed unit: the quote's unit is used and recorded, the meters default is NOT applied
    used = one(world, X(world, "packer.md", "3000", None, "Packer set at 3000 ft MD"), "q3")
    assert used["state"] == "accepted"
    assert used["attrs"]["unit_as_written"] == "ft" and used["attrs"]["unit_source"] == "quote"
    assert used["attrs"]["unit_defaulted"] is False
    assert used["attrs"]["normalized_number"] == 914.4
    assert "unit_defaulted_meters" not in used["validators"]


def test_meters_default_only_when_context_states_no_unit(world: World) -> None:
    # a claimed non-meter unit that neither the quote nor the context states is flagged
    claimed = one(world, X(world, "packer.md", "4160.00", "ft", "Hugin Fm.  1  1  4160.00"))
    claimed_perf = one(world, meas(world, unit="ft"), "perf")
    assert claimed_perf["state"] == "flagged" and "unit_not_in_source" in claimed_perf["reasons"]
    assert claimed["state"] in ("flagged", "rejected")
    # a header that states (ft) is the unit of an unmarked value; meters is not assumed
    ctx = one(world, X(world, "packer.md", "2000", None, "Depth (ft) table: top 2000"), "ctx")
    assert ctx["state"] == "accepted" and ctx["attrs"]["unit_source"] == "context"
    assert ctx["attrs"]["normalized_number"] == 609.6 and ctx["attrs"]["unit_defaulted"] is False
    # ... and a claimed meter unit against that header is flagged, not defaulted
    clash = one(world, X(world, "packer.md", "2000", "m", "Depth (ft) table: top 2000"), "c2")
    assert clash["state"] == "flagged" and "unit_not_in_source" in clash["reasons"]
    # nothing stated anywhere: meters by default, a warning that never blocks
    none = one(world, meas(world, unit=None), "none")
    assert none["state"] == "accepted" and none["attrs"]["unit_source"] == "default"
    assert none["attrs"]["unit_defaulted"] is True


# --- D3 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text_", "expected"),
    [
        ("9 5/8", 9.625),
        ("9-5/8", 9.625),
        ("13 3/8", 13.375),
        ("5/8", 0.625),
        ("−2500", -2500.0),
        ("–2500", -2500.0),
        ("-2500", -2500.0),
        ("4160,50", 4160.5),
        ("4160,5", 4160.5),
        ("4160.50", 4160.5),
    ],
)
def test_number_parsing(text_: str, expected: float) -> None:
    got = parse_quantity(text_, allow_fraction=True)
    assert got.problem is None and got.value == pytest.approx(expected)


@pytest.mark.parametrize(
    "text_", ["1.234,5", "1,234", "1,234.5", "12,3456", "4160 m", "abc", "1/0"]
)
def test_number_parsing_ambiguous_is_not_guessed(text_: str) -> None:
    got = parse_quantity(text_, allow_fraction=True)
    assert got.value is None and got.problem is not None
    assert parse_quantity("9 5/8", allow_fraction=False).value is None  # fractions only for sizes


def test_unit_after_value() -> None:
    assert unit_after("3000", "Packer set at 3000 ft MD") == "ft"
    assert unit_after("9 5/8", "Casing OD 9 5/8 in at shoe") == "in"
    assert unit_after("4160.00", "4160.00 4165.00") is None


def test_parsed_numbers_in_candidates(world: World) -> None:
    od = one(world, X(world, "casing.od", "9 5/8", "in", "Casing OD 9 5/8 in at shoe"))
    assert od["state"] == "accepted"
    assert od["attrs"]["number"] == 9.625 and od["attrs"]["normalized_number"] == 0.244475
    big = one(world, X(world, "casing.od", "13 3/8", None, "Liner 13 3/8 in; ID 12.347 in"), "b")
    assert big["attrs"]["normalized_number"] == 0.339725 and big["attrs"]["unit_as_written"] == "in"
    # a Unicode minus keeps its sign (here the value is then out of the plausible range)
    neg = one(world, X(world, "datum.tvdss", "−2500", "m", "Datum TVDSS −2500 m"), "n")
    assert neg["attrs"]["normalized_number"] == -2500.0 and "out_of_range" in neg["reasons"]
    comma = one(world, X(world, "packer.md", "4160,50", "m", "Depth 4160,50 m MD"), "c")
    assert comma["state"] == "accepted" and comma["attrs"]["normalized_number"] == 4160.5
    for value, q in (("1.234,5", "a"), ("1,234", "b")):
        amb = one(world, X(world, "packer.md", value, "m", "Value 1.234,5 and 1,234 m"), q)
        assert amb["state"] == "flagged" and "number_unparseable" in amb["reasons"]


# --- D4 ------------------------------------------------------------------------------------


def test_subject_must_be_named_by_the_source(world: World) -> None:
    # extra.txt names F-98 on line 9 only: a claim of F-99 is not supported by the span
    arbitrary = one(
        world,
        X(
            world,
            "perforation.top_md",
            "13000",
            "ft",
            "TD 13000 ft MD reached",
            subject={"wellbore_label": "15/9-F-99"},
        ),
    )
    assert arbitrary["state"] == "flagged" and arbitrary["wellbore_id"] is None
    # the span explicitly names another well (F-98): a stronger finding than "unresolved"
    assert "subject_page_names_other_well" in arbitrary["reasons"]
    # the cited lines do not name the well either (line 2 only): unattached with a finding
    narrow = one(
        world,
        X(world, "packer.md", "13000", "ft", "TD 13000 ft MD reached", a=2, b=2),
        "narrow",
    )
    assert narrow["state"] == "flagged" and narrow["wellbore_id"] is None
    # named by the cited span: attached and accepted
    named = one(world, X(world, "packer.md", "13000", "ft", "TD 13000 ft MD reached"), "ok")
    assert named["state"] == "accepted" and named["wellbore_id"] is not None


def test_subject_supported_by_pdf_cover_page(world: World) -> None:
    out, _ = run_cands(
        world,
        [
            page_item(
                world.pdf_doc,
                3,
                name="Rig crew",
                depth_text=None,
                quote="Rig crew on shift",
                item_type="crew",
            )
        ],
        doc=world.pdf_doc,
        kind="page_read",
        page=3,
        line_range=None,
    )
    assert out.state == "succeeded" and rows(world)[-1]["state"] == "accepted"  # page 1 names F-99


# --- D5 ------------------------------------------------------------------------------------


def test_page_item_fields_are_verified_per_field(world: World) -> None:
    out, _ = run_cands(
        world,
        [
            page_item(
                world.pdf_doc, 1, depth_text="9999 m MD", sizes_text=["99 in"], notes="fabricated"
            ),
            page_item(world.pdf_doc, 1, depth_text="064.39 m MD"),  # inside 3064.39
            page_item(
                world.pdf_doc,
                1,
                name="Tubing hanger Vetco",
                sizes_text=["6-3/8 in"],
                depth_text=None,
                quote="Tubing hanger Vetco 6-3/8 in XMT",
            ),
        ],
        doc=world.pdf_doc,
        kind="page_read",
        page=1,
        line_range=None,
    )
    assert out.state == "succeeded"
    bad, partial, good = rows(world)[-3:]
    for r in (bad, partial):
        assert r["state"] == "flagged" and "field_unverified" in r["reasons"]
    a = json.loads(bad["attributes"])
    assert a["depth_text"] is None and a["sizes_text"] == [] and a["notes"] is None
    assert sorted(a["dropped_fields"]) == ["depth_text", "notes", "sizes_text"]
    assert json.loads(partial["attributes"])["dropped_fields"] == ["depth_text"]
    g = json.loads(good["attributes"])
    assert (
        good["state"] == "accepted"
        and g["sizes_text"] == ["6-3/8 in"]
        and g["dropped_fields"] == []
    )


# --- D6 ------------------------------------------------------------------------------------


def test_conflict_against_the_whole_parsed_set(world: World) -> None:
    # no parsed record at the cited (PDF) location: compare with ALL parsed top_md values
    page = lambda value, quote: meas(  # noqa: E731
        world, value_text=value, unit="m", quote=quote, locator=loc(world.pdf_doc, page=2)
    )
    out, _ = run_cands(
        world,
        [page("3605", "Perforation top 3605 m"), page("4157", "Reperforation top 4157 m")],
        doc=world.pdf_doc,
        page=2,
        line_range=None,
    )
    assert out.state == "succeeded"
    off, agrees = rows(world)[-2:]
    assert off["state"] == "flagged" and "parsed_conflict" in off["reasons"]
    detail = next(v for v in json.loads(off["validators"]) if v["validator"] == "parsed_conflict")
    assert (
        "nearest" in detail["detail"] and "4157" in detail["detail"] and "4160" in detail["detail"]
    )
    assert off["conflict"] is not None
    assert agrees["state"] == "accepted"  # within tolerance of one of the parsed values
    assert not any(
        v["outcome"] == "skipped"
        for v in json.loads(off["validators"])
        if v["validator"] == "parsed_conflict"
    )


def test_conflict_respects_effective_time(world: World) -> None:
    f98 = world.scalar("select wellbore_id from wellbore where wellbore_key='15/9-F-98'")
    doc = world.reader.require(world.project_id, world.revision_id, world.perf98_doc)
    span = val._Span(doc, "", True, {"kind": "pdf", "page": 1})
    with world.factory() as s:
        key = "perforation.top_md"
        other, _ = val._parsed_conflict(s, world.project_id, f98, key, 3950.0, span, "2013-01-01")
        same, rec = val._parsed_conflict(s, world.project_id, f98, key, 3950.0, span, "2011-01-02")
        agree, _ = val._parsed_conflict(s, world.project_id, f98, key, 3900.0, span, "2011-01-02")
    assert other.outcome.value == "skipped" and "effective time" in (other.detail or "")
    assert same.outcome.value == "flagged" and rec is not None
    assert agree.outcome.value == "passed"


# --- D7 ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", ["trajectory_station.md", "survey.md", "wellhead.northing", "coordinate.x"]
)
def test_trajectory_type_candidates_have_no_accept_path(world: World, key: str) -> None:
    r = one(world, X(world, key, "13000", "ft", "TD 13000 ft MD reached"))
    assert r["state"] == "flagged" and "coordinate_fallback_unsupported" in r["reasons"]
    assert "attribute_unknown" not in r["reasons"]


# --- D8 ------------------------------------------------------------------------------------


def test_settle_failure_leaves_the_unit_recoverable(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = FixtureProvider(lambda r, n: json_response([meas(world)]))
    h = world.harness(provider)

    def boom(rid: UUID) -> Any:
        raise RuntimeError("database hiccup")

    real = h._ledger.settle
    monkeypatch.setattr(h._ledger, "settle", boom)
    req = UnitRequest(
        world.project_id, world.revision_id, world.perf_doc, "q", "measurement", line_range=(1, 3)
    )
    out = h.run_unit(req)
    assert out.state == "succeeded"  # the unit result stands
    assert world.scalar("select state from spend_reservation") == "reserved"  # liability stays open
    monkeypatch.setattr(h._ledger, "settle", real)
    h.recover_interrupted()  # startup/recovery sweep settles it
    assert world.scalar("select state from spend_reservation") == "settled"
    assert world.scalar("select committed_usd from spend_reservation") > 0
    assert settle_finished_units(world.factory, h._ledger) == []  # idempotent


def test_startup_reconciles_unsettled_reservations(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi.testclient import TestClient

    from tests.upload_support import BASE

    provider = FixtureProvider(lambda r, n: json_response([meas(world)]))
    h = world.harness(provider)
    monkeypatch.setattr(h._ledger, "settle", lambda rid: (_ for _ in ()).throw(RuntimeError("x")))
    run_cands(world, [], harness=h)
    monkeypatch.undo()
    assert world.scalar("select state from spend_reservation") == "reserved"
    with TestClient(world.api.client.app, base_url=BASE):  # lifespan = process start
        pass
    assert world.scalar("select state from spend_reservation") == "settled"
    # a running unit's reservation is never touched by the sweep
    handle = world.log.start_unit(world.project_id, world.revision_id, "run-1", "q")
    assert handle.unit_id and settle_finished_units(world.factory, h._ledger) == []

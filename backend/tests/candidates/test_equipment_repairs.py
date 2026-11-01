"""TASK-041 repairs after the first live run (stub provider only, real-rate arithmetic):
one turn and no tools for prefetched equipment pages, an honest reservation, an output cap that
fits a 25-item page, truncation never partial, tolerant but unguessing printed quantities."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

import pytest

from fieldlens.assistant.messages import ImagePart, ProviderResponse, TextPart
from fieldlens.assistant.provider import Pricing, attempt_upper_bound_usd
from fieldlens.assistant.runner import RequestLimits
from fieldlens.candidates.equipment_prompt import (
    EQUIPMENT_CATEGORIES,
    EQUIPMENT_PROMPT_VERSION,
    EQUIPMENT_SYSTEM_PROMPT,
    EQUIPMENT_SYSTEM_PROMPT_TWO_PASS,
)
from fieldlens.candidates.harness import (
    EQUIPMENT_TWO_PASS_RESERVE_USD,
    EQUIPMENT_UNIT_RESERVE_USD,
    ExtractionHarness,
    HarnessConfig,
    UnitRequest,
)
from fieldlens.candidates.schema import MAX_OUTPUT_BYTES, parse_equipment_output
from fieldlens.candidates.textmatch import parse_printed_quantity
from tests.assistant_support import MODEL
from tests.candidates.conftest import World
from tests.candidates.eq_helpers import eq_rows, equip
from tests.candidates.support import FixtureProvider, call_response, json_response, usage

REAL = Pricing("placeholder-5-25", MODEL, Decimal("5.00"), Decimal("25.00"))


def real_rate_harness(world: World, provider: FixtureProvider, **cfg: Any) -> ExtractionHarness:
    pricing_id = world.ledger.register_pricing(REAL, "test placeholder rates")
    return ExtractionHarness(
        factory=world.factory,
        reader=world.reader,
        ledger=world.ledger,
        provider=provider,
        config=HarnessConfig(
            model=MODEL,
            pricing=REAL,
            pricing_id=pricing_id,
            period_id=world.period,
            limits=RequestLimits(retry_backoff_s=0.0),
            **cfg,
        ),
        retrieval=world.api.client.app.state.retrieval,
        log=world.log,
    )


def unit(world: World, page: int = 1, rotation: int | None = None) -> UnitRequest:
    return UnitRequest(
        world.project_id,
        world.revision_id,
        world.scan_doc,
        "q",
        "equipment",
        page=page,
        rotation=rotation,
    )


def twenty_five(world: World) -> list[dict[str, Any]]:
    cats = ["casing", "tubing", "packer", "liner", "completion_accessory", "isolation"]
    return [
        equip(
            world.scan_doc,
            1,
            category=cats[i % 6],
            label_text=f"Item {i}",
            od={"value_text": "9 5/8", "unit": "in"},
            top_depth={"value_text": f"{3000 + i}.5", "unit": "m", "reference_text": "MD"},
        )
        for i in range(25)
    ]


def test_one_turn_no_tools_and_an_honest_reservation(world: World) -> None:
    """Live shape of p29/p35: one image-bearing turn, 25 items, ~2.7k output tokens. The unit
    makes ONE provider call with no tools, within a USD 0.25 reservation at the placeholder rates."""
    provider = FixtureProvider(lambda r, n: json_response(twenty_five(world), usage(3916, 2682)))
    h = real_rate_harness(world, provider)
    out = h.run_unit(unit(world))
    assert out.state == "succeeded" and out.provider_calls == 1 and len(provider.calls) == 1
    req = provider.calls[0]
    assert req.tools == () and req.max_output_tokens == 8192 and req.effort == "low"
    assert any(isinstance(p, ImagePart) for m in req.messages for p in m.parts)
    # the worst-case bound of this exact request fits the unit's reservation
    bound = attempt_upper_bound_usd(req, REAL, h.config.equipment_image_token_bound)
    assert bound <= EQUIPMENT_UNIT_RESERVE_USD == Decimal("0.25")
    reserved = world.scalar("select max(reserved_usd) from spend_reservation")
    assert Decimal(reserved) == EQUIPMENT_UNIT_RESERVE_USD
    assert len(eq_rows(world)) == 25
    assert out.cost_usd < EQUIPMENT_UNIT_RESERVE_USD


def test_a_tool_call_on_a_prefetched_page_is_refused_not_a_budget_failure(world: World) -> None:
    """The p30/p36 shape: the model answered turn 1 with a tool call. Now no tool is offered; a
    call is a refused, failed unit (`tool_not_allowed`), never `budget_exhausted`."""
    provider = FixtureProvider(
        lambda r, n: call_response(
            "get_page_image", {"document_id": "x", "page": 1, "rotation": 90}
        )
    )
    out = real_rate_harness(world, provider).run_unit(unit(world, rotation=90))
    assert out.state == "failed" and out.stop_reason == "tool_not_allowed"
    assert len(provider.calls) == 1
    refused = world.rows(
        "select outcome from agent_step where tool_name='get_page_image' and outcome='refused'"
    )
    assert refused
    assert world.scalar("select count(*) from spend_reservation where state='open'") == 0


def test_default_prompt_has_no_rotation_invitation_and_lists_the_enum() -> None:
    p = EQUIPMENT_SYSTEM_PROMPT
    assert "get_page_image" not in p and "no tools are available" in p
    for cat in EQUIPMENT_CATEGORIES:
        assert cat in p
    assert "category MUST be exactly one of" in p and 'when unsure use "other"' in p
    assert "description" not in p and "region" not in p  # shrunk wire output
    assert "the number only" in p and "no prose" in p
    assert "get_page_image" in EQUIPMENT_SYSTEM_PROMPT_TWO_PASS
    assert EQUIPMENT_PROMPT_VERSION == "eq-prompt-2"


def test_two_pass_mode_is_opt_in_and_only_for_unknown_orientation(world: World) -> None:
    def tools_of(provider: FixtureProvider) -> list[str]:
        return [t.name for t in provider.calls[0].tools]

    p0 = FixtureProvider(lambda r, n: json_response([]))
    real_rate_harness(world, p0).run_unit(unit(world))  # default: off
    assert tools_of(p0) == []
    # on, orientation configured: still no tools
    p1 = FixtureProvider(lambda r, n: json_response([]))
    real_rate_harness(world, p1, allow_rotation_requests=True).run_unit(unit(world, rotation=90))
    assert tools_of(p1) == []

    # on, orientation unknown: one tool, two attempts reserved, prompt invites the request
    def two_pass(request: Any, n: int) -> ProviderResponse:
        if n == 1:
            return call_response(
                "get_page_image", {"document_id": str(world.scan_doc), "page": 1, "rotation": 90}
            )
        return json_response([equip(world.scan_doc, 1)], usage(6600, 900))

    p2 = FixtureProvider(two_pass)
    out = real_rate_harness(world, p2, allow_rotation_requests=True).run_unit(unit(world))
    assert out.state == "succeeded" and len(p2.calls) == 2
    assert tools_of(p2) == ["get_page_image"]
    system = [m for m in p2.calls[0].messages if m.role == "system"][0].parts[0]
    assert isinstance(system, TextPart) and "rotation of 90" in system.text
    assert Decimal(world.scalar("select max(reserved_usd) from spend_reservation")) == (
        EQUIPMENT_TWO_PASS_RESERVE_USD
    )
    # the second request (two images) still fits the reservation: the run did not stop on budget
    assert out.stop_reason == "completed"


def test_truncated_output_fails_and_is_never_partial(world: World) -> None:
    partial = json.dumps({"candidates": twenty_five(world)})[:900]  # cut mid-item

    def truncated(request: Any, n: int) -> ProviderResponse:
        return ProviderResponse(
            status="truncated", parts=(TextPart(text=partial),), usage=usage(3916, 8192)
        )

    out = real_rate_harness(world, FixtureProvider(truncated)).run_unit(unit(world))
    assert out.state == "failed" and out.stop_reason == "output_truncated"
    assert world.scalar("select count(*) from extraction_candidate") == 0


def test_a_25_and_a_40_item_page_fit_the_wire_and_the_cap() -> None:
    doc = "00000000-0000-0000-0000-000000000001"

    def item(i: int) -> dict[str, Any]:
        return {
            "kind": "equipment",
            "category": "completion_accessory",
            "material": "13Cr S110",
            "label_text": f"Printed label number {i} with some words",
            "od": {"value_text": "9 5/8", "unit": "in"},
            "id": {"value_text": "8.681", "unit": "in"},
            "length": {"value_text": "12.5", "unit": "m"},
            "top_depth": {"value_text": f"{3000 + i}.5", "unit": "m", "reference_text": "MD"},
            "bottom_depth": {"value_text": f"{3010 + i}.5", "unit": "m", "reference_text": "MD"},
            "locator": {"document_id": doc, "page": 49},
        }

    for n in (25, 40):
        text = json.dumps({"candidates": [item(i) for i in range(n)]})
        assert len(text.encode()) < MAX_OUTPUT_BYTES
        parsed = parse_equipment_output(text)
        assert len(parsed) == n and all(type(p).__name__ == "WireEquipment" for p in parsed)
        # ~4 characters per token is a safe bound; even 40 full items stay well below 8,192 tokens
        assert len(text) / 3 < 8192


@pytest.mark.parametrize(
    ("text", "size", "number", "unit", "ref", "problem"),
    [
        ('7"', True, 7.0, '"', None, None),
        ("7 in", True, 7.0, "in", None, None),
        ('13 3/8"', True, 13.375, '"', None, None),
        ("9-5/8", True, 9.625, None, None, None),
        ("9 5/8 in", True, 9.625, "in", None, None),
        ("2615,4 m MD", False, 2615.4, "m", "MD", None),
        ("2615,4", False, 2615.4, None, None, None),
        ("1,234 m", False, 1234.0, "m", None, None),
        ("1,234.5 m MD RKB", False, 1234.5, "m", "MD RKB", None),
        ("5000ft", False, 5000.0, "ft", None, None),
        ("3 000 m", False, None, None, None, "other text after the number"),
        ("9 5/8 x 7", True, None, None, None, "several sizes in one field"),
        ("1,234", True, None, None, None, "ambiguous separator"),
        ("3605-3608", False, None, None, None, "a range in one field; kept as printed"),
        ("3605 - 3608 m", False, None, None, None, "a range in one field; kept as printed"),
        ("3605 to 3608 m", False, None, None, None, "other text after the number"),
        ("95/8", True, None, None, None, "ambiguous size fraction"),
        ("about 3000 m", False, None, None, None, "not a plain number"),
        ("3000 m approx", False, None, None, None, "other text after the number"),
        ("1.234,5 m", False, None, None, None, "ambiguous separator"),
        ("0,125 m", False, 0.125, "m", None, None),
        ("0,125", False, 0.125, None, None, None),
        ('0,125"', True, 0.125, '"', None, None),
        ("-0,5 m", False, -0.5, "m", None, None),
        ("-2500 m", False, -2500.0, "m", None, None),
        ("−2500 m", False, -2500.0, "m", None, None),
    ],
)
def test_printed_quantities_parse_without_guessing(
    text: str,
    size: bool,
    number: float | None,
    unit: str | None,
    ref: str | None,
    problem: str | None,
) -> None:
    got = parse_printed_quantity(text, size=size)
    assert got.number == number and got.unit_word == unit and got.reference_text == ref
    assert got.problem == problem


def test_the_live_strings_now_validate(world: World) -> None:
    """The three strings the first live run flagged `number_unparseable`."""
    items = [
        equip(world.scan_doc, 1, category="casing", od={"value_text": '7"', "unit": '"'}),
        equip(world.scan_doc, 1, category="casing", od={"value_text": '7"', "unit": None}),
        equip(
            world.scan_doc,
            1,
            top_depth={"value_text": "2615,4 m MD", "unit": "m", "reference_text": "MD"},
        ),
        # the value contradicts the claimed unit: flagged, never converted
        equip(world.scan_doc, 1, top_depth={"value_text": "3000 ft", "unit": "m"}),
    ]
    provider = FixtureProvider(lambda r, n: json_response(items))
    out = real_rate_harness(world, provider).run_unit(unit(world))
    assert out.state == "succeeded"
    a, b, c, d = eq_rows(world)
    assert a["attrs"]["od"]["number"] == 7 and a["attrs"]["od"]["issue"] is None
    assert b["attrs"]["od"]["number"] == 7 and b["attrs"]["od"]["unit_as_written"] == '"'
    assert b["attrs"]["od"]["normalized_number"] == pytest.approx(0.1778)
    assert c["attrs"]["top_depth"]["number"] == pytest.approx(2615.4)
    assert c["attrs"]["top_depth"]["depth_reference"] == "MD"
    for r in (a, b, c):
        assert "number_unparseable" not in r["reasons"]
    assert "unit_conflicts_with_quote" in d["reasons"] and d["state"] == "flagged"


def _flags(world: World, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    provider = FixtureProvider(lambda r, n: json_response(items))
    out = real_rate_harness(world, provider).run_unit(unit(world))
    assert out.state == "succeeded"
    return eq_rows(world)


def test_printed_depth_reference_never_silently_replaces_the_claimed_one(world: World) -> None:
    def d(value: str, ref: str | None) -> dict[str, Any]:
        return equip(
            world.scan_doc, 1, top_depth={"value_text": value, "unit": "m", "reference_text": ref}
        )

    rows = _flags(
        world,
        [
            d("3000 m TVD", "MD"),  # contradiction, flagged
            d("3000 m MD", "TVD"),  # contradiction, flagged
            d("3000 m TVD", None),  # nothing claimed: the printed reference is used
            d("3000 m MD", "MD RKB"),  # consistent
        ],
    )
    a, b, c, e = rows
    for r in (a, b):
        assert r["state"] == "flagged" and "md_tvd_confusion" in r["reasons"]
        assert "not resolved" in r["attrs"]["top_depth"]["issue"]
    assert a["attrs"]["top_depth"]["depth_reference"] == "MD"  # MD is never recorded as TVD
    assert b["attrs"]["top_depth"]["depth_reference"] == "TVD"
    assert (
        "md_tvd_confusion" not in c["reasons"]
        and c["attrs"]["top_depth"]["depth_reference"] == "TVD"
    )
    assert (
        "md_tvd_confusion" not in e["reasons"]
        and e["attrs"]["top_depth"]["depth_reference"] == "MD"
    )


def test_depth_and_length_in_inches_are_flagged_not_converted(world: World) -> None:
    rows = _flags(
        world,
        [
            equip(world.scan_doc, 1, top_depth={"value_text": '3000"', "unit": None}),
            equip(world.scan_doc, 1, top_depth={"value_text": "3000", "unit": "in"}),
            equip(
                world.scan_doc, 1, category="tubing", length={"value_text": "12 in", "unit": None}
            ),
            equip(world.scan_doc, 1, category="casing", od={"value_text": '7"', "unit": None}),
        ],
    )
    for r in rows[:3]:
        assert r["state"] == "flagged" and "unit_dimension_mismatch" in r["reasons"]
    assert rows[0]["attrs"]["top_depth"]["normalized_number"] is None
    assert "inches" in rows[0]["attrs"]["top_depth"]["issue"]
    assert "unit_dimension_mismatch" not in rows[3]["reasons"]  # an OD in inches is normal


def test_leading_zero_comma_is_decimal_and_thousands_stay_thousands(world: World) -> None:
    rows = _flags(
        world,
        [
            equip(world.scan_doc, 1, length={"value_text": "0,125 m", "unit": "m"}),
            equip(
                world.scan_doc,
                1,
                top_depth={"value_text": "0,125", "unit": "m", "reference_text": "MD"},
            ),
            equip(
                world.scan_doc,
                1,
                top_depth={"value_text": "1,234 m", "unit": "m", "reference_text": "MD"},
            ),
            equip(world.scan_doc, 1, category="casing", od={"value_text": "1,234", "unit": "in"}),
        ],
    )
    assert rows[0]["attrs"]["length"]["normalized_number"] == pytest.approx(0.125)
    assert rows[1]["attrs"]["top_depth"]["number"] == pytest.approx(0.125)
    assert rows[2]["attrs"]["top_depth"]["number"] == 1234
    assert "number_unparseable" in rows[3]["reasons"]  # a thousands separator in a size is flagged

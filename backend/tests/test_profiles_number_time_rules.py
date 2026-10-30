"""QA D6/D7/D9: ambiguous commas, stated-unit validation and timezone preservation."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldlens.profiles.common import event_time, parse_number, quantity_attr
from fieldlens.profiles.production import ProductionWorkbookProfile
from tests.profile_support import CTX, write, xlsx_bytes
from tests.test_profiles_sources import DAILY_HEAD, MONTHLY_HEAD, MONTHLY_UNITS, _day


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1,234.5", 1234.5), ("1,234,567", 1234567.0), ("12.5", 12.5), ("-1,000", -1000.0)],
)
def test_unambiguous_thousands_commas_are_accepted(text: str, expected: float) -> None:
    assert parse_number(text) == expected


@pytest.mark.parametrize("text", ["1,5", "12,34", "1,23", "1,2345", ",5", "1,,234", "1.234,5"])
def test_ambiguous_commas_are_unknown_never_fifteen(text: str) -> None:
    assert parse_number(text) is None


def test_ambiguous_comma_attribute_states_why() -> None:
    attr = quantity_attr("x", {"kind": "text", "line_start": 1}, "1,5", "m")
    assert attr.number is None and attr.original_text == "1,5"
    assert attr.unknown_reason and "comma" in attr.unknown_reason


def test_timezone_is_kept_for_z_and_offsets_and_naive_is_flagged() -> None:
    z = event_time("2007-11-11T15:51:12.000Z")
    off = event_time("2007-11-11T15:51:12+02:00")
    naive = event_time("2007-11-11T15:51:12")
    day = event_time("2007-11-11")
    assert z and z.timezone == "UTC" and z.timezone_known
    assert off and off.timezone == "UTC+02:00" and off.timezone_known
    assert naive and naive.timezone is None and not naive.timezone_known
    assert day and day.precision == "day" and not day.timezone_known


def test_stated_choke_unit_is_evidence_and_validation_follows_other_stated_units(
    tmp_path: Path,
) -> None:
    head = [*DAILY_HEAD, "AVG_CHOKE_SIZE_P", "AVG_CHOKE_UOM"]
    row = [*_day(40000, "15/9-F-99", 1, 10.5), 55.0, "%"]
    book = xlsx_bytes(
        {
            "Daily Production Data": [head, row],
            "Monthly Production Data": [MONTHLY_HEAD, MONTHLY_UNITS],
        }
    )
    out = ProductionWorkbookProfile().parse(write(tmp_path, "p.xlsx", book), CTX)
    day = next(r for r in out.records if r.kind == "production_day")
    choke = day.attr("production_day.avg_choke_size_p")
    assert choke is not None and (choke.number, choke.unit, choke.unit_status) == (
        55.0,
        "%",
        "stated",
    )
    assert choke.validation_state == "unreviewed"

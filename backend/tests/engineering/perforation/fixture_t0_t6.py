"""Synthetic FieldLens perforation fixture t0..t6 (PERFORATION_HISTORY.md; not Volve data)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

WELLBORE = "wb-synthetic-1"
DATUM = "KB"
TOL = 1e-6


def t(day: int) -> datetime:
    """t0 = 2000-01-01T00:00:00Z ... t6 = 2000-01-07T00:00:00Z."""
    return datetime(2000, 1, 1 + day, tzinfo=UTC)


def depth(lo: Any, hi: Any, unit: str = "m", **extra: Any) -> dict[str, Any]:
    return {"from": lo, "to": hi, "unit": unit, "reference": "MD", "datum": DATUM, **extra}


def ev(
    event_id: str,
    kind: str,
    when: datetime | str,
    *,
    lo: Any = None,
    hi: Any = None,
    unit: str = "m",
    revision: int = 1,
    **extra: Any,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "event_id": event_id,
        "wellbore_id": WELLBORE,
        "kind": kind,
        "effective_time": when,
        "precision": "instant",
        "dataset_revision": revision,
    }
    if lo is not None:
        rec["depth"] = depth(lo, hi, unit)
    rec.update(extra)
    return rec


def day_ev(event_id: str, kind: str, day: str, tz: str = "UTC", **kwargs: Any) -> dict[str, Any]:
    rec = ev(event_id, kind, day, **kwargs)
    rec["precision"] = "day"
    rec["timezone"] = tz
    return rec


def fixture_records() -> list[dict[str, Any]]:
    return [
        ev("e0-base", "baseline", t(0), status="shut_in", baseline_intervals=[]),
        ev("e1-perf-a", "perforate", t(1), lo=1000, hi=1010),
        ev("e1-perf-b", "perforate", t(1), lo=1020, hi=1030),
        ev("e1-open-a", "open", t(1), lo=1000, hi=1010),
        ev("e1-open-b", "open", t(1), lo=1020, hi=1030),
        ev("e1-producing", "wellbore_status", t(1), status="producing"),
        ev("e2-isolate", "isolate", t(2), lo=1005, hi=1010),
        ev("e3-shut-in", "wellbore_status", t(3), status="shut_in"),
        ev("e4-reperf", "reperforate", t(4), lo=1008, hi=1025),
        ev("e4-reopen", "reopen", t(4), lo=1005, hi=1010),
        ev("e4-open-new", "open", t(4), lo=1010, hi=1020),
        ev("e5-injecting", "wellbore_status", t(5), status="injecting"),
        ev("e6-reperf-again", "reperforate", t(6), lo=1000, hi=1030),
    ]


# instant -> (total m, open m, wellbore status)
EXPECTED = {
    0: (0.0, 0.0, "shut_in"),
    1: (20.0, 20.0, "producing"),
    2: (20.0, 15.0, "producing"),
    3: (20.0, 15.0, "shut_in"),
    4: (30.0, 30.0, "shut_in"),
    5: (30.0, 30.0, "injecting"),
    6: (30.0, 30.0, "injecting"),
}

# the instant just before each event group returns the previous state
JUST_BEFORE = timedelta(microseconds=1)

"""Pure-unit tests (no database): perforation-history series via the engineering engine."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

from fieldlens.charts import perforation
from fieldlens.charts.perforation import PerfRow

WB = uuid4()


def _row(
    n: int,
    top: float | None,
    base: float | None,
    literal: str | None,
    precision: str | None = "day",
    unit: str | None = "m",
) -> PerfRow:
    return PerfRow(
        record_id=UUID(int=n),
        ordinal=n,
        top=top,
        base=base,
        unit=unit,
        unit_defaulted=False,
        literal=literal,
        precision=precision,
        timezone_known=False,
    )


def test_union_of_overlapping_intervals_steps_over_dates() -> None:
    res = perforation.build(
        WB,
        [
            _row(1, 100.0, 110.0, "2020-01-01"),
            _row(2, 105.0, 120.0, "2020-02-01"),
            _row(3, 200.0, 210.0, "2020-03-01"),
        ],
        None,
    )
    totals = [(s.x, s.total) for s in res.steps]
    assert totals == [("2020-01-01", 10.0), ("2020-02-01", 20.0), ("2020-03-01", 30.0)]
    assert res.dated_events == 3 and res.undated_events == 0


def test_same_day_events_form_one_step_without_invented_order() -> None:
    res = perforation.build(
        WB, [_row(1, 100.0, 110.0, "2020-01-01"), _row(2, 120.0, 130.0, "2020-01-01")], None
    )
    assert len(res.steps) == 1
    assert res.steps[0].total == 20.0 and len(res.steps[0].event_ids) == 2


def test_unknown_history_before_first_event_is_not_zero() -> None:
    res = perforation.build(WB, [_row(1, 100.0, 110.0, "2020-06-01")], date(2019, 1, 1))
    assert all(s.total != 0.0 for s in res.steps)
    assert res.steps == []  # nothing is shown before the first dated event


def test_as_of_excludes_later_events() -> None:
    res = perforation.build(
        WB,
        [_row(1, 100.0, 110.0, "2020-01-01"), _row(2, 200.0, 210.0, "2020-06-01")],
        date(2020, 3, 1),
    )
    assert [s.x for s in res.steps] == ["2020-01-01"]


def test_undated_record_is_listed_with_reason_and_not_stepped() -> None:
    res = perforation.build(
        WB, [_row(1, 100.0, 110.0, None, precision="unknown"), _row(2, 1.0, 2.0, "2020-01-01")], None
    )
    assert res.undated_events == 1 and res.dated_events == 1
    assert any(e.effective_time_unknown_reason for e in res.history.events)
    assert [s.x for s in res.steps] == ["2020-01-01"]


def test_no_rows_gives_no_steps() -> None:
    res = perforation.build(WB, [], None)
    assert res.steps == [] and res.history.events == []


def test_deterministic() -> None:
    rows = [_row(2, 5.0, 9.0, "2020-02-01"), _row(1, 1.0, 4.0, "2020-01-01")]
    a = perforation.build(WB, rows, None)
    b = perforation.build(WB, list(reversed(rows)), None)
    assert [(s.x, s.total) for s in a.steps] == [(s.x, s.total) for s in b.steps]

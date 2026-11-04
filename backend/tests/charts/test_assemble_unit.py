"""Pure-unit tests (no database): chart assembly, unit axes, empty states, cache keys."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import numpy as np
import pytest

from fieldlens.charts.assemble import Line, axis_group, build_chart
from fieldlens.contracts.charts import (
    AxisKind,
    ChartEmptyReason,
    ChartKey,
    ChartKind,
    ChartScope,
    ChartSeriesScope,
    ChartSpec,
    SeriesUnitStatus,
)

_SCOPE = ChartSeriesScope(
    scope=ChartScope.WELLBORE, scope_label="wellbore W-1", wellbore_id=uuid4(), wellbore_label="W-1"
)


def _line(key: str, unit: str | None, y: list[float], measure: str = "m") -> Line:
    status = SeriesUnitStatus.STATED if unit else SeriesUnitStatus.MISSING
    return Line(
        series_key=key,
        name=key,
        axis_label=key,
        unit=unit,
        unit_status=status,
        axis_group=axis_group(measure, unit, status, "doc"),
        scope=_SCOPE,
        x=np.arange(len(y), dtype=np.float64) + 20000.0,
        y=np.array(y, dtype=np.float64),
    )


def _chart(lines: list[Line], as_of: date | None = None, seed: str = "s"):  # type: ignore[no-untyped-def]
    return build_chart(
        ChartKey.DOWNHOLE_PRESSURE_TEMPERATURE,
        "c",
        "Title",
        ChartKind.LINE,
        _SCOPE,
        lines,
        window=None,
        as_of=as_of,
        seed=seed,
    )


def test_units_never_share_an_axis() -> None:
    chart = _chart([_line("p", "bar", [1.0, 2.0]), _line("t", "degC", [3.0, 4.0], "t")])
    value_axes = [a for a in chart.axes if a.axis_id != "x"]
    assert len(value_axes) == 2
    assert {a.unit for a in value_axes} == {"bar", "degC"}
    by_axis = {s.axis_id: s.unit for s in chart.series}
    for axis in value_axes:
        assert by_axis[axis.axis_id] == axis.unit


def test_same_unit_shares_one_axis() -> None:
    chart = _chart([_line("a", "bar", [1.0]), _line("b", "bar", [2.0])])
    assert len([a for a in chart.axes if a.axis_id != "x"]) == 1


def test_unstated_units_of_different_measures_do_not_share_an_axis() -> None:
    chart = _chart([_line("a", None, [1.0], "oil"), _line("b", None, [2.0], "gas")])
    assert len([a for a in chart.axes if a.axis_id != "x"]) == 2
    assert all(s.unit is None for s in chart.series)


def test_empty_chart_states_reason() -> None:
    chart = _chart([])
    assert chart.series == [] and chart.empty is not None
    assert chart.empty.reason is ChartEmptyReason.NO_RECORDS and chart.empty.message


def test_all_null_series_is_excluded_not_drawn() -> None:
    chart = _chart([_line("good", "bar", [1.0]), _line("none", "bar", [float("nan")])])
    assert [s.name for s in chart.series] == ["good"]
    assert [e.name for e in chart.excluded_series] == ["none"]


def test_series_counts_are_consistent() -> None:
    chart = _chart([_line("a", "bar", [1.0, float("nan"), 3.0])])
    s = chart.series[0]
    assert s.aggregates.count == s.aggregates.valid_count + s.aggregates.null_count
    assert s.downsample.returned_points == len(s.points) == 3
    assert s.gap_count == sum(1 for p in s.points if p.y is None) == 1
    assert s.aggregates.minimum <= s.aggregates.maximum


def test_cache_key_is_deterministic_and_includes_as_of() -> None:
    lines = [_line("a", "bar", [1.0, 2.0])]
    a = _chart(lines, as_of=date(2020, 1, 1))
    b = _chart(lines, as_of=date(2020, 1, 1))
    c = _chart(lines, as_of=date(2021, 1, 1))
    assert a.cache_key == b.cache_key
    assert a.cache_key != c.cache_key
    assert a.as_of == date(2020, 1, 1)


def test_time_series_x_are_iso_dates_on_a_time_axis() -> None:
    chart = _chart([_line("a", "bar", [1.0, float("nan"), 3.0])])
    x_axis = next(a for a in chart.axes if a.axis_id == "x")
    assert x_axis.kind is AxisKind.TIME
    s = chart.series[0]
    assert [p.x for p in s.points] == ["2024-10-04", "2024-10-05", "2024-10-06"]
    assert s.aggregates.first_valid_x == "2024-10-04"
    assert s.aggregates.last_valid_x == "2024-10-06"
    # round trip through the validators (ISO date strings are accepted)
    assert ChartSpec.model_validate(chart.model_dump(mode="json")) == chart


def test_depth_series_keep_numeric_x_on_a_value_axis() -> None:
    line = _line("gr", "gAPI", [1.0, 2.0])
    line.x = np.array([1500.5, 1501.0])
    line.time_axis = False
    chart = build_chart(
        ChartKey.DOWNHOLE_PRESSURE_TEMPERATURE,
        "c",
        "Title",
        ChartKind.LOG_TRACK,
        _SCOPE,
        [line],
        window=None,
        as_of=None,
        seed="s",
        x_name="MD",
        x_kind=AxisKind.VALUE,
        x_unit="m",
    )
    s = chart.series[0]
    assert [p.x for p in s.points] == [1500.5, 1501.0]
    assert s.aggregates.first_valid_x == 1500.5


def test_time_and_value_lines_cannot_share_one_x_axis() -> None:
    value_line = _line("gr", "gAPI", [1.0])
    value_line.time_axis = False
    with pytest.raises(ValueError, match="x axis"):
        _chart([_line("a", "bar", [1.0]), value_line])

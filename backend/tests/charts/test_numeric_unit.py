"""Pure-unit tests (no database): exact aggregates, display decimation, derived series."""

from __future__ import annotations

import math

import numpy as np

from fieldlens.charts import numeric
from fieldlens.contracts.charts import MAX_DISPLAY_POINTS


def _days(n: int, start: float = 20000.0) -> np.ndarray:
    return start + np.arange(n, dtype=np.float64)


def test_aggregates_are_exact_over_full_resolution() -> None:
    n = 20_000
    x = _days(n)
    y = np.arange(n, dtype=np.float64)
    y[[5, 6, 7]] = np.nan
    agg = numeric.aggregates(x, y, unit=None, summable=True)
    assert agg.count == n and agg.valid_count == n - 3 and agg.null_count == 3
    assert agg.count == agg.valid_count + agg.null_count
    assert agg.minimum == 0.0 and agg.maximum == float(n - 1)
    assert agg.total == math.fsum(float(v) for v in y if v == v)
    assert agg.last_value == float(n - 1)
    assert agg.first_valid_x == numeric.iso_day(x[0])
    assert agg.last_valid_x == numeric.iso_day(x[-1])
    assert agg.minimum <= agg.maximum


def test_aggregates_not_summable_have_no_total_and_all_null_has_no_extrema() -> None:
    x = _days(3)
    assert (
        numeric.aggregates(x, np.array([1.0, 2.0, 3.0]), unit="bar", summable=False).total is None
    )
    empty = numeric.aggregates(x, np.full(3, np.nan), unit=None, summable=True)
    assert empty.valid_count == 0 and empty.null_count == 3
    assert empty.minimum is None and empty.maximum is None and empty.total is None


def test_last_value_follows_x_order_not_storage_order() -> None:
    x = np.array([30.0, 10.0, 20.0])
    y = np.array([3.0, 1.0, 2.0])
    agg = numeric.aggregates(x, y, unit=None, summable=False)
    assert agg.last_value == 3.0
    assert agg.first_valid_x == numeric.iso_day(10.0)


def test_display_caps_points_and_reports_downsample_truthfully() -> None:
    n = 50_000
    x = _days(n)
    y = np.sin(np.arange(n) / 50.0)
    y[1000] = 99.0  # extreme must survive decimation
    y[2000] = -99.0
    pts, info, gaps = numeric.display(x, y)
    assert len(pts) <= MAX_DISPLAY_POINTS
    assert info.applied is True and info.source_points == n and info.returned_points == len(pts)
    assert gaps == 0
    ys = [p.y for p in pts if p.y is not None]
    assert max(ys) == 99.0 and min(ys) == -99.0


def test_display_small_series_is_not_downsampled() -> None:
    pts, info, gaps = numeric.display(_days(10), np.arange(10, dtype=np.float64))
    assert len(pts) == 10 and info.applied is False and info.algorithm is None
    assert info.returned_points == 10 and gaps == 0


def test_display_preserves_gaps_as_null_points() -> None:
    y = np.array([1.0, np.nan, 3.0, np.nan, 5.0])
    pts, info, gaps = numeric.display(_days(5), y)
    assert [p.y for p in pts] == [1.0, None, 3.0, None, 5.0]
    assert gaps == 2 and info.gap_markers_preserved is True


def test_gap_count_includes_omitted_gaps_after_downsampling() -> None:
    n = 40_000
    y = np.sin(np.arange(n) / 9.0)
    y[::3] = np.nan
    pts, info, gaps = numeric.display(_days(n), y)
    assert gaps == sum(1 for p in pts if p.y is None) + info.gaps_omitted


def test_mean_is_within_extrema_for_constant_series() -> None:
    y = np.full(1000, 0.1)
    agg = numeric.aggregates(_days(1000), y, unit=None, summable=True)
    assert agg.minimum <= agg.mean <= agg.maximum


def test_display_is_deterministic() -> None:
    x = _days(30_000)
    y = np.cos(np.arange(30_000) / 7.0)
    a = numeric.display(x, y)
    b = numeric.display(x, y)
    assert [p.model_dump() for p in a[0]] == [p.model_dump() for p in b[0]]


def test_cumulative_keeps_gaps_and_does_not_fill() -> None:
    out = numeric.cumulative(np.array([1.0, np.nan, 2.0, 3.0]))
    assert out[0] == 1.0 and math.isnan(out[1]) and out[2] == 3.0 and out[3] == 6.0


def test_sum_by_day_union_of_days_and_gap_when_no_value() -> None:
    a = (np.array([1.0, 2.0]), np.array([10.0, np.nan]))
    b = (np.array([2.0, 3.0]), np.array([np.nan, 5.0]))
    days, total = numeric.sum_by_day([a, b])
    assert days.tolist() == [1.0, 2.0, 3.0]
    assert total[0] == 10.0 and math.isnan(total[1]) and total[2] == 5.0


def test_has_repeated() -> None:
    assert numeric.has_repeated(np.array([1.0, 1.0, 2.0]))
    assert not numeric.has_repeated(np.array([1.0, 2.0]))

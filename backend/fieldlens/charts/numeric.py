"""Pure, deterministic numeric helpers for chart series (no I/O).

Aggregates are exact values over the full-resolution samples; display points are a separate,
decimated view (``minmax-gap-v1``, at most ``MAX_DISPLAY_POINTS``) that keeps endpoints, extrema
and gap markers. NaN encodes a missing sample (a gap): it is never zero-filled."""

from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
from numpy.typing import NDArray

from fieldlens.contracts.charts import (
    DOWNSAMPLING_ALGORITHM,
    MAX_DISPLAY_POINTS,
    ChartPoint,
    DownsampleInfo,
    SeriesAggregates,
)
from fieldlens.series.downsample import select_positions

_EPOCH = date(1970, 1, 1)


def iso_day(epoch_day: float) -> str:
    return (_EPOCH + timedelta(days=int(epoch_day))).isoformat()


def epoch_day(value: date) -> float:
    return float((value - _EPOCH).days)


def aggregates(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    unit: str | None,
    summable: bool,
    time_axis: bool = True,
) -> SeriesAggregates:
    """Exact aggregates of the full-resolution window (``x`` is epoch days on time axes)."""
    n = int(y.size)
    good = np.flatnonzero(~np.isnan(y))
    valid = int(good.size)
    out = SeriesAggregates(count=n, valid_count=valid, null_count=n - valid, unit=unit)
    if not valid:
        return out
    picked = [float(v) for v in y[good]]
    order = good[np.lexsort((good, x[good]))]  # by x, source order on ties
    first, last = int(order[0]), int(order[-1])

    def label(position: int) -> float | str:
        return iso_day(float(x[position])) if time_axis else float(x[position])

    out.minimum = min(picked)
    out.maximum = max(picked)
    out.mean = math.fsum(picked) / valid
    out.total = math.fsum(picked) if summable else None
    out.first_valid_x = label(first)
    out.last_valid_x = label(last)
    out.last_value = float(y[last])
    return out


def display(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    time_axis: bool = True,
    max_points: int = MAX_DISPLAY_POINTS,
) -> tuple[list[ChartPoint], DownsampleInfo, int]:
    """Display points (<= ``max_points``), the downsample report and the gap (null point) count."""
    n = int(y.size)
    positions, omitted = select_positions(y, max_points)
    applied = int(positions.size) < n
    points = [
        ChartPoint(
            x=iso_day(float(x[p])) if time_axis else float(x[p]),
            y=None if math.isnan(float(y[p])) else float(y[p]),
        )
        for p in positions.tolist()
    ]
    gaps = sum(1 for p in points if p.y is None)
    info = DownsampleInfo(
        applied=applied,
        algorithm=DOWNSAMPLING_ALGORITHM if applied else None,
        max_points=max_points,
        source_points=n,
        returned_points=len(points),
        gap_markers_preserved=True,
        gaps_omitted=omitted if applied else 0,
        extrema_preserved=True,
    )
    return points, info, gaps


def cumulative(y: NDArray[np.float64]) -> NDArray[np.float64]:
    """Running total over valid samples in order; missing days stay gaps (never filled)."""
    out = np.full(y.shape, np.nan, dtype=np.float64)
    running = 0.0
    for i, value in enumerate(y.tolist()):
        if value == value:
            running += value
            out[i] = running
    return out


def sum_by_day(
    series: list[tuple[NDArray[np.float64], NDArray[np.float64]]],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Per-day sum of the valid values of several series, in the given (stable) order.

    A day present in the inputs where no series has a value stays a gap. Inputs must not repeat
    a day inside one series (callers exclude those)."""
    if not series:
        return np.zeros(0), np.zeros(0)
    days = np.unique(np.concatenate([s[0] for s in series]))
    total = np.zeros(days.size, dtype=np.float64)
    seen = np.zeros(days.size, dtype=bool)
    for x, y in series:
        ok = ~np.isnan(y)
        slot = np.searchsorted(days, x[ok])
        np.add.at(total, slot, y[ok])
        seen[slot] = True
    total[~seen] = np.nan
    return days, total


def has_repeated(x: NDArray[np.float64]) -> bool:
    return int(np.unique(x).size) != int(x.size)

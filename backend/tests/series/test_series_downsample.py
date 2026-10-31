"""DC-8 (pure part): deterministic min/max- and gap-preserving downsampling."""

from __future__ import annotations

import numpy as np
import pytest

from fieldlens.series.downsample import PER_BUCKET, RESERVED, select_positions


def _noisy(n: int, seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return np.cumsum(rng.normal(size=n)) + 5 * np.sin(np.arange(n) / 50.0)


def test_small_windows_are_returned_whole() -> None:
    v = np.array([1.0, np.nan, 3.0])
    pos, omitted = select_positions(v, 10)
    assert pos.tolist() == [0, 1, 2] and omitted == 0


@pytest.mark.parametrize("max_points", [10, 18, 100, 1000, 5000, 10_000])
def test_bounded_sorted_deterministic_and_keeps_global_extremes(max_points: int) -> None:
    v = _noisy(60_000)
    v[12_345] = v.max() + 100.0  # a one-sample spike must survive
    v[44_444] = v.min() - 100.0
    a, _ = select_positions(v, max_points)
    b, _ = select_positions(v.copy(), max_points)
    assert a.tolist() == b.tolist(), "same input, same output"
    assert a.size <= max_points
    assert a.tolist() == sorted(set(a.tolist()))
    assert 0 in a and v.size - 1 in a, "window endpoints are kept"
    assert 12_345 in a and 44_444 in a, "per-bucket extremes are never averaged away"
    assert v[a].max() == v.max() and v[a].min() == v.min()


def test_every_bucket_keeps_its_own_min_and_max() -> None:
    v = _noisy(10_000)
    max_points = 62
    pos, _ = select_positions(v, max_points)
    buckets = (max_points - RESERVED) // PER_BUCKET
    edges = (np.arange(buckets + 1) * v.size) // buckets
    kept = set(pos.tolist())
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        seg = v[lo:hi]
        assert lo + int(np.argmin(seg)) in kept
        assert lo + int(np.argmax(seg)) in kept


def test_null_gaps_are_preserved_with_exact_extent() -> None:
    v = _noisy(1000)
    v[100:140] = np.nan
    v[500] = np.nan
    pos, omitted = select_positions(v, 62)
    kept = pos.tolist()
    assert omitted == 0
    assert {99, 100, 140} <= set(kept), "valid sample before, gap start, valid sample after"
    assert {499, 500, 501} <= set(kept)
    out = v[pos]
    assert np.isnan(out).sum() >= 2, "gaps stay visible as nulls"
    # no kept valid sample falls inside a gap
    assert not any(100 < p < 140 for p in kept if not np.isnan(v[p]))


def test_all_null_window_and_leading_trailing_gaps() -> None:
    v = np.full(500, np.nan)
    pos, omitted = select_positions(v, 62)
    assert 0 in pos and 499 in pos and np.isnan(v[pos]).all() and omitted == 0
    w = _noisy(500)
    w[:30] = np.nan
    w[-30:] = np.nan
    pos, _ = select_positions(w, 62)
    assert 30 in pos and 469 in pos and 470 in pos, "valid sample before/after each gap kept"
    assert np.isnan(w[pos[0]]) and np.isnan(w[pos[-1]])


def test_unrepresentable_null_runs_are_counted_not_hidden() -> None:
    v = _noisy(100)
    v[1:99:2] = np.nan  # 49 separate one-sample gaps in a window of 100
    pos, omitted = select_positions(v, 10)  # one bucket
    assert omitted == 49 - 2
    assert pos.size <= 10


def test_constant_series_ties_use_first_occurrence() -> None:
    v = np.full(200, 3.0)
    a, _ = select_positions(v, 14)
    assert a.size <= 14 and v[a].min() == v[a].max() == 3.0


def test_property_random_series_bounds_and_extremes() -> None:
    rng = np.random.default_rng(11)
    for _ in range(40):
        n = int(rng.integers(20, 5000))
        v = rng.normal(size=n)
        v[rng.random(n) < rng.random() * 0.4] = np.nan
        if np.isnan(v).all():
            continue
        m = int(rng.integers(10, 400))
        pos, _ = select_positions(v, m)
        assert pos.size <= max(m, n) and (n <= m or pos.size <= m)
        valid = v[~np.isnan(v)]
        assert np.nanmax(v[pos]) == valid.max() if n > m else True
        assert np.nanmin(v[pos]) == valid.min() if n > m else True

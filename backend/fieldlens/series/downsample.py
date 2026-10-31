"""Deterministic min/max- and gap-preserving window downsampling (``minmax-gap-v1``).

The window's ``n`` samples are cut into ``B = (max_points - 2) // 8`` buckets of (almost) equal
sample count: bucket ``b`` covers positions ``[b*n//B, (b+1)*n//B)``. Each bucket keeps

* its minimum and maximum valid sample (first occurrence on ties), at their own positions;
* for the first two null runs that *start* in it, the last valid sample before the run, the
  first null sample and the first valid sample after it (so the drawn gap spans exactly the
  null run).

The window's first and last sample are always kept. At most ``2 + 8B <= max_points`` positions
come back, sorted, so null gaps stay visible and no extreme is averaged away. Null runs beyond
two per bucket cannot be represented and are counted in ``gaps_omitted`` (never hidden). The
result depends only on the values and ``max_points``."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

PER_BUCKET = 8
RESERVED = 2  # window first and last sample


def select_positions(values: NDArray[np.float64], max_points: int) -> tuple[NDArray[np.int64], int]:
    """Positions (into ``values``) to keep and the number of null runs left unrepresented."""
    n = int(values.size)
    if n <= max_points:
        return np.arange(n, dtype=np.int64), 0
    buckets = (max_points - RESERVED) // PER_BUCKET
    if buckets < 1:
        raise ValueError("max_points is too small to downsample")
    edges = (np.arange(buckets + 1, dtype=np.int64) * n) // buckets
    starts = edges[:-1]
    sizes = np.diff(edges)
    bucket_of = np.repeat(np.arange(buckets, dtype=np.int64), sizes)
    null = np.isnan(values)
    keep: list[NDArray[np.int64]] = [np.array([0, n - 1], dtype=np.int64)]

    valid_counts = np.add.reduceat((~null).astype(np.int64), starts)
    has_valid = valid_counts > 0
    for fill, reduce, pick in (
        (np.inf, np.minimum, "min"),
        (-np.inf, np.maximum, "max"),
    ):
        filled = np.where(null, fill, values)
        extreme = reduce.reduceat(filled, starts)
        hit = np.flatnonzero((filled == extreme[bucket_of]) & ~null)
        first_hit = np.unique(bucket_of[hit], return_index=True)[1]
        picked = hit[first_hit]  # first occurrence per bucket with a valid sample
        assert picked.size == int(has_valid.sum()), pick
        keep.append(picked)

    padded = np.concatenate(([False], null, [False])).astype(np.int8)
    change = np.diff(padded)
    run_start = np.flatnonzero(change == 1)
    run_after = np.flatnonzero(
        change == -1
    )  # first sample after each run (n if it ends the window)
    omitted = 0
    if run_start.size:
        run_bucket = bucket_of[run_start]
        _, first_of_bucket, counts = np.unique(run_bucket, return_index=True, return_counts=True)
        rank = np.arange(run_start.size) - np.repeat(first_of_bucket, counts)
        kept = rank < 2
        omitted = int((~kept).sum())
        keep.append(run_start[kept])
        before = run_start[kept] - 1
        keep.append(before[before >= 0])
        after = run_after[kept]
        keep.append(after[after < n])
    return np.unique(np.concatenate(keep)), omitted

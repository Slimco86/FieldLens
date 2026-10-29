"""Closest 3D approach between two analytic trajectories (TR-3).

Method: every minimum-curvature segment is a circular arc. Each arc is split (by exact arc
interpolation) into sub-arcs whose chord sagitta ``R(1 - cos(phi/2))`` is <= 0.01 m, giving a
polyline per path. The exact minimum distance between the two polylines is found with an
AABB broad phase that only prunes pairs whose box gap already exceeds the current best
(conservative: no potentially closest piece is skipped). Because each path deviates from its
polyline by at most its sagitta bound, ``|d_true - d_polyline| <= bound_a + bound_b``
(<= 0.02 m). The bound is computed from geometry only and does not depend on display
sampling, LOD or exaggeration.

IMPORTANT: a distance is a geometric measurement of two surveyed paths. It is NOT proof of
connectivity, pressure communication, or safe clearance, and it carries survey uncertainty
that this module does not model.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from fieldlens.engineering.trajectory.mincurve import (
    Trajectory,
    _ratio_factor,
    _tangent_at,
)

Array = NDArray[np.float64]

MAX_CHORD_DEVIATION_M = 0.01
MAX_SEGMENTS_PER_BORE = 10_000
_MAX_SUBDIVISIONS_PER_SEGMENT = 2_000
PROXIMITY_CAVEAT = (
    "Minimum distance between surveyed paths only; not proof of connectivity, pressure "
    "communication or safe clearance."
)


class ProximityStatus(StrEnum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class ProximityResult:
    """Closest approach. ``distance_m`` is exact for the bounded polylines; the true
    arc-to-arc minimum lies in ``[lower_bound_m, upper_bound_m]``. Points lie on the actual
    arc paths at ``md_a_m``/``md_b_m`` (metres, derived MD). When several closest pairs
    exist, the first in (path A MD, path B MD) order is returned. ``UNRESOLVED`` carries no
    distance and must never be presented as an exact or best-so-far result."""

    status: ProximityStatus
    unresolved_reason: str | None = None
    distance_m: float | None = None
    error_bound_m: float | None = None
    lower_bound_m: float | None = None
    upper_bound_m: float | None = None
    md_a_m: float | None = None
    md_b_m: float | None = None
    point_a: tuple[float, float, float] | None = None
    point_b: tuple[float, float, float] | None = None
    caveat: str = PROXIMITY_CAVEAT


@dataclass(frozen=True, slots=True)
class _Pieces:
    p0: Array
    p1: Array
    md0: Array
    md1: Array
    bound: float


def _pieces(traj: Trajectory) -> _Pieces | None:
    p0: list[Array] = []
    p1: list[Array] = []
    m0: list[float] = []
    m1: list[float] = []
    bound = 0.0
    for i in range(len(traj.md_m) - 1):
        length = float(traj.md_m[i + 1] - traj.md_m[i])
        beta = float(traj.dogleg_rad[i])
        n = 1
        if beta > 0.0:
            radius = length / beta
            ratio = MAX_CHORD_DEVIATION_M / radius
            if ratio < 2.0:
                n = max(1, math.ceil(beta / (2.0 * math.acos(max(-1.0, 1.0 - ratio)))))
            while radius * (1.0 - math.cos(beta / (2.0 * n))) > MAX_CHORD_DEVIATION_M:
                n += 1
            if n > _MAX_SUBDIVISIONS_PER_SEGMENT:
                return None
            bound = max(bound, radius * (1.0 - math.cos(beta / (2.0 * n))))
        t1, t2 = traj.tangents[i], traj.tangents[i + 1]
        prev = traj.positions[i]
        for k in range(1, n + 1):
            if k == n:
                cur = traj.positions[i + 1]
            else:
                ds = length * k / n
                u = k / n
                tu = _tangent_at(t1, t2, beta, u)
                cur = traj.positions[i] + 0.5 * ds * (t1 + tu) * _ratio_factor(u * beta)
            p0.append(prev)
            p1.append(cur)
            m0.append(float(traj.md_m[i]) + length * (k - 1) / n)
            m1.append(float(traj.md_m[i]) + length * k / n)
            prev = cur
    return _Pieces(np.array(p0), np.array(p1), np.array(m0), np.array(m1), bound)


def _point_seg(p: Array, a: Array, b: Array) -> tuple[Array, Array]:
    d = b - a
    dd = np.einsum("ij,ij->i", d, d)
    t = np.clip(np.einsum("ij,ij->i", p - a, d) / np.where(dd > 0.0, dd, 1.0), 0.0, 1.0)
    q = a + d * t[:, None]
    return np.einsum("ij,ij->i", p - q, p - q), t


def _seg_seg(a0: Array, a1: Array, b0: Array, b1: Array) -> tuple[Array, Array, Array]:
    """Vectorised exact segment-segment squared distance and parameters (s on A, t on B).

    The squared distance is convex over the (s, t) box, so its minimum is either an interior
    critical point or lies on the boundary (an endpoint of one segment vs the other segment).
    """
    n = a0.shape[0]
    best = np.full(n, np.inf)
    bs = np.zeros(n)
    bt = np.zeros(n)

    def consider(d2: Array, s: Array, t: Array) -> None:
        better = d2 < best
        best[better] = d2[better]
        bs[better] = s[better]
        bt[better] = t[better]

    zeros, ones = np.zeros(n), np.ones(n)
    d2, t = _point_seg(a0, b0, b1)
    consider(d2, zeros, t)
    d2, t = _point_seg(a1, b0, b1)
    consider(d2, ones, t)
    d2, s = _point_seg(b0, a0, a1)
    consider(d2, s, zeros)
    d2, s = _point_seg(b1, a0, a1)
    consider(d2, s, ones)

    d1, d2v, r = a1 - a0, b1 - b0, a0 - b0
    a = np.einsum("ij,ij->i", d1, d1)
    e = np.einsum("ij,ij->i", d2v, d2v)
    b = np.einsum("ij,ij->i", d1, d2v)
    c = np.einsum("ij,ij->i", d1, r)
    f = np.einsum("ij,ij->i", d2v, r)
    denom = a * e - b * b
    ok = (denom > 1e-12 * a * e) & (a > 0.0) & (e > 0.0)
    safe = np.where(ok, denom, 1.0)
    s = (b * f - c * e) / safe
    t = (a * f - b * c) / safe
    ok &= (s > 0.0) & (s < 1.0) & (t > 0.0) & (t < 1.0)
    diff = (a0 + d1 * s[:, None]) - (b0 + d2v * t[:, None])
    d2i = np.where(ok, np.einsum("ij,ij->i", diff, diff), np.inf)
    consider(d2i, s, t)
    return best, bs, bt


def _unresolved(reason: str) -> ProximityResult:
    return ProximityResult(status=ProximityStatus.UNRESOLVED, unresolved_reason=reason)


def closest_approach(
    a: Trajectory,
    b: Trajectory,
    *,
    max_segments_per_bore: int = MAX_SEGMENTS_PER_BORE,
    deadline_monotonic: float | None = None,
) -> ProximityResult:
    """3D minimum distance between two trajectories in the same physical frame.

    The caller must ensure both share CRS/datum; differing references are refused as
    unresolved rather than compared. No extrapolation beyond surveyed MD. Exceeding the
    segment budget or ``deadline_monotonic`` (``time.monotonic()`` value) returns an explicit
    ``UNRESOLVED`` result. This is a distance measurement, not proof of connectivity or
    safe clearance.
    """
    ra, rb = a.survey.reference, b.survey.reference
    if (ra.crs, ra.vertical_datum) != (rb.crs, rb.vertical_datum):
        return _unresolved("trajectories do not share CRS and vertical datum")
    if max(len(a.md_m), len(b.md_m)) - 1 > max_segments_per_bore:
        return _unresolved(f"segment count exceeds {max_segments_per_bore} per bore")
    pa, pb = _pieces(a), _pieces(b)
    if pa is None or pb is None:
        return _unresolved("curvature too high to bound chord deviation")

    lo_a, hi_a = np.minimum(pa.p0, pa.p1), np.maximum(pa.p0, pa.p1)
    lo_b, hi_b = np.minimum(pb.p0, pb.p1), np.maximum(pb.p0, pb.p1)
    best = math.inf
    best_i = best_j = -1
    best_s = best_t = 0.0
    for i in range(len(pa.md0)):
        if deadline_monotonic is not None and time.monotonic() > deadline_monotonic:
            return _unresolved("job deadline reached before search completed")
        gap = np.maximum(np.maximum(lo_b - hi_a[i], lo_a[i] - hi_b), 0.0)
        gap2 = np.einsum("ij,ij->i", gap, gap)
        cand = np.flatnonzero(gap2 < best)  # conservative: only prune strictly worse boxes
        if cand.size == 0:
            continue
        m = cand.size
        d2, s, t = _seg_seg(
            np.broadcast_to(pa.p0[i], (m, 3)),
            np.broadcast_to(pa.p1[i], (m, 3)),
            pb.p0[cand],
            pb.p1[cand],
        )
        k = int(np.argmin(d2))
        if d2[k] < best:
            best, best_i, best_j = float(d2[k]), i, int(cand[k])
            best_s, best_t = float(s[k]), float(t[k])

    md_a = float(pa.md0[best_i] + best_s * (pa.md1[best_i] - pa.md0[best_i]))
    md_b = float(pb.md0[best_j] + best_t * (pb.md1[best_j] - pb.md0[best_j]))
    md_a = min(max(md_a, float(a.md_m[0])), float(a.md_m[-1]))
    md_b = min(max(md_b, float(b.md_m[0])), float(b.md_m[-1]))
    point_a, point_b = a.position_at_md(md_a), b.position_at_md(md_b)
    dist = math.sqrt(best)
    bound = pa.bound + pb.bound
    return ProximityResult(
        status=ProximityStatus.RESOLVED,
        distance_m=dist,
        error_bound_m=bound,
        lower_bound_m=max(0.0, dist - bound),
        upper_bound_m=dist + bound,
        md_a_m=md_a,
        md_b_m=md_b,
        point_a=(float(point_a[0]), float(point_a[1]), float(point_a[2])),
        point_b=(float(point_b[0]), float(point_b[1]), float(point_b[2])),
    )

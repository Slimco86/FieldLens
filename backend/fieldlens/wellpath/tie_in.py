"""Derived wellhead tie-in segment (TASK-091, EXPLORE_POLISH section F). DISPLAY ONLY.

A survey may start below the wellhead (the first station at MD > 0 with a stated TVD). The real
stations are never translated or altered; this module only builds a separate, flagged-derived
polyline from the wellhead (MD 0, TVD 0, local origin) to the first station so the viewer can draw
the trace and place MD-placed components without a gap. No calculation (closest approach,
perforated length, TVD/MD analytics) consumes it.

Geometry (local frame east, north, z-up; the first station is at east = north = 0, z = -TVD):

* ``vertical``: first TVD equals first MD and inclination is ~0 -> straight vertical line.
* ``arc``: otherwise a cubic Hermite curve with a vertical tangent at the wellhead and the first
  station's own tangent (inclination/azimuth) at its end, ending exactly on the first station. Its
  tangent magnitude is solved so the curve's arc length equals the first station MD (so MD along
  the tie-in is true curve length). It is emitted only if the maximum dogleg severity is plausible.

Otherwise nothing is derived (never invented geometry, never zero-filled)."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from fieldlens.contracts.trajectory import TrajectoryPoint

#: |MD - TVD| (m) and inclination (deg) under which the first station counts as vertical.
VERTICAL_MD_TVD_TOL_M = 0.05
VERTICAL_INCL_TOL_DEG = 0.1
#: Largest dogleg severity (deg per 30 m) accepted for a derived arc. Rationale: conventional
#: directional build/turn rates are 1-5 deg/30 m and rarely exceed ~10 deg/30 m for ordinary
#: wells; a larger implied curvature means the stated first station is not a smooth continuation
#: of a vertical hole, so no geometry is invented.
MAX_DLS_DEG_PER_30M = 10.0
#: Tolerance (m) between the required MD and the shortest (chord-length) curve.
LENGTH_TOL_M = 0.05

_DENSE = 400
_OUT_POINTS = 24


@dataclass(frozen=True)
class TieIn:
    kind: str  # "vertical" | "arc"
    points: list[TrajectoryPoint]
    max_dls_deg_per_30m: float


@dataclass(frozen=True)
class TieInRejected:
    code: str
    message: str


def _hermite(m: float, tvd: float, t1: np.ndarray) -> np.ndarray:
    u = np.linspace(0.0, 1.0, _DENSE + 1)[:, None]
    p0 = np.zeros(3)
    p1 = np.array([0.0, 0.0, -tvd])
    m0 = np.array([0.0, 0.0, -m])
    m1 = m * t1
    h00 = 2 * u**3 - 3 * u**2 + 1
    h10 = u**3 - 2 * u**2 + u
    h01 = -2 * u**3 + 3 * u**2
    h11 = u**3 - u**2
    out: np.ndarray = h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1
    out[-1] = p1
    return out


def _length(curve: np.ndarray) -> float:
    return float(np.sum(np.linalg.norm(np.diff(curve, axis=0), axis=1)))


def derive_tie_in(
    md_m: float, tvd_m: float, incl_deg: float, azi_deg: float
) -> TieIn | TieInRejected | None:
    """Tie-in for a first station, ``None`` when none is needed (MD <= 0)."""
    if not all(math.isfinite(v) for v in (md_m, tvd_m, incl_deg, azi_deg)):
        return None
    if md_m <= 0.0:
        return None
    if tvd_m <= 0.0:
        return TieInRejected("TIE_IN_NOT_DERIVED", "The first station TVD is not positive.")
    if abs(md_m - tvd_m) <= VERTICAL_MD_TVD_TOL_M and abs(incl_deg) <= VERTICAL_INCL_TOL_DEG:
        return TieIn(
            "vertical",
            [
                TrajectoryPoint(md_m=0.0, tvd_m=0.0, east_m=0.0, north_m=0.0),
                TrajectoryPoint(md_m=md_m, tvd_m=tvd_m, east_m=0.0, north_m=0.0),
            ],
            0.0,
        )
    if md_m < tvd_m - LENGTH_TOL_M:
        return TieInRejected(
            "TIE_IN_NOT_DERIVED",
            "The first station MD is shorter than its TVD; no tie-in curve is invented.",
        )
    i, a = math.radians(incl_deg), math.radians(azi_deg)
    t1 = np.array([math.sin(i) * math.sin(a), math.sin(i) * math.cos(a), -math.cos(i)])
    lo, hi = 0.0, 4.0 * md_m
    if _length(_hermite(hi, tvd_m, t1)) < md_m:
        return TieInRejected(
            "TIE_IN_NOT_DERIVED", "No smooth tie-in curve matches the first station MD."
        )
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if _length(_hermite(mid, tvd_m, t1)) < md_m:
            lo = mid
        else:
            hi = mid
    curve = _hermite(0.5 * (lo + hi), tvd_m, t1)
    seg = np.linalg.norm(np.diff(curve, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    scale = md_m / cum[-1]
    cum = cum * scale
    tang = np.diff(curve, axis=0) / np.maximum(seg, 1e-12)[:, None]
    dots = np.clip(np.sum(tang[:-1] * tang[1:], axis=1), -1.0, 1.0)
    ds = 0.5 * (seg[:-1] + seg[1:]) * scale
    dls = float(np.max(np.degrees(np.arccos(dots)) / np.maximum(ds, 1e-9) * 30.0))
    # Include the junction with the real survey: the end tangent is the station tangent already.
    if dls > MAX_DLS_DEG_PER_30M:
        return TieInRejected(
            "TIE_IN_NOT_DERIVED",
            f"The implied dogleg severity ({dls:.1f} deg/30 m) exceeds "
            f"{MAX_DLS_DEG_PER_30M:.0f} deg/30 m; no tie-in curve is invented.",
        )
    mds = np.linspace(0.0, md_m, _OUT_POINTS)
    pts = [
        TrajectoryPoint(
            md_m=float(md),
            tvd_m=float(-np.interp(md, cum, curve[:, 2])),
            east_m=float(np.interp(md, cum, curve[:, 0])),
            north_m=float(np.interp(md, cum, curve[:, 1])),
        )
        for md in mds
    ]
    pts[0] = TrajectoryPoint(md_m=0.0, tvd_m=0.0, east_m=0.0, north_m=0.0)
    pts[-1] = TrajectoryPoint(md_m=md_m, tvd_m=tvd_m, east_m=0.0, north_m=0.0)
    return TieIn("arc", pts, dls)

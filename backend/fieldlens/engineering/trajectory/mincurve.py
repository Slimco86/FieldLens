"""Double-precision minimum-curvature trajectories (TR-1).

Conventions (physical frame, see TRAJECTORY_VIEWER.md): coordinates are ``(E, N, z)`` in
metres, E/N in the grid of the survey CRS and ``z`` *up* from the stated vertical datum
(positive TVD down is ``-z``). Azimuth is clockwise from the north reference, inclination
is measured from vertical-down. MD is path length along the wellbore and is never treated
as TVD. All arithmetic is float64 and independent of any display sampling.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from fieldlens.engineering.trajectory.survey import (
    NorthReference,
    Survey,
    SurveyBlockedError,
    SurveyIssue,
    SurveyIssueCode,
    md_to_meters,
    validate_survey,
)

Array = NDArray[np.float64]
_REVERSAL_LIMIT = math.pi - 1e-9


def _tangent(inc_rad: float, az_rad: float) -> Array:
    s = math.sin(inc_rad)
    return np.array([s * math.sin(az_rad), s * math.cos(az_rad), -math.cos(inc_rad)])


def _dogleg(t1: Array, t2: Array) -> float:
    return math.atan2(float(np.linalg.norm(np.cross(t1, t2))), float(np.dot(t1, t2)))


def _ratio_factor(beta: float) -> float:
    """Minimum-curvature RF = tan(beta/2)/(beta/2), exactly 1 at zero dogleg."""
    x = beta / 2.0
    if x < 1e-4:
        return 1.0 + x * x / 3.0 + 2.0 * x**4 / 15.0
    return math.tan(x) / x


def _tangent_at(t1: Array, t2: Array, beta: float, u: float) -> Array:
    """Spherical interpolation of the tangent at fraction ``u`` of the segment."""
    if beta == 0.0:
        return t1
    sb = math.sin(beta)
    return (math.sin((1.0 - u) * beta) * t1 + math.sin(u * beta) * t2) / sb


@dataclass(frozen=True, slots=True)
class Trajectory:
    """Derived physical trajectory plus the untouched source survey.

    Arrays are read-only. ``source_indices[i]`` is the index into ``survey.stations`` of
    derived station ``i`` (exactly repeated stations are dropped, not altered).
    ``md_m`` etc. are derived (metres, grid azimuth); original values stay in ``survey``.
    """

    survey: Survey
    source_indices: tuple[int, ...]
    md_m: Array
    inclination_rad: Array
    grid_azimuth_rad: Array
    positions: Array  # (n, 3) E, N, z-up, metres
    tangents: Array  # (n, 3) unit, E, N, z-up
    dogleg_rad: Array  # (n-1,)

    def position_at_md(self, md_m: float) -> Array:
        """Position at ``md_m`` (metres) on the arc; never extrapolates beyond the survey."""
        if not (self.md_m[0] <= md_m <= self.md_m[-1]):
            raise ValueError("MD outside surveyed range; extrapolation is not performed")
        i = int(np.searchsorted(self.md_m, md_m, side="right")) - 1
        i = min(i, len(self.md_m) - 2)
        return self._segment_point(i, md_m - float(self.md_m[i]))

    def _segment_point(self, i: int, ds: float) -> Array:
        length = float(self.md_m[i + 1] - self.md_m[i])
        t1, t2, beta = self.tangents[i], self.tangents[i + 1], float(self.dogleg_rad[i])
        u = ds / length
        tu = _tangent_at(t1, t2, beta, u)
        out: Array = self.positions[i] + 0.5 * ds * (t1 + tu) * _ratio_factor(u * beta)
        return out


def _grid_azimuth_deg(survey: Survey, azimuth_deg: float) -> float:
    ref = survey.reference
    if ref.north_reference is NorthReference.GRID:
        return azimuth_deg
    assert ref.grid_convergence_deg is not None  # guaranteed by validate_survey
    if ref.north_reference is NorthReference.TRUE:
        return azimuth_deg - ref.grid_convergence_deg
    assert ref.magnetic_declination_deg is not None
    return azimuth_deg + ref.magnetic_declination_deg - ref.grid_convergence_deg


def compute_trajectory(survey: Survey) -> Trajectory:
    """Minimum-curvature coordinates for a validated survey.

    Raises :class:`SurveyBlockedError` (never returns partial/assumed geometry) when any
    reference or station issue exists.
    """
    issues = validate_survey(survey)
    if issues:
        raise SurveyBlockedError(issues)

    scale = md_to_meters(survey)
    keep: list[int] = []
    for i, s in enumerate(survey.stations):
        if keep and s.md == survey.stations[keep[-1]].md:
            continue  # validated: identical duplicate
        keep.append(i)
    if len(keep) < 2:
        raise SurveyBlockedError(
            (SurveyIssue(SurveyIssueCode.TOO_FEW_STATIONS, "no non-zero MD interval"),)
        )

    md = np.array([survey.stations[i].md * scale for i in keep], dtype=np.float64)
    inc = np.radians([survey.stations[i].inclination_deg for i in keep])
    az = np.radians([_grid_azimuth_deg(survey, survey.stations[i].azimuth_deg) for i in keep])
    tans = np.array([_tangent(float(a), float(b)) for a, b in zip(inc, az, strict=True)])

    n = len(keep)
    doglegs = np.empty(n - 1)
    pos = np.empty((n, 3))
    pos[0] = (survey.start_east_m, survey.start_north_m, survey.start_z_m)
    blocked: list[SurveyIssue] = []
    for i in range(n - 1):
        beta = _dogleg(tans[i], tans[i + 1])
        if beta > _REVERSAL_LIMIT:
            blocked.append(
                SurveyIssue(
                    SurveyIssueCode.DOGLEG_REVERSAL, "dogleg ~180 deg is undefined", keep[i + 1]
                )
            )
            continue
        doglegs[i] = beta
        pos[i + 1] = pos[i] + 0.5 * (md[i + 1] - md[i]) * (tans[i] + tans[i + 1]) * _ratio_factor(
            beta
        )
    if blocked:
        raise SurveyBlockedError(tuple(blocked))

    for arr in (md, inc, az, pos, tans, doglegs):
        arr.setflags(write=False)
    return Trajectory(survey, tuple(keep), md, inc, az, pos, tans, doglegs)


def display_samples(
    trajectory: Trajectory, count: int, vertical_exaggeration: float = 1.0
) -> Array:
    """Display-only polyline (copy). Never feeds analytics; analytic results ignore it."""
    mds = np.linspace(trajectory.md_m[0], trajectory.md_m[-1], count)
    pts = np.array([trajectory.position_at_md(float(m)) for m in mds])
    pts[:, 2] *= vertical_exaggeration
    return pts

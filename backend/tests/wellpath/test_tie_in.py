"""TASK-091 (EXPLORE_POLISH F-1..F-4): derived, display-only wellhead tie-in. Pure unit tests."""

from __future__ import annotations

import math

import numpy as np

from fieldlens.engineering.trajectory import compute_trajectory
from fieldlens.wellpath.service import _Computed, compute_set
from fieldlens.wellpath.tie_in import (
    MAX_DLS_DEG_PER_30M,
    TieIn,
    TieInRejected,
    derive_tie_in,
)
from tests.wellpath.test_trajectory_math import _row, _set


def test_f1_vertical_first_station_gives_vertical_tie_in() -> None:
    t = derive_tie_in(145.9, 145.9, 0.0, 0.0)
    assert isinstance(t, TieIn) and t.kind == "vertical"
    assert [(p.md_m, p.tvd_m, p.east_m, p.north_m) for p in t.points] == [
        (0.0, 0.0, 0.0, 0.0),
        (145.9, 145.9, 0.0, 0.0),
    ]


def test_f2_inclined_first_station_arc_matches_tangent_and_endpoints() -> None:
    md, tvd, incl, azi = 502.0, 500.0, 12.0, 70.0
    t = derive_tie_in(md, tvd, incl, azi)
    assert isinstance(t, TieIn) and t.kind == "arc"
    assert t.max_dls_deg_per_30m <= MAX_DLS_DEG_PER_30M
    p = t.points
    assert (p[0].md_m, p[0].tvd_m, p[0].east_m, p[0].north_m) == (0.0, 0.0, 0.0, 0.0)
    assert (p[-1].md_m, p[-1].tvd_m, p[-1].east_m, p[-1].north_m) == (md, tvd, 0.0, 0.0)
    assert all(a.md_m < b.md_m for a, b in zip(p, p[1:], strict=False))
    # wellhead tangent vertical, end tangent equals the station tangent (finite differences)
    xyz = np.array([[q.east_m, q.north_m, -q.tvd_m] for q in p])
    d0, d1 = xyz[1] - xyz[0], xyz[-1] - xyz[-2]
    d0, d1 = d0 / np.linalg.norm(d0), d1 / np.linalg.norm(d1)
    assert math.degrees(math.acos(float(d0 @ [0, 0, -1.0]))) < 3.0
    i, a = math.radians(incl), math.radians(azi)
    t1 = [math.sin(i) * math.sin(a), math.sin(i) * math.cos(a), -math.cos(i)]
    assert math.degrees(math.acos(float(np.clip(d1 @ t1, -1, 1)))) < 3.0
    # MD is curve length: polyline length within a small fraction of the stated MD
    length = float(np.sum(np.linalg.norm(np.diff(xyz, axis=0), axis=1)))
    assert abs(length - md) / md < 0.01


def test_f4_none_when_md_zero_or_inputs_missing_or_implausible() -> None:
    assert derive_tie_in(0.0, 0.0, 0.0, 0.0) is None
    assert derive_tie_in(float("nan"), 100.0, 0.0, 0.0) is None
    assert derive_tie_in(100.0, float("nan"), 0.0, 0.0) is None
    # MD shorter than TVD: impossible path
    assert isinstance(derive_tie_in(90.0, 100.0, 0.0, 0.0), TieInRejected)
    # steep inclination right at the start of a short hole: dogleg far above the threshold
    r = derive_tie_in(100.0, 99.0, 60.0, 0.0)
    assert isinstance(r, TieInRejected) and r.code == "TIE_IN_NOT_DERIVED"


def test_deterministic() -> None:
    assert derive_tie_in(502.0, 500.0, 12.0, 70.0) == derive_tie_in(502.0, 500.0, 12.0, 70.0)


def test_f3_analytics_do_not_depend_on_tie_in() -> None:
    """compute_set (the only analytic source) never sees the tie-in: arrays are identical when the
    tie-in is derived, and the tie-in is built from, not fed back to, the first station."""
    rows = [
        _row(0, 145.9, 0.0, 0.0, tvd=145.9),
        _row(1, 245.9, 5.0, 30.0),
        _row(2, 345.9, 8.0, 40.0),
    ]
    s = _set(rows)
    a, b = compute_set(s), compute_set(s)
    assert isinstance(a, _Computed) and isinstance(b, _Computed)
    assert a.first_tvd_m == 145.9
    before = (a.trajectory.positions.tobytes(), a.trajectory.md_m.tobytes())
    derive_tie_in(145.9, 145.9, 0.0, 0.0)
    again = compute_trajectory(a.trajectory.survey)
    assert before == (again.positions.tobytes(), again.md_m.tobytes())
    assert (b.trajectory.positions.tobytes(), b.trajectory.md_m.tobytes()) == before
    assert a.trajectory.positions[0, 2] == -145.9  # real station not translated

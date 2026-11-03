"""Pure min-curvature checks for the trajectory view (no database): analytic tangent and a
reversing-inclination case, plus the display-only downsample."""

from __future__ import annotations

import math
from uuid import uuid4

from fieldlens.wellpath.service import _Computed, _Row, _Set, compute_set, display_points


def _row(i: int, md: float, incl: float, azi: float, tvd: float | None = None) -> _Row:
    def a(key: str, v: float, unit: str, ref: str | None = None) -> dict[str, object]:
        return {
            "key": f"trajectory_station.{key}",
            "number": v,
            "unit": unit,
            "normalized_number": None,
            "normalized_unit": None,
            "validation_state": "unreviewed",
            "reference": ref,
        }

    return _Row(
        record_id=uuid4(),
        run_id=uuid4(),
        document_id=uuid4(),
        ordinal=i,
        kind="trajectory_station",
        state="unreviewed",
        locator={},
        attrs=[
            a("md", md, "m"),
            a("incl", incl, "deg"),
            a("azi", azi, "deg", "true north"),
            *([a("tvd", tvd, "m")] if tvd is not None else []),
        ],  # type: ignore[list-item]
        filename="x",
        when=None,
    )


def _set(rows: list[_Row]) -> _Set:
    return _Set(uuid4(), uuid4(), "x", None, "as_built", rows)


def test_straight_inclined_hole_is_analytic() -> None:
    c = compute_set(_set([_row(0, 0, 30, 45), _row(1, 1000, 30, 45)]))
    assert isinstance(c, _Computed)
    p = c.trajectory.positions[-1]
    expected_h = 1000 * math.sin(math.radians(30)) * math.sin(math.radians(45))
    assert abs(p[0] - expected_h) < 1e-9 and abs(p[1] - expected_h) < 1e-9
    assert abs(-p[2] - 1000 * math.cos(math.radians(30))) < 1e-9
    assert c.north == "true" and c.azimuth_reference == "true north"


def test_reversing_inclination_returns_tvd_and_stays_finite() -> None:
    # build to 120 deg (heading up again), tvd must be non-monotonic and offsets finite
    rows = [_row(0, 0, 0, 0), _row(1, 1000, 90, 0), _row(2, 2000, 120, 0)]
    c = compute_set(_set(rows))
    assert isinstance(c, _Computed)
    pts = display_points(c.trajectory)
    assert len(pts) == 3
    assert pts[2].tvd_m < pts[1].tvd_m + 1000  # cos(120) < 0: moves up from 90 deg
    assert all(math.isfinite(v) for p in pts for v in (p.east_m, p.north_m, p.tvd_m))


def test_downsample_is_display_only_and_keeps_exact_ends() -> None:
    rows = [_row(i, 10.0 * i, 0.05 * i, 30.0) for i in range(1000)]
    c = compute_set(_set(rows))
    assert isinstance(c, _Computed)
    pts = display_points(c.trajectory, 50)
    assert len(pts) == 50 and pts[-1].md_m == float(c.trajectory.md_m[-1])
    assert len(c.trajectory.md_m) == 1000  # the full-resolution analytic result is untouched

"""TASK-083 route tests on PostgreSQL (synthetic, invented surveys): as-built vs planned, no survey,
invalid stations blocking only their wellbore, references/units, CRS only when stated, display
downsampling and project isolation. Min-curvature numbers are checked against analytic cases."""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID, uuid4

from fieldlens.identity.resolver import resolve_project
from fieldlens.persistence.session import session_scope
from tests.retrieval.support import World, attr, rec

R = 1000.0 / (math.pi / 2)  # radius of a 90 deg build over 1000 m (analytic)
F5 = ("15/9-F-5", "15/9-F-5")
F6 = ("15/9-F-6", "15/9-F-6")


def _subj(label: str, key: str) -> dict[str, Any]:
    return {
        "well_name": label,
        "wellbore_name": None,
        "wellbore_label": label,
        "well_key": key,
        "wellbore_suffix": None,
    }


def _st(
    who: tuple[str, str],
    md: float,
    incl: float,
    azi: float,
    *,
    unit: str = "m",
    azi_ref: str | None = "grid north",
    state: str = "unreviewed",
    md_state: str = "unreviewed",
    tvd: float | None = None,
) -> dict[str, Any]:
    attrs = [
        attr("trajectory_station.md", str(md), unit, number=md, state=md_state, reference="RKB"),
        attr("trajectory_station.incl", str(incl), "deg", number=incl),
        attr("trajectory_station.azi", str(azi), "deg", number=azi, reference=azi_ref),
    ]
    if tvd is not None:
        attrs.append(attr("trajectory_station.tvd", str(tvd), unit, number=tvd))
    return rec("trajectory_station", _subj(*who), attrs, state=state)


def _hdr(who: tuple[str, str], status: str | None) -> dict[str, Any]:
    a = attr("survey_report_header.survey_status", status)
    a["text"] = status
    return rec("survey_report_header", _subj(*who), [a])


def _surface(
    who: tuple[str, str], e: float, n: float, crs: str | None, datum: str | None = None
) -> dict[str, Any]:
    attrs = [
        attr("well_surface_location.easting", str(e), "m", number=e, reference=crs),
        attr("well_surface_location.northing", str(n), "m", number=n, reference=crs),
    ]
    if datum:
        a = attr("well_surface_location.geo_datum", datum)
        a["text"] = datum
        attrs.append(a)
    return rec("well_surface_location", _subj(*who), attrs)


def _build(who: tuple[str, str]) -> list[dict[str, Any]]:
    return [_st(who, 0.0, 0.0, 0.0, tvd=0.0), _st(who, 1000.0, 90.0, 90.0, tvd=R)]


def _bore(world: World, pid: str, name: str) -> str:
    with session_scope(world.factory) as session:
        resolve_project(session, UUID(pid))
    r = world.api.client.get(f"/api/v1/projects/{pid}/identity")
    assert r.status_code == 200, r.text
    return str(
        next(
            b["wellbore_id"] for w in r.json()["wells"] for b in w["wellbores"] if b["name"] == name
        )
    )


def _get(world: World, pid: str, wb: str) -> Any:
    return world.api.client.get(f"/api/v1/projects/{pid}/wellbores/{wb}/trajectory")


def test_as_built_offsets_match_analytic_and_references_are_preserved(world: World) -> None:
    pid = world.project()
    surface = _surface(F5, 456000.0, 6780000.0, "ED50 UTM 31N", "ED50")
    world.add_doc(pid, "ssr.pdf", [_hdr(F5, "as_built"), *_build(F5), surface])
    r = _get(world, pid, _bore(world, pid, "15/9-F-5"))
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["method"] == "minimum_curvature"
    assert t["survey_status"] == "as_built"
    assert t["survey_set"]["filename"] == "ssr.pdf" and t["survey_set"]["used"] is True
    assert t["source_count"] == 2 and t["displayed_count"] == 2
    last = t["points"][-1]
    assert abs(last["east_m"] - R) < 1e-6 and abs(last["tvd_m"] - R) < 1e-6
    assert abs(last["north_m"]) < 1e-9 and last["md_m"] == 1000.0
    assert t["points"][0] == {"md_m": 0.0, "tvd_m": 0.0, "east_m": 0.0, "north_m": 0.0}
    assert abs(t["source_tvd_max_abs_diff_m"]) < 1e-6
    assert t["azimuth_reference"] == "grid north" and t["north_reference"] == "grid"
    assert t["md_reference"] == "RKB" and t["md_unit"] == "m"
    assert t["crs"] == "ED50 UTM 31N" and t["geodetic_datum"] == "ED50"
    sl = t["surface_location"]
    assert (sl["easting"], sl["northing"], sl["unit"]) == (456000.0, 6780000.0, "m")
    assert sl["evidence"]["kind"] == "well_surface_location"
    assert {e["kind"] for e in t["evidence"]} >= {"trajectory_station", "survey_report_header"}
    assert all(e["locator"]["document_id"] for e in t["evidence"])


def test_crs_is_null_when_not_stated_and_surface_missing_is_null(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "a.txt", [_hdr(F5, "as_built"), *_build(F5), _surface(F5, 1.0, 2.0, None)])
    world.add_doc(pid, "b.txt", [_hdr(F6, "as_built"), *_build(F6)])
    t5 = _get(world, pid, _bore(world, pid, "15/9-F-5")).json()
    assert t5["crs"] is None and t5["surface_location"]["crs"] is None
    assert any(w["code"] == "CRS_NOT_STATED" for w in t5["warnings"])
    t6 = _get(world, pid, _bore(world, pid, "15/9-F-6")).json()
    assert t6["surface_location"] is None and t6["crs"] is None


def test_planned_and_as_built_never_mixed(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "plan.txt", [_hdr(F5, "planned"), _st(F5, 0, 0, 0), _st(F5, 500, 0, 0)])
    world.add_doc(pid, "actual.txt", [_hdr(F5, "as_built"), *_build(F5)])
    t = _get(world, pid, _bore(world, pid, "15/9-F-5")).json()
    assert t["survey_set"]["filename"] == "actual.txt" and t["survey_status"] == "as_built"
    assert t["points"][-1]["md_m"] == 1000.0
    others = {s["filename"]: s for s in t["other_sets"]}
    assert set(others) == {"plan.txt"} and others["plan.txt"]["used"] is False
    assert others["plan.txt"]["survey_status"] == "planned"
    assert any(x["code"] == "TRAJECTORY_PLANNED_ONLY" for x in others["plan.txt"]["reasons"])


def test_planned_only_is_not_drawn_and_no_survey_is_404(world: World) -> None:
    pid = world.project()
    world.add_doc(pid, "plan.txt", [_hdr(F5, "planned"), *_build(F5)])
    other = rec("production_day", _subj(*F6), [attr("x", "1", number=1.0)])
    world.add_doc(pid, "prod.xlsx", [other])
    r = _get(world, pid, _bore(world, pid, "15/9-F-5"))
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["details"]["code"] == "no_trajectory"
    assert "TRAJECTORY_PLANNED_ONLY" in err["details"]["sets"][0]["reasons"]
    r6 = _get(world, pid, _bore(world, pid, "15/9-F-6"))
    assert r6.status_code == 404 and r6.json()["error"]["details"]["code"] == "no_trajectory"


def test_invalid_stations_block_only_their_wellbore(world: World) -> None:
    pid = world.project()
    bad = [_st(F5, 0, 0, 0), _st(F5, 500, 10, 20, md_state="conflicting"), _st(F5, 900, 20, 20)]
    world.add_doc(pid, "bad.txt", [_hdr(F5, "as_built"), *bad, _hdr(F6, "as_built"), *_build(F6)])
    r5 = _get(world, pid, _bore(world, pid, "15/9-F-5"))
    assert r5.status_code == 404
    assert "TRAJECTORY_INVALID_STATIONS" in r5.json()["error"]["details"]["sets"][0]["reasons"]
    assert _get(world, pid, _bore(world, pid, "15/9-F-6")).status_code == 200


def test_missing_azimuth_reference_blocks_instead_of_assuming_north(world: World) -> None:
    pid = world.project()
    stations = [_st(F5, 0, 0, 0, azi_ref=None), _st(F5, 1000, 90, 90, azi_ref=None)]
    world.add_doc(pid, "noref.txt", stations)
    r = _get(world, pid, _bore(world, pid, "15/9-F-5"))
    assert r.status_code == 404
    assert r.json()["error"]["details"]["sets"][0]["reasons"] == ["AZIMUTH_REFERENCE_NOT_STATED"]


def test_feet_are_converted_and_first_station_off_wellhead_needs_tvd(world: World) -> None:
    pid = world.project()
    ft = [_st(F5, 0, 0, 0, unit="ft"), _st(F5, 1000.0 / 0.3048, 0, 0, unit="ft")]
    world.add_doc(pid, "ft.txt", [_hdr(F5, "as_built"), *ft])
    t = _get(world, pid, _bore(world, pid, "15/9-F-5")).json()
    assert t["md_unit"] == "ft"
    assert abs(t["md_max_m"] - 1000.0) < 1e-9 and abs(t["points"][-1]["tvd_m"] - 1000.0) < 1e-9
    world.add_doc(pid, "tie.txt", [_hdr(F6, "as_built"), _st(F6, 100, 0, 0), _st(F6, 200, 0, 0)])
    r = _get(world, pid, _bore(world, pid, "15/9-F-6"))
    assert r.status_code == 404
    assert r.json()["error"]["details"]["sets"][0]["reasons"] == ["WELLHEAD_START_UNKNOWN"]


def test_display_downsample_reports_counts_and_keeps_endpoints(world: World) -> None:
    pid = world.project()
    n = 1001
    stations = [_st(F5, 10.0 * i, 0.09 * i, 45.0) for i in range(n)]
    world.add_doc(pid, "big.txt", [_hdr(F5, "as_built"), *stations])
    t = _get(world, pid, _bore(world, pid, "15/9-F-5")).json()
    assert t["source_count"] == n and t["displayed_count"] == len(t["points"]) == 400
    assert t["points"][0]["md_m"] == 0.0 and abs(t["points"][-1]["md_m"] - 10000.0) < 1e-9
    assert t["md_max_m"] == 10000.0


def test_project_isolation_and_unknown_ids(world: World) -> None:
    a, b = world.project("A"), world.project("B")
    world.add_doc(a, "ssr.txt", [_hdr(F5, "as_built"), *_build(F5)])
    wb = _bore(world, a, "15/9-F-5")
    assert _get(world, a, wb).status_code == 200
    leak = _get(world, b, wb)
    assert leak.status_code == 404 and leak.json()["error"]["code"] == "NOT_FOUND"
    assert not leak.json()["error"].get("details")
    assert _get(world, str(uuid4()), wb).status_code == 404
    assert _get(world, a, str(uuid4())).status_code == 404

"""TASK-046 DC-1/DC-2: undocumented depth units default to meters (MD) as one warning per file;
a unit the source states always wins. Synthetic invented wells only."""

from __future__ import annotations

from pathlib import Path

from fieldlens.profiles import registry
from fieldlens.profiles.dat_tables import (
    MAX_DEFAULT_LOCATORS,
    PerforationTableProfile,
    PickTableProfile,
)
from fieldlens.profiles.witsml import WitsmlProfile
from tests.profile_support import CTX, station, witsml, write
from tests.test_profiles_sources import PERF_HEAD, PICKS, _perf_row


def _perf(tmp: Path, rows: int = 2) -> Path:
    text = PERF_HEAD + "".join(
        _perf_row(i + 1, i + 1, f"{4160 + i}.00", f"{4165 + i}.00", "2772.90", "2776.64", "")
        for i in range(rows)
    )
    return write(tmp, "perf.dat", text)


def test_depth_defaults_perforations(tmp_path: Path) -> None:
    out = PerforationTableProfile().parse(_perf(tmp_path), CTX)
    top = out.records[0].attr("perforation.top_md")
    assert top is not None
    assert top.original_text == "4160.00" and top.unit is None and top.unit_status == "missing"
    assert (top.normalized_number, top.normalized_unit) == (4160.0, "m")
    assert top.validation_state == "unreviewed"
    assert top.reference == "assumed MD (default)"
    tvd = out.records[0].attr("perforation.top_tvd")
    assert (
        tvd is not None and tvd.normalized_unit == "m" and tvd.reference == "assumed TVD (default)"
    )
    # coordinates are not depths: no default
    easting = out.records[0].attr("perforation.top_easting")
    assert easting is not None and easting.normalized_unit is None
    warnings = [f for f in out.findings if f.code == "MISSING_UNIT"]
    assert len(warnings) == 1
    w = warnings[0]
    assert w.severity == "warning" and w.blocked == []
    assert "assumed meters" in w.message and "measured depth" in w.message
    assert "reference unspecified" in w.message
    # 2 records x 4 depth attrs (top/base md and tvd; tvdss blank)
    assert "8 attribute(s) in 2 record(s)" in w.message
    assert 1 <= len(w.locators) <= MAX_DEFAULT_LOCATORS


def test_default_finding_locators_are_bounded(tmp_path: Path) -> None:
    out = PerforationTableProfile().parse(_perf(tmp_path, rows=30), CTX)
    (w,) = [f for f in out.findings if f.code == "MISSING_UNIT"]
    assert len(w.locators) == MAX_DEFAULT_LOCATORS and len(w.record_ordinals) == 30


def test_blank_depth_is_never_defaulted(tmp_path: Path) -> None:
    out = PerforationTableProfile().parse(_perf(tmp_path), CTX)
    base_tvdss = out.records[0].attr("perforation.base_tvdss")
    assert base_tvdss is not None
    assert base_tvdss.number is None and base_tvdss.normalized_number is None
    assert base_tvdss.normalized_unit is None and base_tvdss.unknown_reason


def test_depth_defaults_picks_and_flagged_picks_stay_unsupported(tmp_path: Path) -> None:
    out = PickTableProfile().parse(write(tmp_path, "picks.dat", PICKS), CTX)
    first, flagged = out.records
    md = first.attr("pick.md")
    assert md is not None and (md.normalized_number, md.normalized_unit) == (3100.10, "m")
    assert md.validation_state == "unreviewed" and md.reference == "assumed MD (default)"
    twt = first.attr("pick.twt")
    assert twt is not None and twt.normalized_unit is None, "two-way time is not a depth"
    # ER/FP-flagged picks are not formation tops: their depths stay unsupported, not defaulted.
    fmd = flagged.attr("pick.md")
    assert fmd is not None and fmd.validation_state == "unsupported"
    assert fmd.normalized_unit is None and fmd.normalized_number is None
    (w,) = [f for f in out.findings if f.code == "MISSING_UNIT"]
    assert w.severity == "warning" and "stay unsupported" in w.message
    assert "pick.md=1" in w.message


def test_stated_unit_wins_and_feet_convert_exactly(tmp_path: Path) -> None:
    body = (
        '<trajectoryStation uid="S-1"><typeTrajStation>MWD</typeTrajStation>'
        '<md uom="ft">1000</md><tvd uom="ft">900</tvd><incl uom="dega">5</incl>'
        '<azi uom="dega">120</azi></trajectoryStation>'
    )
    path = write(tmp_path, "t.xml", witsml("trajectorys", "trajectory", body))
    out = WitsmlProfile("trajectory").parse(path, CTX)
    stations = [r for r in out.records if r.kind == "trajectory_station"]
    md = stations[0].attr("trajectory_station.md")
    assert md is not None and md.unit == "ft" and md.original_text == "1000"
    assert md.unit_status == "stated" and md.normalized_unit == "m"
    assert md.normalized_number == 1000 * 0.3048
    # the same station in meters is untouched
    m_out = WitsmlProfile("trajectory").parse(
        write(
            tmp_path,
            "m.xml",
            witsml("trajectorys", "trajectory", station("S", "10", "9", "1", "2")),
        ),
        CTX,
    )
    mstation = next(r for r in m_out.records if r.kind == "trajectory_station")
    mmd = mstation.attr("trajectory_station.md")
    assert mmd is not None and mmd.unit == "m" and mmd.normalized_number == 10.0
    assert not [f for f in m_out.findings if f.code == "MISSING_UNIT"]


def test_profile_versions_bumped_so_runs_are_re_derived() -> None:
    assert registry.current_version("dat_perforations_volve") == "3"
    assert registry.current_version("dat_well_picks_volve") == "3"


def test_missing_reference_is_a_non_blocking_warning_for_defaulted_depths(tmp_path: Path) -> None:
    out = PerforationTableProfile().parse(_perf(tmp_path), CTX)
    refs = [f for f in out.findings if f.code == "MISSING_REFERENCE"]
    assert len(refs) == 1 and refs[0].severity == "warning" and refs[0].blocked == []
    assert "reference unspecified" in refs[0].message
    assert "assumed the well's depth reference" in refs[0].message
    # no depth could be used (all blank): genuinely unusable, still blocking
    blank = write(tmp_path, "blank.dat", PERF_HEAD + _perf_row(1, 1, "", "", "", "", ""))
    blank_out = PerforationTableProfile().parse(blank, CTX)
    (ref,) = [f for f in blank_out.findings if f.code == "MISSING_REFERENCE"]
    assert "placement" in ref.blocked

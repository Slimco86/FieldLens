"""Production workbook, LAS, fixed-width table and survey-report PDF profile tests (IN-2, IN-6).

Synthetic fixtures only: invented wells (F-99, F-A, F-B) and values; no Volve content."""

from __future__ import annotations

from pathlib import Path

import pytest

from fieldlens.profiles import registry
from fieldlens.profiles.dat_tables import PerforationTableProfile, PickTableProfile
from fieldlens.profiles.las import LasProfile
from fieldlens.profiles.pdf_survey import SurveyReportProfile
from fieldlens.profiles.production import ProductionWorkbookProfile
from fieldlens.profiles.types import ProfileError
from tests.profile_support import CTX, codes, text_pdf, write, xlsx_bytes

DAILY_HEAD = [
    "DATEPRD",
    "WELL_BORE_CODE",
    "NPD_WELL_BORE_NAME",
    "NPD_WELL_BORE_CODE",
    "ON_STREAM_HRS",
    "BORE_OIL_VOL",
    "BORE_GAS_VOL",
    "BORE_WAT_VOL",
    "BORE_WI_VOL",
    "FLOW_KIND",
    "WELL_TYPE",
]
MONTHLY_HEAD = ["Wellbore name", "NPDCode", "Year", "Month", "On Stream", "Oil", "Gas", "Water"]
MONTHLY_UNITS = [None, None, None, None, "Hrs", "Sm3", "Sm3", "Sm3"]


def _workbook(tmp: Path, daily: list[list[object]], monthly: list[list[object]]) -> Path:
    return write(
        tmp,
        "prod.xlsx",
        xlsx_bytes(
            {
                "Daily Production Data": [DAILY_HEAD, *daily],
                "Monthly Production Data": [MONTHLY_HEAD, MONTHLY_UNITS, *monthly],
            }
        ),
    )


def _day(serial: int, bore: str, code: int, oil: object, hours: object = 24) -> list[object]:
    return [
        ("date", serial),
        f"NO {bore}",
        bore,
        code,
        hours,
        oil,
        "NULL",
        None,
        None,
        "production",
        "OP",
    ]


# -- production ------------------------------------------------------------------------------


def test_production_scopes_rows_to_their_own_wellbore_and_never_zero_fills(tmp_path: Path) -> None:
    path = _workbook(
        tmp_path,
        [_day(40000, "15/9-F-A", 1, 100.5), _day(40000, "15/9-F-B", 2, "NULL")],
        [],
    )
    out = ProductionWorkbookProfile().parse(path, CTX)
    days = [r for r in out.records if r.kind == "production_day"]
    assert {r.subject["wellbore_label"] for r in days} == {"NO 15/9-F-A", "NO 15/9-F-B"}
    a = next(r for r in days if r.subject["npd_wellbore_code"] == "1")
    b = next(r for r in days if r.subject["npd_wellbore_code"] == "2")
    oil_a, oil_b = a.attr("production_day.bore_oil_vol"), b.attr("production_day.bore_oil_vol")
    assert oil_a is not None and oil_a.number == 100.5
    assert oil_b is not None and oil_b.number is None, "NULL is unknown, never zero"
    assert oil_b.unknown_reason and oil_b.original_text == "NULL"
    gas = a.attr("production_day.bore_gas_vol")
    assert gas is not None and gas.number is None
    # Daily sheet states no unit: none is assumed and the gap is a finding.
    assert oil_a.unit is None and oil_a.unit_status == "missing"
    assert "MISSING_UNIT" in codes(out)


def test_production_date_precision_locator_and_source_cell(tmp_path: Path) -> None:
    out = ProductionWorkbookProfile().parse(
        _workbook(tmp_path, [_day(40000, "15/9-F-A", 1, 1.0)], []), CTX
    )
    rec = out.records[0]
    assert rec.effective_time is not None
    assert (rec.effective_time.literal, rec.effective_time.precision) == ("2009-07-06", "day")
    assert rec.effective_time.timezone_known is False
    oil = rec.attr("production_day.bore_oil_vol")
    assert oil is not None
    assert oil.locator == {"kind": "xlsx", "sheet": "Daily Production Data", "cell_range": "F2"}
    assert oil.original_text == "1.0"


def test_production_monthly_units_come_from_the_unit_row_and_flag_conflicts(tmp_path: Path) -> None:
    # July 2009 daily oil sums to 100.5 but the monthly sheet says 3000 Sm3: reported, kept.
    path = _workbook(
        tmp_path,
        [_day(40000, "15/9-F-A", 1, 100.5)],
        [["F-A", 1, 2009, 7, 700, 3000, 10, 5]],
    )
    out = ProductionWorkbookProfile().parse(path, CTX)
    month = next(r for r in out.records if r.kind == "production_month")
    oil = month.attr("production_month.oil")
    assert oil is not None and (oil.number, oil.unit) == (3000.0, "Sm3")
    assert month.effective_time is not None and month.effective_time.precision == "month"
    assert "REFERENCE_CONFLICT" in codes(out)
    assert oil.validation_state == "conflicting"


def test_production_negative_and_over_24h_are_flagged_not_fixed(tmp_path: Path) -> None:
    out = ProductionWorkbookProfile().parse(
        _workbook(tmp_path, [_day(40001, "15/9-F-B", 2, -5, hours=30)], []), CTX
    )
    assert "SUSPICIOUS_VALUE" in codes(out)
    oil = out.records[0].attr("production_day.bore_oil_vol")
    assert oil is not None and oil.number == -5.0


def test_production_detection_is_content_based_and_rejects_other_workbooks(tmp_path: Path) -> None:
    good = _workbook(tmp_path, [_day(40000, "15/9-F-A", 1, 1.0)], [])
    assert [p.name for p in registry.detect(good, "xlsx", "anything.xlsx")] == [
        "production_workbook_volve"
    ]
    other = write(tmp_path, "o.xlsx", xlsx_bytes({"Sheet1": [["a", "b"], [1, 2]]}))
    assert registry.detect(other, "xlsx", "Volve production data.xlsx") == []


def test_corrupt_workbook_is_a_clean_profile_error(tmp_path: Path) -> None:
    with pytest.raises(ProfileError):
        ProductionWorkbookProfile().parse(write(tmp_path, "bad.xlsx", b"not a zip"), CTX)


# -- LAS -------------------------------------------------------------------------------------

LAS = """~VERSION INFORMATION
 VERS.   2.0 : CWLS LOG ASCII STANDARD - VERSION 2.0
 WRAP.   NO  : ONE LINE PER DEPTH STEP
~WELL INFORMATION
 STRT.M   100.0 : START DEPTH
 STOP.M   102.0 : STOP DEPTH
 STEP.M   1.0 : STEP
 NULL.    -999.25 : NULL VALUE
 WELL.    15/9-F-99 : WELL
 DATE.    : LOG DATE
~CURVE INFORMATION
 DEPT.M    : DEPTH
 GR  .GAPI : GAMMA
 RHOB.----   : DENSITY
~A
 100.0 50.0 2.40
 101.0 -999.25 2.41
 102.0 55.5 2.42
"""


def test_las_header_curves_nulls_and_missing_units(tmp_path: Path) -> None:
    path = write(tmp_path, "a.las", LAS)
    assert [p.name for p in registry.detect(path, "las", "x.txt")] == ["las_2_0"]
    out = LasProfile().parse(path, CTX)
    assert out.status == "succeeded" and out.coverage.complete
    gr = next(
        r
        for r in out.records
        if r.subject.get("mnemonic") == "GR" or r.locator.get("las_mnemonic") == "GR"
    )
    assert gr.attr("las_curve.valid_count").number == 2.0  # type: ignore[union-attr]
    assert gr.attr("las_curve.null_count").number == 1.0  # type: ignore[union-attr]
    assert gr.locator["kind"] == "text" and gr.locator["las_section"] == "curve"
    rhob = next(r for r in out.records if r.locator.get("las_mnemonic") == "RHOB")
    assert rhob.attr("las_curve.unit").unknown_reason  # type: ignore[union-attr]
    got = codes(out)
    assert {"MISSING_UNIT", "MISSING_REFERENCE", "TEMPORAL_AMBIGUITY"} <= got
    header = out.records[0]
    assert header.attr("las_header.null").number == -999.25  # type: ignore[union-attr]
    assert header.attr("las_header.well.date").unknown_reason  # type: ignore[union-attr]


def test_las_truncated_data_is_partial_with_missing_lines(tmp_path: Path) -> None:
    bad = LAS.replace(" 101.0 -999.25 2.41\n", " 101.0 -999.25\n")
    out = LasProfile().parse(write(tmp_path, "b.las", bad), CTX)
    assert out.status == "partial"
    assert not out.coverage.complete
    assert "EXTRACTION_PARTIAL" in codes(out)


def test_las_without_version_section_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ProfileError):
        LasProfile().parse(write(tmp_path, "c.las", "~W\n STRT.M 1 : x\n"), CTX)


# -- fixed-width tables ----------------------------------------------------------------------

PERF_HEAD = (
    "Row      Well name                 Top formation                  Perf obs#      "
    "Compl obs#     Top MD         Base MD        Top TVD        Base TVD       Perf date\n"
)


def _perf_row(n: int, po: int, tm: str, bm: str, tt: str, bt: str, date: str) -> str:
    return (
        f"{n:<9}{'NO 15/9-F-99':<26}{'Hugin Fm.':<31}{po:<15}{1:<15}"
        f"{tm:<15}{bm:<15}{tt:<15}{bt:<15}{date}\n"
    )


def test_perforation_intervals_keep_md_and_tvd_dates_and_gaps(tmp_path: Path) -> None:
    text = (
        PERF_HEAD
        + _perf_row(1, 1, "4160.00", "4165.00", "2772.90", "2776.64", "2010-05-03")
        + _perf_row(2, 2, "4157.00", "4159.00", "2770.66", "2772.15", "")
    )
    path = write(tmp_path, "perf.dat", text)
    assert [p.name for p in registry.detect(path, "csv", "whatever.txt")] == [
        "dat_perforations_volve"
    ]
    out = PerforationTableProfile().parse(path, CTX)
    first, second = out.records
    assert first.kind == "perforation_interval"
    top, base = first.attr("perforation.top_md"), first.attr("perforation.base_md")
    assert top is not None and base is not None
    assert (top.number, base.number) == (4160.0, 4165.0)
    assert first.attr("perforation.top_tvd").number == 2772.90  # type: ignore[union-attr]
    assert top.unit is None and top.unit_status == "missing", "no unit is assumed"
    assert top.locator["kind"] == "text" and top.locator["line_start"] == 2
    assert first.effective_time is not None and first.effective_time.precision == "day"
    assert second.effective_time is None
    assert {"MISSING_UNIT", "MISSING_REFERENCE", "TEMPORAL_AMBIGUITY"} <= codes(out)


PICKS = """# Qlf column
# ER: Eroded
# FP: Faulted pick

Well NO 15/9-F-99

  Well name                Surface name                             Obs#  Qlf MD       TVD      TVDSS    TWT      Dip    Azi    Easting   Northing  Intrp
  ------------------------ ---------------------------------------- ----- --- -------- -------- -------- -------- ------ ------ --------- --------- -----
  NO 15/9-F-99             Hugin Fm. Top                            1         3100.10  2900.00                                                       STAT
  NO 15/9-F-99             Skagerrak Fm. Top                        2     FP  3200.00                                                               STAT
"""


def test_well_picks_keep_qualifiers_and_never_invent_missing_depths(tmp_path: Path) -> None:
    path = write(tmp_path, "picks.dat", PICKS)
    assert [p.name for p in registry.detect(path, "csv", "x.dat")] == ["dat_well_picks_volve"]
    out = PickTableProfile().parse(path, CTX)
    first, second = out.records
    assert first.attr("pick.md").number == 3100.10  # type: ignore[union-attr]
    assert first.attr("pick.tvd").number == 2900.0  # type: ignore[union-attr]
    assert second.attr("pick.qualifier").text == "FP"  # type: ignore[union-attr]
    tvd = second.attr("pick.tvd")
    assert tvd is not None and tvd.number is None and tvd.unknown_reason == "blank in source"
    assert {"MISSING_UNIT", "MISSING_REFERENCE", "HISTORY_INCOMPLETE"} <= codes(out)


# -- survey-report PDF -----------------------------------------------------------------------

SURVEY_PAGE = [
    "Standard Survey Report",
    "Company:   Synthetic Co",
    "Site:   F-99 Pad",
    "Well:   15/9-F-99",
    "Wellbore:   15/9-F-99 Main",
    "Design:   Actual",
    "TVD Reference:   Rotary Table @ 54.90m (Synthetic)",
    "MD Reference:   Rotary Table @ 54.90m (Synthetic)",
    "North Reference:   Grid",
    "Survey Calculation Method:   Minimum Curvature",
    "Map System:   Universal Transverse Mercator (UTM)",
    "Geo Datum:   ED50",
    "Map Zone:   Zone 31N",
    "System Datum:   Mean Sea Level",
    "Survey",
    " 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00 0.00",
    " 100.00 5.00 120.00 99.80 -2.00 3.00 1.00 1.50 1.50 0.00",
    " 200.00 6.00 121.00 199.50 -4.00 6.00 2.00 1.50 1.50 0.00",
]


def test_survey_pdf_extracts_stations_with_page_locators_and_references(tmp_path: Path) -> None:
    path = write(tmp_path, "s.pdf", text_pdf([SURVEY_PAGE]))
    assert [p.name for p in registry.detect(path, "pdf", "anything.pdf")] == [
        "pdf_compass_survey_report"
    ]
    out = SurveyReportProfile().parse(path, CTX)
    assert out.status == "succeeded"
    assert (out.coverage.unit, out.coverage.inspected, out.coverage.total) == ("page", 1, 1)
    stations = [r for r in out.records if r.kind == "trajectory_station"]
    assert len(stations) == 3
    md, tvd = stations[1].attr("trajectory_station.md"), stations[1].attr("trajectory_station.tvd")
    assert md is not None and tvd is not None
    assert (md.number, md.unit, tvd.number) == (100.0, "m", 99.8)
    assert md.reference and "54.90" in md.reference, "depth reference travels with the value"
    assert md.locator["kind"] == "pdf" and md.locator["page"] == 1
    assert md.locator["cell_id"].startswith("r2c")
    assert "TEMPORAL_AMBIGUITY" in codes(out), "survey stations carry no acquisition time"


def test_survey_pdf_conflicting_tvd_and_md_references_are_reported(tmp_path: Path) -> None:
    page = [
        ln.replace("MD Reference:   Rotary Table @ 54.90m", "MD Reference:   Rotary Table @ 53.87m")
        for ln in SURVEY_PAGE
    ]
    out = SurveyReportProfile().parse(write(tmp_path, "s2.pdf", text_pdf([page])), CTX)
    conflict = [f for f in out.findings if f.code == "REFERENCE_CONFLICT"]
    assert conflict and "placement" in conflict[0].blocked


def test_pdf_without_report_header_is_refused_and_not_selected(tmp_path: Path) -> None:
    path = write(tmp_path, "n.pdf", text_pdf([["Just a letter", "nothing else"]]))
    assert registry.detect(path, "pdf", "Standard Survey Report.pdf") == []
    with pytest.raises(ProfileError):
        SurveyReportProfile().parse(path, CTX)

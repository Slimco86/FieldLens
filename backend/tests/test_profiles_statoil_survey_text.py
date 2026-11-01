"""Statoil-default survey export TEXT profile (IN-11, TASK-051).

The layout is derived from the real Volve ``..._ACTUAL`` / ``..._PLAN`` exports (CRLF, cp1252 degree
sign in the latitude/longitude lines); every value here is synthetic (well F-99). No Volve data."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.engine import URL

from fieldlens.ingestion.inspect import inspect_file
from fieldlens.profiles import registry
from fieldlens.profiles.compass_text import CompassTextProfile, sniff_compass_text
from fieldlens.profiles.statoil_survey_text import StatoilSurveyTextProfile
from fieldlens.profiles.types import ProfileError, ProfileOutput
from fieldlens.textenc import sniff_path
from tests.jobs.test_extraction_flow import _drain, _ingest, _report
from tests.profile_support import CTX, codes, write
from tests.test_profiles_compass_text import report as compass_report
from tests.test_profiles_sources import LAS, PICKS
from tests.upload_support import make_api

DASH = "-" * 64
TITLES = (
    "MD        Inc       Azim      TVD       X-Offset (E/W)  Y-Offset (N/S)  "
    "UTM E/W         UTM N/S         DLS"
)
UNITS = (
    "m RKB     deg       deg       m RKB     m               m               "
    "m               m               deg/30m"
)


def row(*cells: str) -> str:
    """Fixed-width station row like the export (columns at 0,10,20,30,40,56,72,88,104)."""
    widths = (10, 10, 10, 10, 16, 16, 16, 16, 10)
    return "".join(c.ljust(w) for c, w in zip(cells, widths, strict=True))


ROWS = [
    row("100.00", "0.00", "0.00", "100.00", "0.100", "2.000", "500000.100", "6500000.000", "0.00"),
    row("130.00", "1.50", "90.00", "129.99", "0.200", "2.000", "500000.200", "6500000.000", "1.50"),
    row("160.00", "3.00", "91.00", "159.95", "0.900", "2.010", "500000.900", "6500000.010", "1.50"),
]


def export(
    *,
    rows: list[str] | None = None,
    units: str | None = UNITS,
    drop: tuple[str, ...] = (),
    replace: dict[str, str] | None = None,
    after_rows: list[str] | None = None,
) -> str:
    head = [
        "HEADER INFORMATION (all units in Statoil default) ",
        DASH,
        "COMPANY: Statoil Norway",
        "FIELD: SLEIPNER",
        "WELL NAME: F-99",
        "WELLBORE NAME: F-99",
        "Drilled From: Well Ref. Point",
        "Kick Off Depth: 100.00m",
        "Survey Name: F-99",
        "Survey Date: 21.11.2007",
        "Extraction Date: 26.03.2018",
        DASH,
        "Calculation Method: Minimum Curvature",
        "Datum Name: Rotary Table(50.00m)",
        DASH,
        "Surface EW: 500000.100m",
        "Surface NS: 6500000.000m",
        "Surface Latitude: 58° 26' 29.8941 N",
        "Surface Longitude: 1° 53' 14.9374 E",
        "Bottom Hole MD: 160.00m",
        "Bottom Hole TVD: 159.95m",
        "Bottom Hole EW: 500000.900m",
        "Bottom Hole NS: 6500000.010m",
        DASH,
        "Survey Program:  ",
        'H  100 - 160 14" CASING GYRO SURVEY : OLD_WELLBORE SURVEYOR, CONT',
        DASH,
        "Water Depth: 91.00m",
        "KB-WH: 141.00m",
        "KB-MSL: 50.00m",
        "System Datum: Mean Sea Level",
        DASH,
        "Map-Zone: Zone 31N (0 E to 6 E)",
        "North Reference: Grid",
        "Geo Datum: European 1950 - Mean",
        "Vertical Section Direction: 104.32deg",
        DASH,
        "SURVEY LIST",
        TITLES,
    ]
    head = [ln for ln in head if not ln.startswith(drop)] if drop else head
    body = [*([units] if units else []), *(ROWS if rows is None else rows), *(after_rows or [])]
    text = "\n".join(head + body) + "\n"
    for old, new in (replace or {}).items():
        assert old in text, old
        text = text.replace(old, new)
    return text


def as_file(text: str) -> bytes:
    return text.replace("\n", "\r\n").encode("cp1252")


def parse(
    tmp: Path, text: str | bytes, name: str = "Volve F_F-99_F-99_F-99_ACTUAL"
) -> ProfileOutput:
    data = as_file(text) if isinstance(text, str) else text
    path = write(tmp, name, data)
    assert [p.name for p in registry.detect(path, "text", name)] == ["text_statoil_survey_export"]
    return StatoilSurveyTextProfile().parse(path, CTX)


def stations(out: ProfileOutput) -> list:
    return [r for r in out.records if r.kind == "trajectory_station"]


def finding(out: ProfileOutput, key: str):
    return next((f for f in out.findings if f.key == key), None)


def test_normal_export_extracts_stations_header_program_and_surface_location(
    tmp_path: Path,
) -> None:
    out = parse(tmp_path, export())
    assert out.status == "succeeded", out.coverage
    assert out.detail["text_encoding"] == "cp1252" and out.detail["stations"] == 3
    assert sniff_path(tmp_path / "Volve F_F-99_F-99_F-99_ACTUAL") == "cp1252"
    assert [r.kind for r in out.records[:2]] == ["survey_report_header", "well_surface_location"]
    st = stations(out)
    md, tvd, azi, ue, dls = (
        st[1].attr(f"trajectory_station.{k}") for k in ("md", "tvd", "azi", "utmEasting", "dls")
    )
    assert md and tvd and azi and ue and dls
    assert (md.number, md.unit, md.original_text) == (130.0, "m", "130.00")
    assert md.reference == "RKB (Datum Name: Rotary Table(50.00m))" == tvd.reference
    assert azi.unit == "deg" and azi.reference == "grid north"
    assert (ue.number, ue.unit) == (500000.2, "m") and ue.reference
    assert "Zone 31N" in ue.reference and "European 1950" in ue.reference
    assert (dls.number, dls.unit) == (1.5, "deg/30m")
    line = next(i for i, ln in enumerate(export().splitlines(), 1) if ln.startswith("130.00"))
    assert md.locator == {
        "kind": "text",
        "line_start": line,
        "line_end": line,
        "logical_record": 2,
        "column_name": "md",
    }
    assert st[0].attr("trajectory_station.dispEw").number == 0.1  # type: ignore[union-attr]
    assert st[0].attr("trajectory_station.dispNs").number == 2.0  # type: ignore[union-attr]
    hdr = out.records[0]
    get = hdr.attr
    assert hdr.subject["well_name"] == "F-99" and hdr.subject["wellbore_name"] == "F-99"
    assert get("survey_report_header.calculation_method").text == "Minimum Curvature"  # type: ignore[union-attr]
    assert get("survey_report_header.geo_datum").text == "European 1950 - Mean"  # type: ignore[union-attr]
    assert get("survey_report_header.map_zone").text == "Zone 31N (0 E to 6 E)"  # type: ignore[union-attr]
    assert get("survey_report_header.system_datum").text == "Mean Sea Level"  # type: ignore[union-attr]
    assert get("survey_report_header.north_reference").text == "Grid"  # type: ignore[union-attr]
    elev = get("survey_report_header.reference_elevation")
    assert elev is not None and (elev.number, elev.unit) == (50.0, "m")
    vsd = get("survey_report_header.vertical_section_direction")
    assert vsd is not None and (vsd.number, vsd.unit, vsd.original_text) == (
        104.32,
        "deg",
        "104.32deg",
    )
    for key, value in (("water_depth", 91.0), ("kb_wh", 141.0), ("kb_msl", 50.0)):
        a = get(f"survey_report_header.{key}")
        assert a is not None and (a.number, a.unit) == (value, "m"), key
    for key, value in (("bottom_hole_md", 160.0), ("bottom_hole_ew", 500000.9)):
        a = get(f"survey_report_header.{key}")
        assert a is not None and a.number == value
    kod = get("survey_report_header.kick_off_depth")
    assert kod is not None and kod.original_text == "100.00m"
    # extraction date is report time; the survey date is the effective (day) time, never merged
    assert hdr.effective_time and hdr.effective_time.literal == "2007-11-21"
    assert hdr.effective_time.precision == "day" and hdr.effective_time.field == "Survey Date"
    assert hdr.report_time and hdr.report_time.literal == "2018-03-26"
    assert st[0].effective_time is None and st[0].report_time == hdr.report_time
    prog = [r for r in out.records if r.kind == "survey_program_entry"]
    assert len(prog) == 1
    assert prog[0].attr("survey_program_entry.from_md").number == 100.0  # type: ignore[union-attr]
    assert prog[0].attr("survey_program_entry.to_md").number == 160.0  # type: ignore[union-attr]
    assert prog[0].attr("survey_program_entry.survey_name").text == '14" CASING GYRO SURVEY'  # type: ignore[union-attr]
    assert not any(f.severity in ("warning", "error") for f in out.findings), out.findings
    # surface location: UTM with units, lat/long verbatim (degree sign decoded) + decimal value
    loc = out.records[1]
    assert loc.kind == "well_surface_location" and loc.subject == hdr.subject
    e, n = (loc.attr(f"well_surface_location.{k}") for k in ("easting", "northing"))
    assert e and n and (e.number, e.unit, n.number, n.unit) == (500000.1, "m", 6500000.0, "m")
    assert e.original_text == "500000.100m" and "Zone 31N" in (e.reference or "")
    lat, lon = (loc.attr(f"well_surface_location.{k}") for k in ("latitude", "longitude"))
    assert lat and lon
    assert lat.original_text == "58° 26' 29.8941 N" and lon.original_text == "1° 53' 14.9374 E"
    assert lat.normalized_number == pytest.approx(58 + 26 / 60 + 29.8941 / 3600)
    assert lon.normalized_number == pytest.approx(1 + 53 / 60 + 14.9374 / 3600)
    assert loc.attr("well_surface_location.geo_datum").text == "European 1950 - Mean"  # type: ignore[union-attr]
    # cheap cross-checks pass silently; the CRS is left unresolved (info, no EPSG guess)
    assert not any(f.key.startswith("check:") for f in out.findings)
    assert finding(out, "surface_crs_not_resolved").severity == "info"  # type: ignore[union-attr]


def test_survey_status_is_unstated_and_never_taken_from_the_filename(tmp_path: Path) -> None:
    plan_named = parse(tmp_path, export(), "Volve F_F-99_F-99_F99 Rev1_PLAN")
    status = plan_named.records[0].attr("survey_report_header.survey_status")
    assert status and status.text is None and status.unknown_reason
    assert status.original_text == "F-99"
    f = finding(plan_named, "survey_status_unstated")
    assert f and f.code == "TEMPORAL_AMBIGUITY" and "temporal_state" in f.blocked
    named = parse(tmp_path, export(replace={"Survey Name: F-99": "Survey Name: F99 Plan 3"}))
    st = named.records[0].attr("survey_report_header.survey_status")
    assert st and st.text == "planned" and st.original_text == "F99 Plan 3"
    assert finding(named, "survey_status_unstated") is None


def test_ambiguous_survey_date_keeps_unknown_precision(tmp_path: Path) -> None:
    out = parse(
        tmp_path,
        export(
            replace={
                "Survey Date: 21.11.2007": "Survey Date: 05.08.2008",
                "Extraction Date: 26.03.2018": "Extraction Date: 03.04.2018",
            }
        ),
    )
    assert out.records[0].effective_time.precision == "unknown"  # type: ignore[union-attr]
    assert finding(out, "survey_date_ambiguous") is not None


def test_missing_units_row_warns_and_never_assumes_units_or_reference(tmp_path: Path) -> None:
    out = parse(tmp_path, export(units=None))
    assert out.status == "succeeded" and len(stations(out)) == 3
    md = stations(out)[0].attr("trajectory_station.md")
    assert md and md.unit is None and md.reference is None and md.unit_status == "missing"
    assert {"MISSING_UNIT", "MISSING_REFERENCE"} <= codes(out)
    assert finding(out, "missing:station_units") and finding(out, "missing:md_tvd_reference")


def test_missing_surface_location_is_a_warning_and_no_location_record(tmp_path: Path) -> None:
    out = parse(tmp_path, export(drop=("Surface ",)))
    assert not [r for r in out.records if r.kind == "well_surface_location"]
    f = finding(out, "missing:surface_location")
    assert f and f.severity == "warning" and "placement" in f.blocked
    assert out.detail["has_surface_location"] is False
    assert len(stations(out)) == 3


def test_partial_surface_location_keeps_unknown_parts_and_warns(tmp_path: Path) -> None:
    out = parse(tmp_path, export(drop=("Surface NS", "Surface Longitude")))
    loc = next(r for r in out.records if r.kind == "well_surface_location")
    n = loc.attr("well_surface_location.northing")
    assert n and n.number is None and n.unknown_reason
    assert loc.attr("well_surface_location.longitude") is None
    assert finding(out, "surface_location_incomplete")


def test_undecodable_latitude_is_unknown_and_flagged(tmp_path: Path) -> None:
    out = parse(tmp_path, export(replace={"58° 26' 29.8941 N": "58° 86' 29.8941 N"}))
    lat = next(r for r in out.records if r.kind == "well_surface_location").attr(
        "well_surface_location.latitude"
    )
    assert lat and lat.normalized_number is None and lat.original_text == "58° 86' 29.8941 N"
    assert finding(out, "surface_latitude_undecoded")


def test_missing_datum_name_warns_and_keeps_reference_from_units_row(tmp_path: Path) -> None:
    out = parse(tmp_path, export(drop=("Datum Name",)))
    md = stations(out)[0].attr("trajectory_station.md")
    assert md and md.reference == "RKB" and md.unit == "m"
    assert finding(out, "missing:datum_name")
    assert out.records[0].attr("survey_report_header.reference_elevation") is None


def test_row_with_eight_or_ten_fields_is_not_guessed_and_partial(tmp_path: Path) -> None:
    eight = "130.00    1.50      90.00     129.99    0.200   2.000   500000.200   6500000.000"
    ten = ROWS[1] + "      9.99"
    out = parse(tmp_path, export(rows=[ROWS[0], eight, ten, ROWS[2]]))
    assert len(stations(out)) == 2
    assert [r.locator["logical_record"] for r in stations(out)] == [1, 2]
    assert out.status == "partial" and out.detail["skipped_rows"] == 2
    f = finding(out, "text_rows_skipped")
    assert f and f.severity == "warning" and len(f.locators) == 2
    assert out.coverage.missing_ranges and not out.coverage.complete


def test_blank_field_in_a_fixed_width_row_stays_unknown(tmp_path: Path) -> None:
    blank = row(
        "130.00", "1.50", "", "129.99", "0.200", "2.000", "500000.200", "6500000.000", "1.50"
    )
    out = parse(tmp_path, export(rows=[ROWS[0], blank, ROWS[2]]))
    azi = stations(out)[1].attr("trajectory_station.azi")
    assert azi and azi.number is None and azi.unknown_reason == "empty in source"
    assert stations(out)[1].attr("trajectory_station.incl").number == 1.5  # type: ignore[union-attr]
    assert stations(out)[1].attr("trajectory_station.tvd").number == 129.99  # type: ignore[union-attr]
    assert finding(out, "station_values_unknown")


def test_decimal_comma_is_not_guessed(tmp_path: Path) -> None:
    comma = ROWS[1].replace("129.99", "129,99")
    out = parse(tmp_path, export(rows=[ROWS[0], comma, ROWS[2]]))
    tvd = stations(out)[1].attr("trajectory_station.tvd")
    assert tvd and tvd.number is None and "comma" in (tvd.unknown_reason or "")
    assert tvd.original_text == "129,99"


def test_repeated_survey_list_section_is_not_merged_and_partial(tmp_path: Path) -> None:
    out = parse(tmp_path, export(after_rows=["SURVEY LIST", TITLES, UNITS, *ROWS]))
    assert len(stations(out)) == 3 and out.status == "partial"
    f = finding(out, "text_rows_skipped")
    assert f and "repeated" in f.message
    assert out.detail["skipped_rows"] == 4  # the repeated title plus its three rows


def test_wrong_column_order_or_missing_titles_are_refused(tmp_path: Path) -> None:
    swapped = TITLES.replace("Inc       Azim", "Azim      Inc ")
    path = write(tmp_path, "swapped", as_file(export(replace={TITLES: swapped})))
    assert [p.name for p in registry.detect(path, "text", "swapped")] == [
        "text_statoil_survey_export"
    ]
    with pytest.raises(ProfileError, match="order"):
        StatoilSurveyTextProfile().parse(path, CTX)
    gone = write(tmp_path, "gone", as_file(export(replace={TITLES: "Some other header"})))
    with pytest.raises(ProfileError, match="not recognized"):
        StatoilSurveyTextProfile().parse(gone, CTX)


def test_cross_check_findings(tmp_path: Path) -> None:
    out = parse(
        tmp_path,
        export(
            replace={
                "Bottom Hole TVD: 159.95m": "Bottom Hole TVD: 160.95m",
                "Surface EW: 500000.100m": "Surface EW: 500001.100m",
                "Kick Off Depth: 100.00m": "Kick Off Depth: 101.00m",
                "KB-MSL: 50.00m": "KB-MSL: 54.90m",
                "H  100 - 160": "H  120 - 140",
            }
        ),
    )
    keys = {f.key for f in out.findings if f.key.startswith("check:")}
    assert keys == {
        "check:first_station_vs_surface",
        "check:last_station_vs_bottom_hole",
        "check:kick_off_vs_first_station",
        "check:datum_vs_kb_msl",
        "check:md_range_vs_program",
    }
    assert finding(out, "check:datum_vs_kb_msl").severity == "error"  # type: ignore[union-attr]


def test_tvd_greater_than_md_and_non_increasing_md_are_reported(tmp_path: Path) -> None:
    bad = ROWS[2].replace("159.95", "165.00").replace("160.00", "120.00")
    out = parse(tmp_path, export(rows=[ROWS[0], ROWS[1], bad]))
    assert finding(out, "survey_tvd_gt_md") and finding(out, "survey_md_not_increasing")
    assert stations(out)[2].attr("trajectory_station.tvd").validation_state == "invalid"  # type: ignore[union-attr]


def test_conflicting_repeated_header_value_is_an_error(tmp_path: Path) -> None:
    out = parse(
        tmp_path, export(replace={"Calculation Method: Minimum Curvature": "Geo Datum: ED50"})
    )
    f = finding(out, "header_conflict:geo datum")
    assert f and f.severity == "error" and f.code == "REFERENCE_CONFLICT"


# ---- selection: never hijack, never hijacked -------------------------------------------------


def test_compass_profile_declines_this_layout_and_this_profile_declines_compass(
    tmp_path: Path,
) -> None:
    statoil = write(tmp_path, "statoil", as_file(export()))
    assert not sniff_compass_text(export().splitlines())
    assert CompassTextProfile().detect(statoil, "text", "statoil") is False
    with pytest.raises(ProfileError):
        CompassTextProfile().parse(statoil, CTX)
    compass = write(tmp_path, "compass", compass_report())
    assert StatoilSurveyTextProfile().detect(compass, "text", "compass") is False
    with pytest.raises(ProfileError):
        StatoilSurveyTextProfile().parse(compass, CTX)
    assert [p.name for p in registry.detect(compass, "text", "compass")] == [
        "text_compass_survey_report"
    ]


@pytest.mark.parametrize(
    "text",
    [
        "HEADER INFORMATION (all units in Statoil default)\nWELL NAME: F-99\n",  # header only
        "SURVEY LIST\n" + ROWS[0] + "\n",  # no export title
        "HEADER INFORMATION (all units in Statoil default)\nSURVEY LIST\n" + TITLES + "\n",
        "HEADER INFORMATION (all units in Statoil default)\nSURVEY LIST\n1.0 2.0 3.0\n",
    ],
)
def test_incomplete_export_text_declines(tmp_path: Path, text: str) -> None:
    path = write(tmp_path, "other", text)
    assert registry.detect(path, "text", "other") == []


def test_las_dat_and_csv_are_not_hijacked(tmp_path: Path) -> None:
    las = write(tmp_path, "x.las", LAS)
    dat = write(tmp_path, "x.dat", PICKS)
    csv = write(tmp_path, "x.csv", "MD,INC,AZI\n100.0,1.0,2.0\n")
    for path, family in ((las, "las"), (dat, "csv"), (csv, "csv")):
        names = [p.name for p in registry.detect(path, family, path.name)]
        assert "text_statoil_survey_export" not in names
        assert not StatoilSurveyTextProfile().detect(path, family, path.name)
    # even an export-looking body inside a family the profile does not serve is ignored
    statoil = write(tmp_path, "statoil.las", as_file(export()))
    assert "text_statoil_survey_export" not in [
        p.name for p in registry.detect(statoil, "las", "statoil.las")
    ]


def test_intake_marks_the_layout_pending_extraction_and_ignores_the_filename(
    tmp_path: Path,
) -> None:
    for name in ("Volve F_F-99_ACTUAL", "notes.txt", "survey.dat"):
        path = write(tmp_path, name, as_file(export()))
        det = inspect_file(path, name, max_file_bytes=10**9, remaining_batch_bytes=10**9)
        assert (det.format_family, det.extraction_state) == ("text", "pending_extraction")
        assert det.encoding == "cp1252"
    other = write(tmp_path, "plain", "just some text\n")
    det = inspect_file(other, "plain", max_file_bytes=10**9, remaining_batch_bytes=10**9)
    assert det.extraction_state == "unsupported"


def test_extensionless_upload_yields_stations_and_a_surface_location(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("Volve F_F-99_F-99_F-99_ACTUAL", as_file(export()))])
    doc = docs[0]
    assert doc["format_family"] == "text"
    assert doc["origin_metadata"]["text_encoding"] == "cp1252"
    assert doc["extraction_state"] == "pending_extraction"
    did = str(doc["document_id"])
    _drain(api)
    rep = _report(api, pid, did)
    assert rep["profile_name"] == "text_statoil_survey_export"
    assert rep["status"] == "succeeded"
    base = f"/api/v1/projects/{pid}/documents/{did}/extraction/records"
    recs = api.client.get(f"{base}?kind=trajectory_station").json()
    assert recs["total"] == 3
    md = next(a for a in recs["items"][1]["attributes"] if a["key"].endswith(".md"))
    assert md["evidence"]["locator"]["kind"] == "text"
    assert (md["original_text"], md["unit"], md["number"]) == ("130.00", "m", 130.0)
    assert md["reference"] and "50.00" in md["reference"]
    locs = api.client.get(f"{base}?kind=well_surface_location").json()
    assert locs["total"] == 1
    attrs = {a["key"]: a for a in locs["items"][0]["attributes"]}
    assert attrs["well_surface_location.easting"]["number"] == 500000.1
    assert attrs["well_surface_location.northing"]["unit"] == "m"
    assert attrs["well_surface_location.latitude"]["original_text"] == "58° 26' 29.8941 N"
    assert attrs["well_surface_location.longitude"]["evidence"]["locator"]["kind"] == "text"
    assert api.documents(pid)[0]["extraction_state"] in ("extracted", "extracted_with_issues")

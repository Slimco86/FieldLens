"""Compass "Standard Survey Report" (native-text PDF) profile.

Uses ``pypdf`` (pure Python, no OCR, no network). Layout-mode text gives the column order that
plain mode scrambles; casing-point rows are read from plain text where the layout mode loses the
name column. Every page is accounted for (processed / no-text), every value carries its page and
a table/row/column cell id, and the depth/azimuth/CRS references are read from the report's own
header (MD/TVD reference with its elevation, map system, datum, grid convergence). Scanned pages
are never OCR'd here (TASK-030): a page without a text layer is reported as skipped."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import event_time, parse_number, text_attr
from .types import (
    MAX_PDF_PAGES,
    MISSING_REFERENCE,
    REFERENCE_CONFLICT,
    SUSPICIOUS_VALUE,
    TEMPORAL_AMBIGUITY,
    Attr,
    CoverageOut,
    Finding,
    Locator,
    ParseContext,
    ProfileError,
    ProfileOutput,
    Rec,
)

_NUM = r"-?\d[\d,]*\.\d+|-?\.\d+"
_SURVEY_ROW = re.compile(rf"^\s*((?:{_NUM})(?:\s+(?:{_NUM})){{9}})\s*$")
_PROGRAM_ROW = re.compile(rf"^\s*({_NUM})\s+({_NUM})\s{{2,}}(.+?)\s{{2,}}(.+?)\s{{2,}}(.+?)\s*$")
_CASING_ROW = re.compile(
    rf'^(?P<name>[\d /]+")(?P<md>{_NUM})\s+(?P<tvd>{_NUM})\s+(?P<csg>{_NUM})\s+(?P<hole>{_NUM})$'
)
SURVEY_COLUMNS = (
    ("md", "m"),
    ("incl", "deg"),
    ("azi", "deg"),
    ("tvd", "m"),
    ("dispNs", "m"),
    ("dispEw", "m"),
    ("vertSect", "m"),
    ("dls", "deg/30m"),
    ("build_rate", "deg/30m"),
    ("turn_rate", "deg/30m"),
)
EXPECTED_HEADER_UNITS = "(m)", "(°)", "(°/30m)"
ELEVATION = re.compile(r"@\s*(\d+(?:\.\d+)?)\s*m")


def _pdf_loc(page: int, table: str | None = None, cell: str | None = None) -> Locator:
    loc: Locator = {"kind": "pdf", "page": page}
    if table:
        loc["table_id"] = table
    if cell:
        loc["cell_id"] = cell
    return loc


def _collapse(line: str) -> str:
    return re.sub(r" {3,}", "   ", line.strip())


def _num(token: str) -> float | None:
    return parse_number(token)


def _after(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


class SurveyReportProfile:
    name = "pdf_compass_survey_report"
    version = "1"
    method = "native_pdf_pypdf"
    families = ("pdf",)

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        if format_family != "pdf":
            return False
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            if len(reader.pages) > MAX_PDF_PAGES:
                return False
            text = (reader.pages[0].extract_text() or "") + (
                reader.pages[1].extract_text() if len(reader.pages) > 1 else ""
            )
        except Exception:
            return False
        return "Standard Survey Report" in text or (
            "Survey Report" in text and "COMPASS" in text.upper()
        )

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError

        try:
            reader = PdfReader(str(path))
            n_pages = len(reader.pages)
        except (PyPdfError, ValueError, OSError) as exc:
            raise ProfileError("pdf_malformed", f"PDF cannot be read: {exc}") from exc
        if n_pages > MAX_PDF_PAGES:
            raise ProfileError("too_many_pages", f"PDF has {n_pages} pages (limit {MAX_PDF_PAGES})")
        findings: list[Finding] = []
        records: list[Rec] = []
        layout: dict[int, str] = {}
        plain: dict[int, str] = {}
        failed: list[int] = []
        notext: list[int] = []
        for i in range(n_pages):
            try:
                layout[i + 1] = reader.pages[i].extract_text(extraction_mode="layout") or ""
                plain[i + 1] = reader.pages[i].extract_text() or ""
            except Exception:  # per-page isolation: one bad page must not hide the rest
                failed.append(i + 1)
                continue
            if not layout[i + 1].strip():
                notext.append(i + 1)
        # ---- header ------------------------------------------------------------------------
        hdr_page = next((p for p, t in layout.items() if "TVD Reference" in t), None)
        if hdr_page is None:
            raise ProfileError("profile_mismatch", "no survey-report header page found")
        header = self._header(layout[hdr_page], plain.get(hdr_page, ""), hdr_page, findings)
        subject = header.pop("_subject")
        head_attrs: list[Attr] = header["attrs"]
        tvd_ref = header.get("tvd_ref")
        md_ref = header.get("md_ref")
        report_time = None
        footer = _after(r"(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})", plain.get(hdr_page, ""))
        if footer:
            d, mo, rest = footer[:2], footer[3:5], footer[6:]
            report_time = event_time(f"{rest[:4]}-{mo}-{d}T{rest[5:]}", "report footer")
            if report_time:
                report_time.timezone_known = False
        head = Rec("survey_report_header", subject, _pdf_loc(hdr_page), head_attrs, None, report_time)
        records.append(head)
        if tvd_ref and md_ref and ELEVATION.search(tvd_ref) and ELEVATION.search(md_ref):
            if ELEVATION.search(tvd_ref).group(1) != ELEVATION.search(md_ref).group(1):  # type: ignore[union-attr]
                findings.append(
                    Finding(REFERENCE_CONFLICT, "error",
                            "TVD and MD references state different elevations.",
                            "ref_tvd_md_conflict", ["survey_report_header.tvd_reference", "survey_report_header.md_reference"],
                            [0], [_pdf_loc(hdr_page)], ["placement", "calculation"])
                )
        # ---- survey program + stations + casing -----------------------------------------
        azi_ref = header.get("azi_ref")
        stations = 0
        bad_tvd: list[int] = []
        non_mono: list[int] = []
        prev_md: float | None = None
        row_no_in_table = 0
        program = 0
        for page in sorted(layout):
            lines = [_collapse(ln) for ln in layout[page].splitlines() if ln.strip()]
            in_prog = False
            for ln in lines:
                if ln.startswith("Survey Program"):
                    in_prog = True
                    continue
                if in_prog:
                    m = _PROGRAM_ROW.match(ln)
                    if m:
                        program += 1
                        cid = f"program/r{program}"
                        recs = Rec(
                            "survey_program_entry", subject, _pdf_loc(page, "survey_program", f"r{program}"),
                            [
                                _q("survey_program_entry.from_md", page, "survey_program", f"r{program}c1", m.group(1), "m", md_ref),
                                _q("survey_program_entry.to_md", page, "survey_program", f"r{program}c2", m.group(2), "m", md_ref),
                                text_attr("survey_program_entry.survey_name", _pdf_loc(page, "survey_program", f"r{program}c3"), m.group(3)),
                                text_attr("survey_program_entry.tool_name", _pdf_loc(page, "survey_program", f"r{program}c4"), m.group(4)),
                                text_attr("survey_program_entry.description", _pdf_loc(page, "survey_program", f"r{program}c5"), m.group(5)),
                            ],
                            None, report_time,
                        )
                        del cid
                        records.append(recs)
                        continue
                    if ln.startswith("Survey") and "Program" not in ln:
                        in_prog = False
                m = _SURVEY_ROW.match(ln)
                if not m:
                    continue
                toks = m.group(1).split()
                vals = [_num(t) for t in toks]
                row_no_in_table += 1
                stations += 1
                attrs: list[Attr] = []
                for ci, ((key, unit), tok) in enumerate(zip(SURVEY_COLUMNS, toks, strict=True), 1):
                    ref = tvd_ref if key == "tvd" else md_ref if key == "md" else None
                    if key in ("incl", "azi"):
                        ref = azi_ref if key == "azi" else None
                    attrs.append(
                        _q(f"trajectory_station.{key}", page, "survey", f"r{row_no_in_table}c{ci}", tok, unit, ref)
                    )
                rec = Rec(
                    "trajectory_station", subject,
                    _pdf_loc(page, "survey", f"r{row_no_in_table}"), attrs, None, report_time,
                )
                rec.ordinal = len(records)
                records.append(rec)
                md, tvd = vals[0], vals[3]
                if md is not None and tvd is not None and tvd > md + 1e-6:
                    bad_tvd.append(rec.ordinal)
                    for a in attrs:
                        if a.key == "trajectory_station.tvd":
                            a.validation_state = "invalid"
                if md is not None:
                    if prev_md is not None and md <= prev_md:
                        non_mono.append(rec.ordinal)
                    prev_md = md
        # casing points (plain text keeps the name column)
        casing = 0
        for page in sorted(plain):
            text = plain[page]
            k = text.find("Casing Points")
            if k < 0:
                continue
            hole_unit = "in" if "Casing" in text and "(in)" in layout.get(page, "") else None
            for ln in text[k:].splitlines()[1:]:
                if ln.startswith(("Measured", "Design", "Formations", "Approved", "Checked")):
                    break
                m = _CASING_ROW.match(ln.strip())
                if not m:
                    continue
                casing += 1
                loc = lambda c: _pdf_loc(page, "casing_points", f"r{casing}c{c}")  # noqa: E731
                records.append(
                    Rec(
                        "casing_point", subject, _pdf_loc(page, "casing_points", f"r{casing}"),
                        [
                            text_attr("casing_point.name", loc(1), m.group("name")),
                            _q("casing_point.md", page, "casing_points", f"r{casing}c2", m.group("md"), "m", md_ref),
                            _q("casing_point.tvd", page, "casing_points", f"r{casing}c3", m.group("tvd"), "m", tvd_ref),
                            _q("casing_point.casing_diameter", page, "casing_points", f"r{casing}c4", m.group("csg"), hole_unit, None),
                            _q("casing_point.hole_diameter", page, "casing_points", f"r{casing}c5", m.group("hole"), hole_unit, None),
                        ],
                        None, report_time,
                    )
                )
        for i, r in enumerate(records):
            r.ordinal = i
        if stations == 0:
            findings.append(
                Finding("EXTRACTION_PARTIAL", "error", "no survey station rows were recognized.",
                        "survey_no_rows", blocked=["placement", "calculation"])
            )
        if casing == 0:
            findings.append(
                Finding("EXTRACTION_PARTIAL", "info", "no casing-point rows were recognized.",
                        "casing_none", blocked=["physical_geometry"])
            )
        if bad_tvd:
            findings.append(
                Finding(SUSPICIOUS_VALUE, "error", f"{len(bad_tvd)} station(s) have TVD greater than MD; marked invalid.",
                        "survey_tvd_gt_md", ["trajectory_station.tvd"], bad_tvd[:50],
                        [records[o].locator for o in bad_tvd[:5]], ["placement", "calculation"])
            )
        if non_mono:
            findings.append(
                Finding(SUSPICIOUS_VALUE, "warning", f"MD is not increasing at {len(non_mono)} station(s); order kept.",
                        "survey_md_not_increasing", ["trajectory_station.md"], non_mono[:50],
                        [records[o].locator for o in non_mono[:5]], ["calculation"])
            )
        findings.append(
            Finding(TEMPORAL_AMBIGUITY, "info",
                    "stations carry no acquisition time; only the report print time is known "
                    "(kept as report time, not effective time).",
                    "survey_no_effective_time", ["trajectory_station.md"], [0], blocked=["temporal_state"])
        )
        tie = header.get("tie_on")
        first = next((r for r in records if r.kind == "trajectory_station"), None)
        if tie is not None and first is not None:
            md0 = first.attr("trajectory_station.md")
            if md0 is not None and md0.number is not None and abs(md0.number - tie) > 1e-6:
                findings.append(
                    Finding(REFERENCE_CONFLICT, "warning",
                            f"tie-on depth {tie:g} differs from the first station MD {md0.number:g}.",
                            "survey_tie_on_mismatch", ["trajectory_station.md"], [first.ordinal],
                            [first.locator], ["calculation"])
                )
        # ---- coverage -----------------------------------------------------------------------
        reasons: list[str] = []
        missing = [str(p) for p in sorted(set(failed + notext))]
        if failed:
            reasons.append(f"text extraction failed on page(s) {failed}")
        if notext:
            reasons.append(f"page(s) {notext} have no text layer (scanned; OCR is out of scope)")
        if reasons:
            findings.append(
                Finding("EXTRACTION_PARTIAL", "warning", "; ".join(reasons) + ".", "pdf_pages_skipped",
                        locators=[_pdf_loc(p) for p in sorted(set(failed + notext))[:5]],
                        blocked=["claim_acceptance"])
            )
        done = n_pages - len(set(failed + notext))
        cov = CoverageOut("page", done, n_pages, missing, reasons)
        return ProfileOutput(
            records, findings, cov, "succeeded" if cov.complete else "partial",
            {"pages": n_pages, "stations": stations, "casing_points": casing,
             "program_rows": program, "pypdf": _pypdf_version()},
        )

    # -------------------------------------------------------------------------------------
    def _header(self, lay: str, pl: str, page: int, findings: list[Finding]) -> dict[str, Any]:
        lines = [_collapse(ln) for ln in lay.splitlines() if ln.strip()]
        text = "\n".join(lines)

        def ref_value(label: str) -> str | None:
            for i, ln in enumerate(lines):
                m = re.search(rf"{label}:\s{{3}}(.+)$", ln)
                if m:
                    val = re.sub(r"\s{3,}", " ", m.group(1)).strip()
                    nxt = lines[i + 1] if i + 1 < len(lines) else ""
                    if nxt and ":" not in nxt and len(nxt) < 30 and not nxt[0].isdigit():
                        val = f"{val} {nxt.strip()}"
                    return val
            return None

        tvd_ref, md_ref = ref_value("TVD Reference"), ref_value("MD Reference")
        well = _after(r"Wellbore:\s{3}(\S.*?)(?:\s{3}|$)", text, re.M)
        design = _after(r"Design:\s{3}(\S.*?)(?:\s{3}|$)", text, re.M)
        site = _after(r"Site:\s{3}(\S.*?)(?:\s{3}|$)", text, re.M)
        cal = _after(r"Survey Calculation Method:\s{3}(\S.*?)(?:\s{3}|$)", text, re.M)
        map_system = _after(r"Map System:\s{3}(.+?)(?:\s{3}|$)", text, re.M)
        geo_datum = _after(r"Geo Datum:\s{3}(.+?)(?:\s{3}|$)", text, re.M)
        map_zone = _after(r"Map Zone:\s{3}(.+?)(?:\s{3}|$)", text, re.M)
        sys_datum = _after(r"System Datum:\s{3}(.+?)(?:\s{3}|$)", text, re.M)
        conv = _after(r"Grid Convergence:\s*(-?[\d.]+)", text)
        grid = bool(re.search(r"\bGrid\S*North Reference", text))
        tie = _after(r"Tie On Depth:\s{3}(-?\d[\d,.]*)", text)
        vs_dir = None
        m = re.search(rf"Direction\s+\(°\)\s*\n[^\n]*\(m\)[^\n]*\n\s*({_NUM})\s+({_NUM})\s+({_NUM})\s+({_NUM})", text)
        if m is None:
            m = re.search(rf"^\s*({_NUM})\s{{3}}({_NUM})\s{{3}}({_NUM})\s{{3}}({_NUM})\s*$", text, re.M)
        if m:
            vs_dir = m.group(4)
        mag = re.search(rf"GEOMAGNETICREFERENCE\s+(\d{{2}}\.\d{{2}}\.\d{{4}})\s+({_NUM})\s+({_NUM})\s+({_NUM})", text)
        site_n = re.search(rf"Site Position:\s+Northing:\s+({_NUM})", text)
        site_e = re.search(rf"From:\s+Map\s+Easting:\s+({_NUM})", text)
        well_n = re.search(rf"Well Position\s+\+N/-S\s+({_NUM})\s+m\s+Northing:\s+({_NUM})", text)
        well_e = re.search(rf"\+E/-W\s+({_NUM})\s+m\s+Easting:\s+({_NUM})", text)
        subject = {
            "well_name": site,
            "wellbore_name": well,
            "wellbore_label": well,
            "well_key": None,
            "design": design,
        }
        key = _well_key(well, text)
        subject["well_key"] = key
        attrs: list[Attr] = []

        def txt(k: str, v: str | None) -> None:
            attrs.append(text_attr(f"survey_report_header.{k}", _pdf_loc(page, "header", k), v))

        txt("tvd_reference", tvd_ref)
        txt("md_reference", md_ref)
        elev = ELEVATION.search(tvd_ref or "")
        if elev:
            attrs.append(_q("survey_report_header.reference_elevation", page, "header", "tvd_reference", elev.group(1), "m", tvd_ref))
        txt("map_system", map_system)
        txt("geo_datum", geo_datum)
        txt("map_zone", map_zone)
        txt("system_datum", sys_datum)
        txt("calculation_method", cal)
        txt("north_reference", "Grid" if grid else None)
        if conv:
            attrs.append(_q("survey_report_header.grid_convergence", page, "header", "grid_convergence", conv, "deg", "grid"))
        if tie:
            attrs.append(_q("survey_report_header.tie_on_depth", page, "header", "tie_on_depth", tie, "m", md_ref))
        if vs_dir:
            attrs.append(_q("survey_report_header.vertical_section_direction", page, "header", "vs_direction", vs_dir, "deg", "grid" if grid else None))
        if mag:
            attrs.append(text_attr("survey_report_header.magnetic_sample_date", _pdf_loc(page, "header", "magnetics"), mag.group(1)))
            attrs.append(_q("survey_report_header.magnetic_declination", page, "header", "magnetics", mag.group(2), "deg", None))
            attrs.append(_q("survey_report_header.magnetic_dip", page, "header", "magnetics", mag.group(3), "deg", None))
            attrs.append(_q("survey_report_header.magnetic_field_strength", page, "header", "magnetics", mag.group(4), "nT", None))
        for k, mm in (("site_northing", site_n), ("site_easting", site_e)):
            if mm:
                attrs.append(_q(f"survey_report_header.{k}", page, "header", k, mm.group(1), "m", f"{map_system or ''} {geo_datum or ''} {map_zone or ''}".strip() or None))
        if well_n:
            attrs.append(_q("survey_report_header.well_offset_ns", page, "header", "well_position", well_n.group(1), "m", None))
            attrs.append(_q("survey_report_header.well_northing", page, "header", "well_position", well_n.group(2), "m", f"{map_system or ''} {geo_datum or ''} {map_zone or ''}".strip() or None))
        if well_e:
            attrs.append(_q("survey_report_header.well_offset_ew", page, "header", "well_position", well_e.group(1), "m", None))
            attrs.append(_q("survey_report_header.well_easting", page, "header", "well_position", well_e.group(2), "m", f"{map_system or ''} {geo_datum or ''} {map_zone or ''}".strip() or None))
        for label, value, keys, blocked in (
            ("MD/TVD reference", tvd_ref and md_ref, ["survey_report_header.tvd_reference", "survey_report_header.md_reference"], ["placement", "calculation"]),
            ("map system / geodetic datum", map_system and geo_datum, ["survey_report_header.map_system", "survey_report_header.geo_datum"], ["placement"]),
            ("grid/true north reference", grid, ["survey_report_header.north_reference"], ["calculation", "placement"]),
        ):
            if not value:
                findings.append(
                    Finding(MISSING_REFERENCE, "warning", f"the report header does not state the {label}.",
                            f"missing:{label}", keys, [0], [_pdf_loc(page)], blocked)
                )
        return {"_subject": subject, "attrs": attrs, "tvd_ref": tvd_ref, "md_ref": md_ref,
                "azi_ref": "grid north" if grid else None,
                "tie_on": _num(tie) if tie else None}


def _q(key: str, page: int, table: str, cell: str, text: str, unit: str | None, ref: str | None) -> Attr:
    from .common import quantity_attr

    return quantity_attr(key, _pdf_loc(page, table, cell), text, unit, reference=ref)


def _well_key(wellbore: str | None, text: str) -> str | None:
    quad = _after(r"Site\s+[^\n]*?,\s*(\d{1,2}/\d{1,2})\s*$", text, re.M)
    m = re.fullmatch(r"([A-Z])-?(\d{1,3})", (wellbore or "").strip().upper())
    return f"{quad}-{m.group(1)}-{m.group(2)}" if quad and m else None


def _pypdf_version() -> str:
    import pypdf

    return str(pypdf.__version__)

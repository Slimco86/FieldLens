"""Compass "Standard Survey Report" plain-text profile (IN-11, TASK-051).

The same report the PDF profile reads, exported as a text file (the Volve ``..._ACTUAL`` files
are extensionless). Selection is by CONTENT only: a "Standard Survey Report" title (or "Survey
Report" with COMPASS) plus at least one plausible ten-column station row. Anything else is
declined so the other profiles still run.

The real export was not available when this was written; the layout assumptions are listed in
``docs/specs/INGESTION.md`` (IN-11) and are validated only against synthetic fixtures. Defensive
behaviour: LF/CRLF/CR line ends, form feeds between pages, tab- or space-separated columns,
header blocks repeated per page, units read from the column header block (a ``°`` that arrives as
byte 0xB0 is decoded through the encoding ``fieldlens.textenc`` records). Nothing is assumed: a
reference or unit the file does not state is reported (MISSING_REFERENCE / MISSING_UNIT), numbers
use the shared strict rules (a decimal comma stays unknown), and every value carries a text
locator (1-based physical line, station number, column name)."""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from fieldlens.textenc import open_text, sniff_path

from .common import event_time, parse_number, quantity_attr, text_attr
from .survey_lines import (
    CASING_ROW,
    ELEVATION,
    PROGRAM_ROW,
    SURVEY_COLUMNS,
    after,
    collapse,
    well_key,
)
from .types import (
    EXTRACTION_PARTIAL,
    IDENTITY_MISMATCH,
    MAX_RECORDS,
    MAX_TEXT_LINES,
    MISSING_REFERENCE,
    MISSING_UNIT,
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

DETECT_LINES = 20_000
TITLE_LINES = 300
HEADER_WINDOW = 6
_TOKEN = re.compile(r"[+-]?(?:\d[\d,]*\.?\d*|\.\d+)")
_UNIT_TOKEN = re.compile(r"\(([^()]*)\)")
_REPORT_TIME = r"(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}:\d{2})"
_TITLE_KEYS = (
    r"Measured",
    r"Incl",
    r"Azi",
    r"Vertical Depth|TVD",
    r"\+N/-S",
    r"\+E/-W",
    r"Vertical Section|Vert\w*\.? Sect|V\.? ?Sect",
    r"Dogleg|DLS",
    r"Build",
    r"Turn",
)
_HEADER_LABELS = (
    "TVD Reference",
    "MD Reference",
    "Wellbore",
    "Site",
    "Design",
    "Survey Calculation Method",
    "Map System",
    "Geo Datum",
    "Map Zone",
    "System Datum",
    "North Reference",
    "Tie On Depth",
)
_REF_CONFLICT_LABELS = frozenset(
    {
        "TVD Reference",
        "MD Reference",
        "Map System",
        "Geo Datum",
        "Map Zone",
        "System Datum",
        "North Reference",
    }
)
_LABEL_RE = {
    label: re.compile(rf"(?:^|\s){re.escape(label)}:\s*(\S.*)$") for label in _HEADER_LABELS
}
_CASING_STOP = ("Design", "Formations", "Approved", "Checked", "Survey Program")


def split_station_row(line: str) -> list[str] | None:
    """The ten fields of a survey row, or ``None``. Tab-separated lines keep empty fields (they
    become unknown values, never zero); otherwise fields are whitespace separated."""
    raw = line.replace("\f", "").strip(" \r\n")
    if not raw:
        return None
    fields: list[str] = []
    if "\t" in raw:
        fields = [f.strip() for f in raw.strip("\t ").split("\t")]
    if len(fields) != 10:
        fields = raw.split()
    if len(fields) != 10 or not fields[0]:
        return None
    return fields if all(not f or _TOKEN.fullmatch(f) for f in fields) else None


def sniff_compass_text(lines: Iterable[str]) -> bool:
    """Content check shared by the profile and upload intake: report title + a station row."""
    titled = False
    seen = 0
    head: list[str] = []
    for line in lines:
        seen += 1
        if seen > DETECT_LINES:
            break
        if seen <= TITLE_LINES:
            head.append(line)
            if not titled:
                joined = "\n".join(head)
                titled = "Standard Survey Report" in joined or (
                    "Survey Report" in joined and "COMPASS" in joined.upper()
                )
        if titled and split_station_row(line) is not None:
            return True
    return False


def _loc(line: int, column: str | None = None, record: int | None = None) -> Locator:
    loc: Locator = {"kind": "text", "line_start": line, "line_end": line}
    if record is not None:
        loc["logical_record"] = record
    if column:
        loc["column_name"] = column
    return loc


def _q(
    key: str,
    line: int,
    column: str,
    record: int | None,
    text: str,
    unit: str | None,
    ref: str | None,
) -> Attr:
    return quantity_attr(key, _loc(line, column, record), text, unit, reference=ref)


def _canon_unit(token: str) -> str | None:
    """Stated unit text; the degree sign is spelled ``deg`` like the PDF profile. A token that
    carries a replacement character (wrong decode) counts as not stated."""
    unit = token.strip().replace("°", "deg")
    return None if not unit or "\ufffd" in unit else unit


def _window_units(window: Iterable[str]) -> list[str | None] | None:
    tokens = [m for ln in window for m in _UNIT_TOKEN.findall(ln)]
    if len(tokens) < 10:
        return None
    return [_canon_unit(t) for t in tokens[-10:]]


def _titles_in_order(window: Iterable[str]) -> bool | None:
    """True/False when all ten column titles are found in/out of Compass order, else None."""
    text = " ".join(window)
    spots: list[int] = []
    for pattern in _TITLE_KEYS:
        m = re.search(pattern, text, re.I)
        if m is None:
            return None
        spots.append(m.start())
    return spots == sorted(spots) and len(set(spots)) == 10


class CompassTextProfile:
    name = "text_compass_survey_report"
    version = "1"
    method = "native_text_compass"
    families = ("text", "csv")

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        if format_family not in self.families or sniff_path(path) is None:
            return False
        try:
            with open_text(path) as handle:
                return sniff_compass_text(handle)
        except (OSError, ValueError):
            return False

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        encoding = sniff_path(path)
        if encoding is None:
            raise ProfileError("profile_mismatch", "file is not decodable text")
        raw_lines: list[str] = []
        with open_text(path) as handle:
            for raw in handle:
                if len(raw_lines) >= MAX_TEXT_LINES:
                    raise ProfileError("too_many_lines", f"text has over {MAX_TEXT_LINES} lines")
                raw_lines.append(raw.rstrip("\n"))
        if not sniff_compass_text(raw_lines):
            raise ProfileError("profile_mismatch", "no Compass survey report title and rows found")
        norm = [collapse(ln.replace("\f", "").replace("\t", "   ")) for ln in raw_lines]
        pages = 1 + sum(ln.count("\f") for ln in raw_lines)
        title_no = next(
            (i + 1 for i, ln in enumerate(norm[:TITLE_LINES]) if "Survey Report" in ln), 1
        )
        rows = [split_station_row(ln) for ln in raw_lines]
        first_row = next((i for i, f in enumerate(rows) if f is not None), len(norm))
        findings: list[Finding] = []
        header = self._header(norm, norm[:first_row], title_no, findings)
        subject = header.pop("_subject")
        tvd_ref, md_ref, azi_ref = header["tvd_ref"], header["md_ref"], header["azi_ref"]
        # column units/titles from the header block that precedes the first station row
        lead = [ln for ln in norm[:first_row] if ln][-HEADER_WINDOW:]
        units = _window_units(lead)
        titles_state = _titles_in_order(lead)
        if titles_state is False:
            raise ProfileError(
                "profile_mismatch", "survey column titles are not in the Compass standard order"
            )
        units_line = first_row + 1
        if units is not None:
            tie_attr = next((a for a in header["attrs"] if a.key.endswith(".tie_on_depth")), None)
            if tie_attr is not None and units[0]:
                fixed = _q(
                    tie_attr.key,
                    tie_attr.locator["line_start"],
                    "tie_on_depth",
                    None,
                    tie_attr.original_text or "",
                    units[0],
                    md_ref,
                )
                header["attrs"][header["attrs"].index(tie_attr)] = fixed
        report_time = None
        footer = after(_REPORT_TIME, "\n".join(norm))
        if footer:
            report_time = event_time(
                f"{footer[6:10]}-{footer[3:5]}-{footer[:2]}T{footer[11:]}", "report footer"
            )
            if report_time:
                report_time.timezone_known = False
        records: list[Rec] = [
            Rec("survey_report_header", subject, _loc(title_no), header["attrs"], None, report_time)
        ]
        if tvd_ref and md_ref and ELEVATION.search(tvd_ref) and ELEVATION.search(md_ref):
            if ELEVATION.search(tvd_ref).group(1) != ELEVATION.search(md_ref).group(1):  # type: ignore[union-attr]
                findings.append(
                    Finding(
                        REFERENCE_CONFLICT,
                        "error",
                        "TVD and MD references state different elevations.",
                        "ref_tvd_md_conflict",
                        ["survey_report_header.tvd_reference", "survey_report_header.md_reference"],
                        [0],
                        [_loc(title_no)],
                        ["placement", "calculation"],
                    )
                )
        # ---- body ---------------------------------------------------------------------------
        unit_conflicts: list[int] = []
        stations = program = casing = 0
        bad_tvd: list[int] = []
        non_mono: list[int] = []
        malformed: list[int] = []
        prev_md: float | None = None
        window: deque[str] = deque(maxlen=HEADER_WINDOW)
        prev_was_row = False
        in_prog = in_casing = False
        casing_units: list[str] = []
        casing_scan = 0
        for idx, ln in enumerate(norm):
            line_no = idx + 1
            fields = rows[idx]
            if fields is not None:
                if not prev_was_row and stations:
                    found = _window_units(window)
                    if found is not None and units is not None and found != units:
                        unit_conflicts.append(line_no)
                prev_was_row = True
                in_prog = in_casing = False
                stations += 1
                if stations > MAX_RECORDS:
                    raise ProfileError("too_many_records", "too many survey rows")
                attrs: list[Attr] = []
                for ci, ((key, _), tok) in enumerate(zip(SURVEY_COLUMNS, fields, strict=True)):
                    ref = tvd_ref if key == "tvd" else md_ref if key == "md" else None
                    if key == "azi":
                        ref = azi_ref
                    unit = units[ci] if units else None
                    attrs.append(
                        _q(f"trajectory_station.{key}", line_no, key, stations, tok, unit, ref)
                    )
                rec = Rec(
                    "trajectory_station",
                    subject,
                    _loc(line_no, None, stations),
                    attrs,
                    None,
                    report_time,
                )
                rec.ordinal = len(records)
                records.append(rec)
                md, tvd = parse_number(fields[0]), parse_number(fields[3])
                if md is not None and tvd is not None and tvd > md + 1e-6:
                    bad_tvd.append(rec.ordinal)
                    for a in attrs:
                        if a.key == "trajectory_station.tvd":
                            a.validation_state = "invalid"
                if md is not None:
                    if prev_md is not None and md <= prev_md:
                        non_mono.append(rec.ordinal)
                    prev_md = md
                continue
            if not ln:
                continue
            window.append(ln)
            prev_was_row = False
            tokens = ln.split()
            if (
                stations
                and 6 <= len(tokens) <= 30
                and len(tokens) != 10
                and all(_TOKEN.fullmatch(t) for t in tokens)
            ):
                malformed.append(line_no)  # numeric row that is not ten columns: never dropped
                continue
            if ln.startswith("Survey Program"):
                in_prog, in_casing = True, False
                continue
            if "Casing Points" in ln:
                in_casing, in_prog = True, False
                casing_units = []
                casing_scan = 4
                continue
            if in_prog:
                m = PROGRAM_ROW.match(ln)
                if m:
                    program += 1
                    unit = units[0] if units else None
                    cols = ("from_md", "to_md", "survey_name", "tool_name", "description")
                    pattrs: list[Attr] = [
                        _q(
                            f"survey_program_entry.{c}",
                            line_no,
                            c,
                            program,
                            m.group(i),
                            unit,
                            md_ref,
                        )
                        for i, c in enumerate(cols[:2], 1)
                    ] + [
                        text_attr(
                            f"survey_program_entry.{c}", _loc(line_no, c, program), m.group(i)
                        )
                        for i, c in enumerate(cols[2:], 3)
                    ]
                    records.append(
                        Rec(
                            "survey_program_entry",
                            subject,
                            _loc(line_no, None, program),
                            pattrs,
                            None,
                            report_time,
                        )
                    )
                    continue
                if ln.startswith("Survey") and "Program" not in ln:
                    in_prog = False
            if in_casing:
                if ln.startswith(_CASING_STOP):
                    in_casing = False
                    continue
                if casing_scan > 0:
                    casing_units += _UNIT_TOKEN.findall(ln)
                    casing_scan -= 1
                cm = CASING_ROW.match(ln)
                if cm:
                    casing += 1
                    dia_unit = "in" if "in" in casing_units else None
                    md_unit = units[0] if units else None
                    tvd_unit = units[3] if units else None
                    cattrs: list[Attr] = [
                        text_attr("casing_point.name", _loc(line_no, "name", casing), cm["name"]),
                        _q("casing_point.md", line_no, "md", casing, cm["md"], md_unit, md_ref),
                        _q(
                            "casing_point.tvd", line_no, "tvd", casing, cm["tvd"], tvd_unit, tvd_ref
                        ),
                        _q(
                            "casing_point.casing_diameter",
                            line_no,
                            "casing_diameter",
                            casing,
                            cm["csg"],
                            dia_unit,
                            None,
                        ),
                        _q(
                            "casing_point.hole_diameter",
                            line_no,
                            "hole_diameter",
                            casing,
                            cm["hole"],
                            dia_unit,
                            None,
                        ),
                    ]
                    records.append(
                        Rec(
                            "casing_point",
                            subject,
                            _loc(line_no, None, casing),
                            cattrs,
                            None,
                            report_time,
                        )
                    )
        for i, r in enumerate(records):
            r.ordinal = i
        self._findings(
            findings,
            records,
            header,
            units,
            units_line,
            unit_conflicts,
            titles_state,
            stations,
            casing,
            bad_tvd,
            non_mono,
            title_no,
        )
        total = sum(1 for ln in norm if ln)
        reasons: list[str] = []
        if malformed:
            reasons.append(
                f"{len(malformed)} numeric row(s) in the survey section do not have ten columns "
                "and were not extracted"
            )
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "warning",
                    reasons[-1] + ".",
                    "text_rows_skipped",
                    locators=[_loc(n) for n in malformed[:5]],
                    blocked=["claim_acceptance"],
                )
            )
        cov = CoverageOut(
            "line", total - len(malformed), total, [f"L{n}" for n in malformed[:200]], reasons
        )
        return ProfileOutput(
            records,
            findings,
            cov,
            "succeeded" if cov.complete else "partial",
            {
                "text_encoding": encoding,
                "lines": len(raw_lines),
                "pages": pages,
                "stations": stations,
                "casing_points": casing,
                "program_rows": program,
                "malformed_rows": len(malformed),
            },
        )

    # -------------------------------------------------------------------------------------
    def _findings(
        self,
        findings: list[Finding],
        records: list[Rec],
        header: dict[str, Any],
        units: list[str | None] | None,
        units_line: int,
        unit_conflicts: list[int],
        titles_state: bool | None,
        stations: int,
        casing: int,
        bad_tvd: list[int],
        non_mono: list[int],
        title_line: int,
    ) -> None:
        if stations == 0:
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "error",
                    "no survey station rows were recognized.",
                    "survey_no_rows",
                    blocked=["placement", "calculation"],
                )
            )
        if casing == 0:
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "info",
                    "no casing-point rows were recognized.",
                    "casing_none",
                    blocked=["physical_geometry"],
                )
            )
        if stations and (units is None or any(u is None for u in units)):
            findings.append(
                Finding(
                    MISSING_UNIT,
                    "warning",
                    "the survey column header block does not state a unit for every column; "
                    "station values keep no unit (never assumed).",
                    "missing:station_units",
                    ["trajectory_station.md", "trajectory_station.tvd"],
                    [],
                    [_loc(units_line)],
                    ["placement", "calculation"],
                )
            )
        if stations and titles_state is None:
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "warning",
                    "the ten survey column titles were not all found; the Compass standard "
                    "column order is assumed.",
                    "survey_titles_unconfirmed",
                    ["trajectory_station.md"],
                    [],
                    [_loc(units_line)],
                    ["placement", "calculation"],
                )
            )
        if unit_conflicts:
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "error",
                    "a repeated page header states different column units than the first one.",
                    "survey_units_conflict",
                    ["trajectory_station.md"],
                    [],
                    [_loc(n) for n in unit_conflicts[:5]],
                    ["placement", "calculation"],
                )
            )
        if bad_tvd:
            findings.append(
                Finding(
                    SUSPICIOUS_VALUE,
                    "error",
                    f"{len(bad_tvd)} station(s) have TVD greater than MD; marked invalid.",
                    "survey_tvd_gt_md",
                    ["trajectory_station.tvd"],
                    bad_tvd[:50],
                    [records[o].locator for o in bad_tvd[:5]],
                    ["placement", "calculation"],
                )
            )
        if non_mono:
            findings.append(
                Finding(
                    SUSPICIOUS_VALUE,
                    "warning",
                    f"MD is not increasing at {len(non_mono)} station(s); order kept.",
                    "survey_md_not_increasing",
                    ["trajectory_station.md"],
                    non_mono[:50],
                    [records[o].locator for o in non_mono[:5]],
                    ["calculation"],
                )
            )
        findings.append(
            Finding(
                TEMPORAL_AMBIGUITY,
                "info",
                "stations carry no acquisition time; only the report print time is known "
                "(kept as report time, not effective time).",
                "survey_no_effective_time",
                ["trajectory_station.md"],
                [0],
                blocked=["temporal_state"],
            )
        )
        tie = header.get("tie_on")
        first = next((r for r in records if r.kind == "trajectory_station"), None)
        if tie is not None and first is not None:
            md0 = first.attr("trajectory_station.md")
            if md0 is not None and md0.number is not None and abs(md0.number - tie) > 1e-6:
                findings.append(
                    Finding(
                        REFERENCE_CONFLICT,
                        "warning",
                        f"tie-on depth {tie:g} differs from the first station MD {md0.number:g}.",
                        "survey_tie_on_mismatch",
                        ["trajectory_station.md"],
                        [first.ordinal],
                        [first.locator],
                        ["calculation"],
                    )
                )

    def _header(
        self, norm: list[str], head: list[str], title_line: int, findings: list[Finding]
    ) -> dict[str, Any]:
        found: dict[str, list[tuple[int, str]]] = {}
        for i, ln in enumerate(norm):
            for label, rx in _LABEL_RE.items():
                m = rx.search(ln)
                if m:
                    val = re.split(r"\s{3,}", m.group(1))[0].strip()
                    if val:
                        found.setdefault(label, []).append((i + 1, val))

        def first(label: str) -> tuple[int, str] | None:
            hits = found.get(label)
            return hits[0] if hits else None

        def value(label: str) -> str | None:
            hit = first(label)
            return hit[1] if hit else None

        for label, hits in found.items():
            distinct = list(dict.fromkeys(v for _, v in hits))
            if len(distinct) > 1:
                findings.append(
                    Finding(
                        REFERENCE_CONFLICT if label in _REF_CONFLICT_LABELS else IDENTITY_MISMATCH,
                        "error",
                        f"the file states more than one {label}: {', '.join(distinct[:3])}.",
                        f"header_conflict:{label}",
                        [],
                        [0],
                        [_loc(n) for n, _ in hits[:5]],
                        ["placement", "calculation"],
                    )
                )
        text = "\n".join(head)
        tvd_ref, md_ref = value("TVD Reference"), value("MD Reference")
        wellbore, site = value("Wellbore"), value("Site")
        north = value("North Reference")
        grid = bool(re.search(r"\bGrid\S*North Reference", text)) or bool(
            north and north.lower().startswith("grid")
        )
        azi_ref: str | None
        if north and not grid:
            word = north.lower().split()[0]
            azi_ref = f"{word} north" if word in ("true", "magnetic") else north
        else:
            azi_ref = "grid north" if grid else None
        conv = after(r"Grid Convergence:\s*(-?[\d.]+)", text)
        tie = value("Tie On Depth")
        tie_m = re.match(r"-?\d[\d,.]*", tie) if tie else None
        tie_num = parse_number(tie_m.group(0)) if tie_m else None
        subject: dict[str, Any] = {
            "well_name": site,
            "wellbore_name": wellbore,
            "wellbore_label": wellbore,
            "well_key": well_key(wellbore, text),
            "design": value("Design"),
        }
        attrs: list[Attr] = []

        def txt(key: str, label: str, override: str | None = None) -> None:
            hit = first(label)
            val = override if override is not None else (hit[1] if hit else None)
            attrs.append(
                text_attr(
                    f"survey_report_header.{key}", _loc(hit[0] if hit else title_line, key), val
                )
            )

        txt("tvd_reference", "TVD Reference")
        txt("md_reference", "MD Reference")
        elev = ELEVATION.search(tvd_ref or "")
        if elev:
            hit = first("TVD Reference")
            attrs.append(
                _q(
                    "survey_report_header.reference_elevation",
                    hit[0] if hit else title_line,
                    "reference_elevation",
                    None,
                    elev.group(1),
                    "m",
                    tvd_ref,
                )
            )
        txt("map_system", "Map System")
        txt("geo_datum", "Geo Datum")
        txt("map_zone", "Map Zone")
        txt("system_datum", "System Datum")
        txt("calculation_method", "Survey Calculation Method")
        txt("north_reference", "North Reference", None if north else "Grid" if grid else None)
        if conv:
            attrs.append(
                _q(
                    "survey_report_header.grid_convergence",
                    title_line,
                    "grid_convergence",
                    None,
                    conv,
                    "deg",
                    "grid",
                )
            )
        if tie:
            hit = first("Tie On Depth")
            attrs.append(
                _q(
                    "survey_report_header.tie_on_depth",
                    hit[0] if hit else title_line,
                    "tie_on_depth",
                    None,
                    tie,
                    None,
                    md_ref,
                )
            )
        map_system, geo_datum = value("Map System"), value("Geo Datum")
        for label, present, keys, blocked in (
            (
                "MD/TVD reference",
                tvd_ref and md_ref,
                ["survey_report_header.tvd_reference", "survey_report_header.md_reference"],
                ["placement", "calculation"],
            ),
            (
                "map system / geodetic datum",
                map_system and geo_datum,
                ["survey_report_header.map_system", "survey_report_header.geo_datum"],
                ["placement"],
            ),
            (
                "grid/true north reference",
                azi_ref,
                ["survey_report_header.north_reference"],
                ["calculation", "placement"],
            ),
        ):
            if not present:
                findings.append(
                    Finding(
                        MISSING_REFERENCE,
                        "warning",
                        f"the report header does not state the {label}.",
                        f"missing:{label}",
                        keys,
                        [0],
                        [_loc(title_line)],
                        blocked,
                    )
                )
        return {
            "_subject": subject,
            "attrs": attrs,
            "tvd_ref": tvd_ref,
            "md_ref": md_ref,
            "azi_ref": azi_ref,
            "tie_on": tie_num,
        }

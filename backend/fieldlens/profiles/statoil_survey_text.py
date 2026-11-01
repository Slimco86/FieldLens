"""Statoil-default survey export plain-text profile (IN-11, TASK-051).

The extensionless Volve ``Volve F_F-<n>_F-<n>_<survey name>_ACTUAL`` / ``..._PLAN`` files beside the
Compass PDFs are NOT the Compass "Standard Survey Report": they are a Statoil survey export::

    HEADER INFORMATION (all units in Statoil default)
    ---- / COMPANY: / FIELD: / WELL NAME: / WELLBORE NAME: / Survey Name: / Survey Date: ...
    Datum Name: Rotary Table(54.90m) / Surface EW: ...m / Surface Latitude: 58° 26' 29.8941 N ...
    Bottom Hole MD/TVD/EW/NS / Survey Program: ("H  174 - 2465 <name> : <description>") / ...
    Map-Zone / North Reference / Geo Datum / Vertical Section Direction
    SURVEY LIST
    MD  Inc  Azim  TVD  X-Offset (E/W)  Y-Offset (N/S)  UTM E/W  UTM N/S  DLS     (nine titles)
    m RKB  deg  deg  m RKB  m  m  m  m  deg/30m                                   (units row)
    145.90 0.00 0.00 145.90 0.190 2.698 435050.210 6478566.220 0.00               (nine numbers)

Selection is by CONTENT only (title line + ``SURVEY LIST`` + a nine-number station row). Nothing is
assumed: the survey status (planned / as-built) is only taken from explicit words in the survey
name, units and references come from the units row and ``Datum Name``, a numeric row with other
than nine fields is reported and not extracted (a field left blank in a fixed-width row stays
unknown), repeated ``SURVEY LIST`` sections are not merged, and no CRS code is guessed (the stated
map zone / geodetic datum text is preserved as a candidate). Every value carries a text locator
(1-based physical line, station number, column name). The surface location is emitted as a
``well_surface_location`` record so a wellbore need not fall back to the unlocated origin."""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Any

from fieldlens.textenc import open_text, sniff_path

from .common import event_time, parse_number, quantity_attr, text_attr
from .types import (
    EXTRACTION_PARTIAL,
    IDENTITY_MISMATCH,
    INTERVAL_CONFLICT,
    MAX_RECORDS,
    MAX_TEXT_LINES,
    MISSING_REFERENCE,
    MISSING_UNIT,
    REFERENCE_CONFLICT,
    SUSPICIOUS_VALUE,
    TEMPORAL_AMBIGUITY,
    Attr,
    CoverageOut,
    EventTime,
    Finding,
    Locator,
    ParseContext,
    ProfileError,
    ProfileOutput,
    Rec,
)

DETECT_LINES = 20_000
TITLE_LINES = 60
TITLE = "HEADER INFORMATION (all units in Statoil default)"
LIST_TITLE = "SURVEY LIST"
COLUMN_TITLES = (
    "md",
    "inc",
    "azim",
    "tvd",
    "x-offset (e/w)",
    "y-offset (n/s)",
    "utm e/w",
    "utm n/s",
    "dls",
)
COLUMNS = (
    "md",
    "incl",
    "azi",
    "tvd",
    "dispEw",
    "dispNs",
    "utmEasting",
    "utmNorthing",
    "dls",
)
NCOL = len(COLUMNS)
_TOKEN = re.compile(r"[+-]?(?:\d[\d,]*\.?\d*|\.\d+)")
_GAP = re.compile(r"\s{2,}")
_LABEL = re.compile(r"^\s*([A-Za-z][A-Za-z0-9 .\-/()]*?)\s*:\s*(.*?)\s*$")
_PROGRAM = re.compile(
    r"^H\s+(?P<from>\d+(?:\.\d+)?)\s*-\s*(?P<to>\d+(?:\.\d+)?)\s+(?P<name>.*?)\s*:\s*(?P<desc>.*?)\s*$"
)
_QUANTITY = re.compile(r"^(?P<n>[+-]?[\d.,]+)\s*(?P<u>[A-Za-z°]*)$")
_DATUM = re.compile(r"^(?P<name>.*?)\s*\(\s*(?P<n>[+-]?[\d.,]+)\s*(?P<u>[A-Za-z]+)\s*\)$")
_LATLON = re.compile(r"^(\d{1,3})\D+?(\d{1,2})\D+?(\d{1,2}(?:\.\d+)?)\D*?([NSEW])$")
_DATE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{4})$")
_STATUS_PLAN = re.compile(r"\b(?:plan|planned|proposed)\b", re.I)
_STATUS_ACTUAL = re.compile(r"\b(?:as[- ]?built|actual)\b", re.I)

# header label (lower case) -> attribute key
_TEXT_LABELS = {
    "company": "company",
    "field": "field_name",
    "drilled from": "drilled_from",
    "survey name": "survey_name",
    "survey date": "survey_date",
    "extraction date": "extraction_date",
    "calculation method": "calculation_method",
    "datum name": "datum_name",
    "system datum": "system_datum",
    "map-zone": "map_zone",
    "north reference": "north_reference",
    "geo datum": "geo_datum",
}
_QUANTITY_LABELS = {
    "kick off depth": "kick_off_depth",
    "water depth": "water_depth",
    "kb-wh": "kb_wh",
    "kb-msl": "kb_msl",
    "vertical section direction": "vertical_section_direction",
    "bottom hole md": "bottom_hole_md",
    "bottom hole tvd": "bottom_hole_tvd",
    "bottom hole ew": "bottom_hole_ew",
    "bottom hole ns": "bottom_hole_ns",
}
_IDENTITY_LABELS = ("well name", "wellbore name")
_SURFACE_LABELS = ("surface ew", "surface ns", "surface latitude", "surface longitude")
_KNOWN = (
    set(_TEXT_LABELS)
    | set(_QUANTITY_LABELS)
    | set(_IDENTITY_LABELS)
    | set(_SURFACE_LABELS)
    | {"survey program"}
)
_REF_CONFLICT_LABELS = frozenset(
    {"datum name", "system datum", "map-zone", "north reference", "geo datum"}
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\t", " ")).strip().lower()


def _is_numeric_token(token: str) -> bool:
    return bool(_TOKEN.fullmatch(token))


def _header_titles(line: str) -> list[str]:
    return [_norm(t) for t in _GAP.split(line.replace("\t", "  ").strip()) if t.strip()]


def _starts(header_line: str) -> list[int] | None:
    """Column start offsets of a space-aligned header row (None for tab-separated rows)."""
    if "\t" in header_line:
        return None
    spots = [m.start() for m in re.finditer(r"\S+(?: \S+)*", header_line)]
    return spots if len(spots) == NCOL else None


def split_station_row(line: str, starts: list[int] | None = None) -> list[str] | None:
    """The nine fields of a station row, or ``None``. A field that is blank in a tab-separated or
    column-aligned row is returned as an empty string (an unknown value, never zero); a numeric
    row whose fields cannot be assigned to columns without guessing returns ``None``."""
    raw = line.replace("\f", "").rstrip("\r\n")
    if not raw.strip():
        return None
    if "\t" in raw:
        parts = [p.strip() for p in raw.strip("\t ").split("\t")]
        ok = len(parts) == NCOL and parts[0] and all(not p or _is_numeric_token(p) for p in parts)
        return parts if ok else None
    tokens = raw.split()
    if not all(_is_numeric_token(t) for t in tokens):
        return None
    if len(tokens) == NCOL:
        return tokens
    if starts is None or not 1 <= len(tokens) < NCOL:
        return None
    bounds = [*starts, max(len(raw), starts[-1]) + 1]
    bounds[0] = 0
    fields = [raw[bounds[i] : bounds[i + 1]].strip() for i in range(NCOL)]
    if (
        any(len(f.split()) > 1 for f in fields)
        or [t for f in fields for t in f.split()] != tokens
        or not fields[0]
    ):
        return None
    return fields


def sniff_statoil_survey_text(lines: Iterable[str]) -> bool:
    """Content check shared by the profile and upload intake: export title, a ``SURVEY LIST``
    section and at least one plausible nine-number station row after it."""
    titled = listed = False
    seen = 0
    for line in lines:
        seen += 1
        if seen > DETECT_LINES:
            break
        text = line.strip()
        if not titled:
            titled = seen <= TITLE_LINES and text.startswith(TITLE)
            continue
        if not listed:
            listed = text == LIST_TITLE
            continue
        tokens = text.split()
        if len(tokens) == NCOL and all(_is_numeric_token(t) for t in tokens):
            return True
    return False


def _loc(line: int, column: str | None = None, record: int | None = None) -> Locator:
    loc: Locator = {"kind": "text", "line_start": line, "line_end": line}
    if record is not None:
        loc["logical_record"] = record
    if column:
        loc["column_name"] = column
    return loc


def _canon_unit(token: str) -> str | None:
    unit = token.strip().replace("°", "deg")
    return None if not unit or "\ufffd" in unit else unit


def _units_row(line: str) -> list[tuple[str | None, str | None]] | None:
    """(unit, reference) per column from ``m RKB   deg ...``; None unless nine cells."""
    cells = [c for c in _GAP.split(line.replace("\t", "  ").strip()) if c.strip()]
    if len(cells) != NCOL:
        return None
    out: list[tuple[str | None, str | None]] = []
    for cell in cells:
        unit, _, rest = cell.strip().partition(" ")
        out.append((_canon_unit(unit), rest.strip() or None))
    return out


def _dms(text: str) -> tuple[float | None, str | None]:
    """Decimal degrees of ``58° 26' 29.8941 N`` or (None, reason); the original stays verbatim."""
    m = _LATLON.match(text.strip())
    if not m:
        return None, "not a degree/minute/second coordinate"
    deg, minute, sec, hemi = int(m[1]), int(m[2]), float(m[3]), m[4]
    limit = 90 if hemi in "NS" else 180
    if minute >= 60 or sec >= 60 or deg > limit or (deg == limit and (minute or sec)):
        return None, "degree/minute/second value out of range"
    value = deg + minute / 60 + sec / 3600
    return (-value if hemi in "SW" else value), None


class StatoilSurveyTextProfile:
    name = "text_statoil_survey_export"
    version = "1"
    method = "native_text_statoil_survey"
    families = ("text", "csv")

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        if format_family not in self.families or sniff_path(path) is None:
            return False
        try:
            with open_text(path) as handle:
                return sniff_statoil_survey_text(handle)
        except (OSError, ValueError):
            return False

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        encoding = sniff_path(path)
        if encoding is None:
            raise ProfileError("profile_mismatch", "file is not decodable text")
        lines: list[str] = []
        with open_text(path) as handle:
            for raw in handle:
                if len(lines) >= MAX_TEXT_LINES:
                    raise ProfileError("too_many_lines", f"text has over {MAX_TEXT_LINES} lines")
                lines.append(raw.rstrip("\r\n"))
        if not sniff_statoil_survey_text(lines):
            raise ProfileError("profile_mismatch", "no Statoil survey export header and rows found")
        findings: list[Finding] = []
        first_list = next(i for i, ln in enumerate(lines) if ln.strip() == LIST_TITLE)
        title_no = next(i + 1 for i, ln in enumerate(lines) if ln.strip().startswith(TITLE))
        head = self._header(lines[:first_list], findings, title_no)

        # ---- column header rows -------------------------------------------------------------
        idx = first_list + 1
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        titles = _header_titles(lines[idx]) if idx < len(lines) else []
        if titles != list(COLUMN_TITLES):
            if sorted(titles) == sorted(COLUMN_TITLES):
                raise ProfileError(
                    "profile_mismatch", "survey column titles are not in the expected order"
                )
            raise ProfileError("profile_mismatch", "survey column titles were not recognized")
        starts = _starts(lines[idx])
        title_line = idx + 1
        idx += 1
        units: list[tuple[str | None, str | None]] | None = None
        units_line = title_line
        while idx < len(lines) and not lines[idx].strip():
            idx += 1
        if idx < len(lines):
            first_tok = lines[idx].split()[:1]
            if first_tok and not _is_numeric_token(first_tok[0]):
                units = _units_row(lines[idx])
                units_line = idx + 1
                idx += 1
        body_start = idx
        md_ref, tvd_ref = self._references(units, head, findings, units_line)
        azi_ref = head["azi_ref"]
        crs_ref = head["crs_ref"]
        subject = head["subject"]
        report_time = head["report_time"]

        records: list[Rec] = [
            Rec(
                "survey_report_header",
                subject,
                _loc(title_no),
                head["attrs"],
                head["survey_time"],
                report_time,
            )
        ]
        location = self._location(head, subject, report_time, findings)
        if location is not None:
            records.append(location)

        # ---- program + stations -------------------------------------------------------------
        skipped: list[int] = []
        repeated: list[int] = []
        stations = program = 0
        prev_md: float | None = None
        non_mono: list[int] = []
        bad_tvd: list[int] = []
        unknown_values = 0
        for entry in head["program"]:
            program += 1
            ln = entry["line"]
            m = entry["match"]
            unit = units[0][0] if units else None
            pattrs: list[Attr] = [
                quantity_attr(
                    f"survey_program_entry.{col}",
                    _loc(ln, col, program),
                    m[grp],
                    unit,
                    reference=md_ref,
                )
                for grp, col in (("from", "from_md"), ("to", "to_md"))
            ]
            pattrs += [
                text_attr("survey_program_entry.flag", _loc(ln, "flag", program), "H"),
                text_attr(
                    "survey_program_entry.survey_name", _loc(ln, "survey_name", program), m["name"]
                ),
                text_attr(
                    "survey_program_entry.description", _loc(ln, "description", program), m["desc"]
                ),
            ]
            records.append(
                Rec(
                    "survey_program_entry",
                    subject,
                    _loc(ln, None, program),
                    pattrs,
                    None,
                    report_time,
                )
            )
        in_repeat = False
        for pos in range(body_start, len(lines)):
            line_no = pos + 1
            text = lines[pos]
            if text.strip() == LIST_TITLE:
                in_repeat = True
                repeated.append(line_no)
                skipped.append(line_no)
                continue
            fields = split_station_row(text, starts)
            if fields is not None and not in_repeat:
                stations += 1
                if stations > MAX_RECORDS:
                    raise ProfileError("too_many_records", "too many survey rows")
                attrs: list[Attr] = []
                for ci, (key, tok) in enumerate(zip(COLUMNS, fields, strict=True)):
                    unit, ref = units[ci] if units else (None, None)
                    if key == "md":
                        ref = md_ref
                    elif key == "tvd":
                        ref = tvd_ref
                    elif key == "azi":
                        ref = azi_ref
                    elif key.startswith("utm"):
                        ref = crs_ref
                    else:
                        ref = None
                    attr = quantity_attr(
                        f"trajectory_station.{key}",
                        _loc(line_no, key, stations),
                        tok,
                        unit,
                        reference=ref,
                    )
                    unknown_values += attr.number is None
                    attrs.append(attr)
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
            tokens = text.split()
            if tokens and all(_is_numeric_token(t) for t in tokens) and len(tokens) >= 6:
                skipped.append(line_no)  # numeric row that is not nine columns: never dropped
                continue
            if in_repeat and fields is not None:
                skipped.append(line_no)
        for i, r in enumerate(records):
            r.ordinal = i
        self._station_findings(
            findings, records, head, units, units_line, stations, bad_tvd, non_mono
        )
        if unknown_values:
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "warning",
                    f"{unknown_values} station value(s) are blank or not plain numbers; "
                    "kept unknown (never zero, decimal commas are not guessed).",
                    "station_values_unknown",
                    ["trajectory_station.md"],
                    blocked=["calculation"],
                )
            )
        total = sum(1 for ln in lines if ln.strip())
        reasons: list[str] = []
        if skipped:
            n_rep = len(repeated)
            n_bad = len(skipped) - n_rep
            parts = []
            if n_rep:
                parts.append(f"{n_rep} repeated SURVEY LIST section(s) were not merged")
            if n_bad:
                parts.append(
                    f"{n_bad} numeric row(s) in the survey section do not have nine columns "
                    "or belong to a repeated section and were not extracted"
                )
            reasons.append("; ".join(parts))
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "warning",
                    reasons[-1] + ".",
                    "text_rows_skipped",
                    locators=[_loc(n) for n in skipped[:5]],
                    blocked=["claim_acceptance"],
                )
            )
        for ln_no in head["bad_program"]:
            skipped.append(ln_no)
        if head["bad_program"]:
            reasons.append(
                f"{len(head['bad_program'])} Survey Program line(s) did not match the "
                "'H <from> - <to> <name> : <description>' layout and were not extracted"
            )
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "warning",
                    reasons[-1] + ".",
                    "program_rows_skipped",
                    locators=[_loc(n) for n in head["bad_program"][:5]],
                )
            )
        cov = CoverageOut(
            "line",
            total - len(skipped),
            total,
            [f"L{n}" for n in sorted(skipped)[:200]],
            reasons,
        )
        return ProfileOutput(
            records,
            findings,
            cov,
            "succeeded" if cov.complete else "partial",
            {
                "text_encoding": encoding,
                "lines": len(lines),
                "stations": stations,
                "program_rows": program,
                "has_surface_location": location is not None,
                "skipped_rows": len(skipped) - len(head["bad_program"]),
                "unrecognized_header_lines": head["unrecognized"][:50],
            },
        )

    # -------------------------------------------------------------------------------------
    def _references(
        self,
        units: list[tuple[str | None, str | None]] | None,
        head: dict[str, Any],
        findings: list[Finding],
        units_line: int,
    ) -> tuple[str | None, str | None]:
        """MD/TVD reference from the units row (``m RKB``) with the Datum Name stated verbatim."""
        datum = head["datum_text"]
        refs: list[str | None] = []
        for ci in (0, 3):
            token = units[ci][1] if units else None
            if token and token.upper() == "RKB" and datum:
                token = f"{token} (Datum Name: {datum})"
            refs.append(token)
        if refs[0] is None or refs[1] is None:
            findings.append(
                Finding(
                    MISSING_REFERENCE,
                    "warning",
                    "the survey units row does not state the MD/TVD reference (e.g. 'm RKB'); "
                    "it is not assumed.",
                    "missing:md_tvd_reference",
                    ["trajectory_station.md", "trajectory_station.tvd"],
                    [0],
                    [_loc(units_line)],
                    ["placement", "calculation"],
                )
            )
        elif not datum:
            findings.append(
                Finding(
                    MISSING_REFERENCE,
                    "warning",
                    "the header states no Datum Name, so the RKB elevation is unknown.",
                    "missing:datum_name",
                    ["survey_report_header.reference_elevation"],
                    [0],
                    [_loc(units_line)],
                    ["placement", "calculation"],
                )
            )
        if units is None or any(u is None for u, _ in units):
            findings.append(
                Finding(
                    MISSING_UNIT,
                    "warning",
                    "the survey units row is missing or does not state a unit for every column; "
                    "station values keep no unit (never assumed).",
                    "missing:station_units",
                    ["trajectory_station.md", "trajectory_station.tvd"],
                    [],
                    [_loc(units_line)],
                    ["placement", "calculation"],
                )
            )
        return refs[0], refs[1]

    def _header(self, head: list[str], findings: list[Finding], title_no: int) -> dict[str, Any]:
        found: dict[str, list[tuple[int, str, str]]] = {}
        program: list[dict[str, Any]] = []
        bad_program: list[int] = []
        unrecognized: list[str] = []
        in_program = False
        for i, raw in enumerate(head):
            line_no = i + 1
            text = raw.strip()
            if not text or set(text) <= {"-"} or text.startswith(TITLE):
                in_program = in_program and bool(text) and not set(text) <= {"-"}
                continue
            if in_program:
                m = _PROGRAM.match(text)
                if m:
                    program.append({"line": line_no, "match": m})
                    continue
                if _LABEL.match(text) and _norm(_LABEL.match(text).group(1)) in _KNOWN:  # type: ignore[union-attr]
                    in_program = False
                else:
                    bad_program.append(line_no)
                    continue
            m = _LABEL.match(text)
            if not m:
                unrecognized.append(f"L{line_no}")
                continue
            label = _norm(m.group(1))
            if label == "survey program":
                in_program = True
                continue
            if label not in _KNOWN:
                unrecognized.append(f"L{line_no}")
                continue
            if m.group(2):
                found.setdefault(label, []).append((line_no, m.group(2), raw))
        for label, hits in found.items():
            distinct = list(dict.fromkeys(v for _, v, _ in hits))
            if len(distinct) > 1:
                findings.append(
                    Finding(
                        REFERENCE_CONFLICT if label in _REF_CONFLICT_LABELS else IDENTITY_MISMATCH,
                        "error",
                        f"the file states more than one {label}: {', '.join(distinct[:3])}.",
                        f"header_conflict:{label}",
                        [],
                        [0],
                        [_loc(n) for n, _, _ in hits[:5]],
                        ["placement", "calculation"],
                    )
                )

        def first(label: str) -> tuple[int, str] | None:
            hit = found.get(label)
            return (hit[0][0], hit[0][1]) if hit else None

        def value(label: str) -> str | None:
            hit = first(label)
            return hit[1] if hit else None

        well, bore = value("well name"), value("wellbore name")
        survey_name = value("survey name")
        if not well and not bore:
            findings.append(
                Finding(
                    EXTRACTION_PARTIAL,
                    "warning",
                    "the header states neither a WELL NAME nor a WELLBORE NAME.",
                    "missing:well_identity",
                    [],
                    [0],
                    [_loc(title_no)],
                    ["claim_acceptance"],
                )
            )
        subject: dict[str, Any] = {
            "well_name": well,
            "wellbore_name": bore,
            "wellbore_label": bore,
            "well_key": None,
            "design": survey_name,
            "field": value("field"),
        }
        attrs: list[Attr] = []
        for label, key in _TEXT_LABELS.items():
            hit = first(label)
            if hit is None:
                continue
            attrs.append(text_attr(f"survey_report_header.{key}", _loc(hit[0], key), hit[1]))
        for label, key in _QUANTITY_LABELS.items():
            hit = first(label)
            if hit is None:
                continue
            attrs.append(self._quantity(f"survey_report_header.{key}", hit[0], key, hit[1]))
        # reference elevation from "Datum Name: Rotary Table(54.90m)"
        datum_text = value("datum name")
        datum_hit = first("datum name")
        if datum_text and datum_hit:
            dm = _DATUM.match(datum_text)
            if dm:
                elev = quantity_attr(
                    "survey_report_header.reference_elevation",
                    _loc(datum_hit[0], "reference_elevation"),
                    dm["n"],
                    _canon_unit(dm["u"]),
                    reference=dm["name"] or None,
                )
                elev.original_text = f"({dm['n']}{dm['u']})"
                attrs.append(elev)
            else:
                findings.append(
                    Finding(
                        MISSING_REFERENCE,
                        "warning",
                        "the Datum Name does not state a parseable elevation "
                        "('<name>(<value><unit>)').",
                        "datum_elevation_unparsed",
                        ["survey_report_header.reference_elevation"],
                        [0],
                        [_loc(datum_hit[0])],
                        ["placement", "calculation"],
                    )
                )
        # North reference -> azimuth reference
        north = value("north reference")
        azi_ref: str | None = None
        if north:
            word = north.lower().split()[0]
            azi_ref = f"{word} north" if word in ("grid", "true", "magnetic") else north
        else:
            findings.append(
                Finding(
                    MISSING_REFERENCE,
                    "warning",
                    "the header does not state the grid/true north reference.",
                    "missing:north_reference",
                    ["survey_report_header.north_reference"],
                    [0],
                    [_loc(title_no)],
                    ["calculation", "placement"],
                )
            )
        zone, geo = value("map-zone"), value("geo datum")
        crs_ref = None
        if zone and geo:
            crs_ref = f"Map-Zone: {zone}; Geo Datum: {geo}"
        else:
            findings.append(
                Finding(
                    MISSING_REFERENCE,
                    "warning",
                    "the header does not state both the Map-Zone and the Geo Datum; no coordinate "
                    "reference is assumed.",
                    "missing:map_zone_geo_datum",
                    ["survey_report_header.map_zone", "survey_report_header.geo_datum"],
                    [0],
                    [_loc(title_no)],
                    ["placement"],
                )
            )
        # survey status: only explicit words in the survey name; never the file name
        name_hit = first("survey name")
        status_loc = _loc(name_hit[0] if name_hit else title_no, "survey_status")
        planned = bool(survey_name and _STATUS_PLAN.search(survey_name))
        actual = bool(survey_name and _STATUS_ACTUAL.search(survey_name))
        key = "survey_report_header.survey_status"
        if planned != actual:
            status = Attr(
                key,
                status_loc,
                original_text=survey_name,
                text="planned" if planned else "as_built",
            )
        else:
            conflict = planned and actual
            reason = (
                "the survey name states both planned and as-built wording"
                if conflict
                else "the file does not state whether the survey is planned or as-built"
            )
            status = Attr(key, status_loc, original_text=survey_name, unknown_reason=reason)
            findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "warning" if conflict else "info",
                    (
                        f"the survey name '{survey_name}' states both planned and as-built "
                        "wording; no status is asserted."
                        if conflict
                        else "the file does not state whether this survey is planned or as-built "
                        f"(Survey Name: {survey_name or 'not stated'}); the file name is only a "
                        "hint and was not used. Planned and as-built surveys must not be mixed."
                    ),
                    "survey_status_conflict" if conflict else "survey_status_unstated",
                    [key, "survey_report_header.survey_name"],
                    [0],
                    [status_loc],
                    ["temporal_state"],
                )
            )
        attrs.append(status)
        # dates: extraction date is report time, survey date effective time (day precision)
        survey_date, extraction = value("survey date"), value("extraction date")
        day_first = any(
            (m := _DATE.match(d or "")) is not None and int(m[1]) > 12
            for d in (survey_date, extraction)
        )

        date_findings: list[Finding] = []

        def to_time(text: str | None, label: str, label_key: str) -> Any:
            if not text:
                return None
            m = _DATE.match(text)
            if not (m and day_first):
                return event_time(text, label)
            hit = first(label_key)
            loc = [_loc(hit[0])] if hit else []
            try:
                date(int(m[3]), int(m[2]), int(m[1]))
            except ValueError:
                date_findings.append(
                    Finding(
                        SUSPICIOUS_VALUE,
                        "warning",
                        f"{label} '{text}' is not a valid calendar date (day-first); kept as "
                        "written with unknown precision.",
                        f"date_invalid:{label_key}",
                        [f"survey_report_header.{label_key.replace(' ', '_')}"],
                        [0],
                        loc,
                        ["temporal_state"],
                    )
                )
                return EventTime(text, "unknown", False, label)
            if int(m[1]) <= 12:
                date_findings.append(
                    Finding(
                        TEMPORAL_AMBIGUITY,
                        "info",
                        f"{label} '{text}' is read day-first because another date in the file "
                        "has a day above 12; the order is inferred, not stated.",
                        f"date_order_inferred:{label_key}",
                        [f"survey_report_header.{label_key.replace(' ', '_')}"],
                        [0],
                        loc,
                    )
                )
            return event_time(f"{m[3]}-{m[2]}-{m[1]}", label)

        survey_time = to_time(survey_date, "Survey Date", "survey date")
        report_time = to_time(extraction, "Extraction Date", "extraction date")
        findings.extend(date_findings)
        if survey_time and survey_time.precision == "unknown" and not day_first:
            findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "warning",
                    f"Survey Date '{survey_date}' has no unambiguous day/month order; kept as "
                    "written with unknown precision.",
                    "survey_date_ambiguous",
                    ["survey_report_header.survey_date"],
                    [0],
                    [_loc(first("survey date")[0])] if first("survey date") else [],  # type: ignore[index]
                    ["temporal_state"],
                )
            )
        return {
            "subject": subject,
            "attrs": attrs,
            "program": program,
            "bad_program": bad_program,
            "unrecognized": unrecognized,
            "datum_text": datum_text,
            "azi_ref": azi_ref,
            "crs_ref": crs_ref,
            "survey_time": survey_time,
            "report_time": report_time,
            "found": found,
            "title_no": title_no,
        }

    @staticmethod
    def _quantity(key: str, line_no: int, column: str, raw: str) -> Attr:
        m = _QUANTITY.match(raw.strip())
        if not m:
            return quantity_attr(key, _loc(line_no, column), raw, None)
        attr = quantity_attr(key, _loc(line_no, column), m["n"], _canon_unit(m["u"]))
        attr.original_text = raw.strip()
        return attr

    def _location(
        self,
        head: dict[str, Any],
        subject: dict[str, Any],
        report_time: Any,
        findings: list[Finding],
    ) -> Rec | None:
        found = head["found"]
        stated = [lab for lab in _SURFACE_LABELS if lab in found]
        if not stated:
            findings.append(
                Finding(
                    MISSING_REFERENCE,
                    "warning",
                    "the header states no surface location (Surface EW/NS, latitude, longitude); "
                    "the wellbore stays unlocated.",
                    "missing:surface_location",
                    ["well_surface_location.easting", "well_surface_location.northing"],
                    [0],
                    [_loc(head["title_no"])],
                    ["placement"],
                )
            )
            return None
        attrs: list[Attr] = []
        first_line = min(found[lab][0][0] for lab in stated)
        for label, key in (("surface ew", "easting"), ("surface ns", "northing")):
            if label in found:
                line_no, raw, _ = found[label][0]
                a = self._quantity(f"well_surface_location.{key}", line_no, key, raw)
                a.reference = head["crs_ref"]
                attrs.append(a)
            else:
                attrs.append(
                    Attr(
                        f"well_surface_location.{key}",
                        _loc(first_line, key),
                        unknown_reason=f"the header does not state '{label.title()}'",
                    )
                )
        for label, key in (("surface latitude", "latitude"), ("surface longitude", "longitude")):
            akey = f"well_surface_location.{key}"
            if label not in found:
                continue
            line_no, raw, _ = found[label][0]
            deg, reason = _dms(raw)
            expect = "NS" if key == "latitude" else "EW"
            if reason is None and raw.strip()[-1] not in expect:
                deg, reason = None, f"hemisphere is not one of {expect}"
            attr = Attr(
                akey,
                _loc(line_no, key),
                original_text=raw,
                text=raw.strip(),
                unit="deg",
                unit_status="stated",
                unknown_reason=reason,
            )
            if deg is not None:
                attr.normalized_number, attr.normalized_unit = deg, "deg"
            else:
                attr.validation_state = "invalid"
                findings.append(
                    Finding(
                        SUSPICIOUS_VALUE,
                        "warning",
                        f"Surface {key} '{raw}' could not be decoded: {reason}.",
                        f"surface_{key}_undecoded",
                        [akey],
                        [],
                        [_loc(line_no, key)],
                        ["placement"],
                    )
                )
            attrs.append(attr)
        for label, key in (
            ("map-zone", "map_zone"),
            ("geo datum", "geo_datum"),
            ("system datum", "system_datum"),
            ("north reference", "north_reference"),
        ):
            if label in found:
                line_no, raw, _ = found[label][0]
                attrs.append(text_attr(f"well_surface_location.{key}", _loc(line_no, key), raw))
        if any(a.key.endswith(("easting", "northing")) and a.number is None for a in attrs):
            findings.append(
                Finding(
                    MISSING_REFERENCE,
                    "warning",
                    "the surface easting/northing is incomplete or not a plain number; the "
                    "wellbore stays unlocated.",
                    "surface_location_incomplete",
                    ["well_surface_location.easting", "well_surface_location.northing"],
                    [1],
                    [_loc(first_line)],
                    ["placement"],
                )
            )
        findings.append(
            Finding(
                MISSING_REFERENCE,
                "info",
                "latitude/longitude carry no datum of their own and the map zone / geodetic "
                "datum text is kept as stated; no EPSG code is assumed.",
                "surface_crs_not_resolved",
                ["well_surface_location.map_zone", "well_surface_location.geo_datum"],
                [1],
                [_loc(first_line)],
                ["placement"],
            )
        )
        return Rec("well_surface_location", subject, _loc(first_line), attrs, None, report_time)

    def _station_findings(
        self,
        findings: list[Finding],
        records: list[Rec],
        head: dict[str, Any],
        units: list[tuple[str | None, str | None]] | None,
        units_line: int,
        stations: int,
        bad_tvd: list[int],
        non_mono: list[int],
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
                "stations carry no acquisition time; the Survey Date is kept as the survey's "
                "effective date and the Extraction Date as report time.",
                "survey_no_station_time",
                ["trajectory_station.md"],
                [0],
                blocked=["temporal_state"],
            )
        )
        st = [r for r in records if r.kind == "trajectory_station"]
        if not st:
            return
        self._cross_checks(findings, records, head, st)

    @staticmethod
    def _num(rec: Rec, key: str) -> float | None:
        a = rec.attr(f"trajectory_station.{key}")
        return a.number if a is not None else None

    def _cross_checks(
        self, findings: list[Finding], records: list[Rec], head: dict[str, Any], st: list[Rec]
    ) -> None:
        def header_number(key: str) -> float | None:
            hdr = records[0].attr(f"survey_report_header.{key}")
            return hdr.number if hdr is not None else None

        surface = next((r for r in records if r.kind == "well_surface_location"), None)
        num = self._num
        first, last = st[0], st[-1]
        tol = 0.0051
        if surface is not None:
            se, sn = (surface.attr(f"well_surface_location.{k}") for k in ("easting", "northing"))
            e0, n0 = num(first, "utmEasting"), num(first, "utmNorthing")
            if (
                se
                and sn
                and None not in (se.number, sn.number, e0, n0)
                and (abs(se.number - e0) > tol or abs(sn.number - n0) > tol)  # type: ignore[operator]
            ):
                findings.append(
                    Finding(
                        REFERENCE_CONFLICT,
                        "warning",
                        "the first station UTM E/N differs from the stated surface location.",
                        "check:first_station_vs_surface",
                        ["trajectory_station.utmEasting", "well_surface_location.easting"],
                        [first.ordinal, surface.ordinal],
                        [first.locator, surface.locator],
                        ["placement"],
                    )
                )
        # Not checked: UTM minus offset. On the real exports it is NOT constant along the survey
        # (offset reference/rotation unstated), so a translation check would only raise noise.
        # last station vs Bottom Hole header
        pairs = (
            ("bottom_hole_md", "md", "MD"),
            ("bottom_hole_tvd", "tvd", "TVD"),
            ("bottom_hole_ew", "utmEasting", "E/W"),
            ("bottom_hole_ns", "utmNorthing", "N/S"),
        )
        diffs: list[str] = []
        for hkey, skey, name in pairs:
            hv, sv = header_number(hkey), num(last, skey)
            if hv is not None and sv is not None and abs(hv - sv) > tol:
                diffs.append(f"{name} {hv:g} vs {sv:g}")
        if diffs:
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "warning",
                    "the last station differs from the Bottom Hole header: " + ", ".join(diffs),
                    "check:last_station_vs_bottom_hole",
                    ["survey_report_header.bottom_hole_md", "trajectory_station.md"],
                    [0, last.ordinal],
                    [records[0].locator, last.locator],
                    ["calculation"],
                )
            )
        # kick-off depth vs first station, datum elevation vs KB-MSL
        kod, md0 = header_number("kick_off_depth"), num(first, "md")
        if kod is not None and md0 is not None and abs(kod - md0) > tol:
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "warning",
                    f"Kick Off Depth {kod:g} differs from the first station MD {md0:g}.",
                    "check:kick_off_vs_first_station",
                    ["survey_report_header.kick_off_depth", "trajectory_station.md"],
                    [0, first.ordinal],
                    [records[0].locator, first.locator],
                    ["calculation"],
                )
            )
        elev, kb = header_number("reference_elevation"), header_number("kb_msl")
        if elev is not None and kb is not None and abs(elev - kb) > tol:
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "error",
                    f"Datum Name elevation {elev:g} differs from KB-MSL {kb:g}.",
                    "check:datum_vs_kb_msl",
                    ["survey_report_header.reference_elevation", "survey_report_header.kb_msl"],
                    [0],
                    [records[0].locator],
                    ["placement", "calculation"],
                )
            )
        # station MD range vs Survey Program ranges (1 m rounding tolerance; info only)
        prog = [r for r in records if r.kind == "survey_program_entry"]
        lows = [
            a.number
            for r in prog
            if (a := r.attr("survey_program_entry.from_md")) and a.number is not None
        ]
        highs = [
            a.number
            for r in prog
            if (a := r.attr("survey_program_entry.to_md")) and a.number is not None
        ]
        mds = [v for r in st if (v := num(r, "md")) is not None]
        if lows and highs and mds and (min(mds) < min(lows) - 1.0 or max(mds) > max(highs) + 1.0):
            findings.append(
                Finding(
                    INTERVAL_CONFLICT,
                    "info",
                    f"station MD range {min(mds):g}-{max(mds):g} extends beyond the Survey "
                    f"Program coverage {min(lows):g}-{max(highs):g}.",
                    "check:md_range_vs_program",
                    ["trajectory_station.md", "survey_program_entry.from_md"],
                    [0],
                    [records[0].locator],
                )
            )

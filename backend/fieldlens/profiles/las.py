"""LAS 2.0 well-log profile (small, safe, line-oriented reader; no third-party dependency).

Stores the header claims, the curve inventory and a per-curve summary (valid/null counts,
min/max, data line range) in ``extracted_record``; every claim points at its LAS section and
line. The full-resolution samples travel beside the records (``ProfileOutput.series``, one
``AxisOut`` per data block, NULL sentinels converted to NaN) and are persisted by the runner in
the run-finalizing transaction. Data lines are parsed once into compact float64 arrays (no
per-token strings are kept). Declared header values (STRT/STOP/STEP/NULL) are compared with the
data and conflicts are reported, never reconciled silently."""

from __future__ import annotations

import re
from array import array
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from .common import event_time, parse_number, quantity_attr, text_attr, well_key
from .types import (
    IDENTITY_MISMATCH,
    MAX_SERIES_CELLS,
    MAX_TEXT_LINES,
    MISSING_REFERENCE,
    MISSING_UNIT,
    REFERENCE_CONFLICT,
    SUSPICIOUS_VALUE,
    TEMPORAL_AMBIGUITY,
    Attr,
    AxisOut,
    CoverageOut,
    CurveOut,
    Finding,
    Locator,
    ParseContext,
    ProfileError,
    ProfileOutput,
    ProfileStatus,
    Rec,
)

_HEADER = re.compile(r"^\s*([^\s.:]*)\s*\.([^\s:]*)\s+(.*?)\s*:(.*)$")
MAX_PARSE_CELLS = 100_000_000  # parsed index+value cells held at once (about 800 MB of float64)
_DEPTH_NAMES = frozenset({"DEPT", "DEPTH", "MD", "TVD", "TVDSS", "MDEPTH"})
_DEPTH_UNITS = frozenset({"m", "ft", "f", "feet", "foot", "meter", "meters", "metre", "metres"})
_TIME_NAMES = frozenset({"TIME", "ETIM", "TIMEMS", "TIME_UTC", "DATETIME"})
_TIME_UNITS = frozenset({"s", "sec", "secs", "ms", "min", "hr", "h", "hhmmss", "d", "day", "days"})
_SECTIONS = {
    "V": "version",
    "W": "well",
    "C": "curve",
    "P": "parameter",
    "O": "other",
    "A": "data",
}


def _loc(
    section: str, start: int, end: int | None = None, mnemonic: str | None = None, **kw: Any
) -> Locator:
    loc: Locator = {
        "kind": "text",
        "line_start": start,
        "line_end": end or start,
        "las_section": section,
    }
    if mnemonic:
        loc["las_mnemonic"] = mnemonic
    loc.update(kw)
    return loc


MAX_SKIPPED_LINE_RATIO = 0.10


def _series_refusal(
    curve_names: list[str], data_header: list[str], a_marker: str, skipped: int, n_data: int
) -> str | None:
    """Why the samples are not a trustworthy series (None = store them). The data marker must be
    exactly ``~A`` (``~Ascii Log Data`` style text makes the header tokens free text, so words
    would become curve names and data the index), the ~A header must name as many columns as the
    ~C block declares curves (a WRAP YES layout breaks this), and at most 10% of the data lines
    may have been skipped as unparseable. Differing names with the same count (truncated
    fixed-width ~A headers) stay a REFERENCE_CONFLICT finding and the ~A names are kept."""
    if a_marker != "~A":
        return f"the data section header '{a_marker}' is free text, not a column header"
    if curve_names and len(curve_names) != len(data_header):
        return (
            f"the ~A header names {len(data_header)} column(s) but the ~C block declares "
            f"{len(curve_names)} curve(s), so the data layout is not established"
        )
    if n_data and skipped / n_data > MAX_SKIPPED_LINE_RATIO:
        return (
            f"{skipped} of {n_data} data lines were skipped as unparseable "
            f"(more than {MAX_SKIPPED_LINE_RATIO:.0%})"
        )
    return None


def classify_index(name: str, unit: str) -> str:
    """depth | time | unknown from the index mnemonic and stated unit (a hint, not a datum)."""
    if name.strip().upper() in _DEPTH_NAMES or unit.strip().lower() in _DEPTH_UNITS:
        return "depth"
    if name.strip().upper() in _TIME_NAMES or unit.strip().lower() in _TIME_UNITS:
        return "time"
    return "unknown"


def looks_like_las(path: Path) -> bool:
    with path.open("rb") as h:
        head = h.read(4096).decode("latin-1", "replace")
    lines = [ln.strip().upper() for ln in head.splitlines()]
    return any(ln.startswith("~V") for ln in lines[:20])


def _parse_date(text: str) -> str | None:
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


class LasProfile:
    name = "las_2_0"
    version = "2"
    method = "native_text_las"
    families = ("las",)

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        return format_family == "las" and looks_like_las(path)

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        section = ""
        items: dict[str, list[tuple[str, str, str, str, int]]] = {}
        findings: list[Finding] = []
        data_header: list[str] = []
        data_start = 0
        n_lines = 0
        a_marker = "~A"
        # data lines are parsed into compact arrays as they are read (see ingest below)
        cols: list[array[float]] = []
        lines: array[int] = array("i")
        ncols = 0
        n_data = 0
        first_data_line = last_data_line = 0
        pending: list[tuple[int, list[str]]] = []
        bad_width: list[int] = []
        bad_token: list[int] = []

        def ingest(ln: int, toks: list[str]) -> None:
            if len(toks) != ncols:
                bad_width.append(ln)
                return
            vals = [parse_number(t) for t in toks]
            if None in vals:
                bad_token.append(ln)
                return
            lines.append(ln)
            for col, v in zip(cols, vals, strict=True):
                col.append(v)  # type: ignore[arg-type]
            if len(lines) * ncols > MAX_PARSE_CELLS:
                raise ProfileError("too_many_samples", "LAS data exceeds the sample limit")

        with path.open("r", encoding="latin-1", errors="replace") as handle:
            for n_lines, raw in enumerate(handle, 1):
                if n_lines > MAX_TEXT_LINES:
                    raise ProfileError("too_many_lines", "LAS exceeds the line limit")
                line = raw.rstrip("\r\n")
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                if s.startswith("~"):
                    section = _SECTIONS.get(s[1:2].upper(), "unknown")
                    if section == "data":
                        data_header = s[2:].split()
                        data_start = n_lines
                        a_marker = s.split()[0].upper()
                    continue
                if section == "data":
                    n_data += 1
                    first_data_line = first_data_line or n_lines
                    last_data_line = n_lines
                    if not ncols:
                        names = data_header or [c[0] for c in items.get("curve", [])]
                        if names:
                            ncols = len(names)
                            cols = [array("d") for _ in names]
                    if ncols:
                        ingest(n_lines, s.split())
                    else:
                        pending.append((n_lines, s.split()))
                elif section:
                    m = _HEADER.match(line)
                    if m:
                        items.setdefault(section, []).append(
                            (
                                m.group(1).strip(),
                                m.group(2).strip(),
                                m.group(3).strip(),
                                m.group(4).strip(),
                                n_lines,
                            )
                        )
                    else:
                        findings.append(
                            Finding(
                                "EXTRACTION_PARTIAL",
                                "info",
                                f"line {n_lines} in the {section} section is not a header item.",
                                f"las_unparsed:{section}:{n_lines}",
                                locators=[_loc(section, n_lines)],
                            )
                        )
        if not data_header and items.get("curve"):
            # LAS 2.0 allows a bare ``~A``: the ~C section then names the data columns.
            data_header = [c[0] for c in items["curve"]]
        if not data_header or "version" not in items:
            raise ProfileError("profile_mismatch", "LAS lacks ~V or ~A section")
        if pending:  # data lines that preceded any column names (non-standard order)
            ncols = len(data_header)
            cols = [array("d") for _ in data_header]
            for ln, toks in pending:
                ingest(ln, toks)
            pending = []
        records: list[Rec] = []
        wellkv: dict[str, tuple[str, str, str, int]] = {}
        header_attrs: list[Attr] = []
        for mnem, _unit, value, _desc, ln in items.get("version", []):
            header_attrs.append(
                text_attr(
                    f"las_header.version.{mnem.lower()}", _loc("version", ln, mnemonic=mnem), value
                )
            )
        stop_dups: list[int] = []
        for mnem, unit, value, desc, ln in items.get("well", []):
            key = mnem.upper()
            if key in wellkv:
                stop_dups.append(ln)
                findings.append(
                    Finding(
                        REFERENCE_CONFLICT,
                        "warning",
                        f"well-section mnemonic {mnem} is declared again at line {wellkv[key][3]} and line {ln}; both kept.",
                        f"las_dup_mnemonic:{key}:{ln}",
                        [f"las_header.well.{key.lower()}"],
                        locators=[
                            _loc("well", wellkv[key][3], mnemonic=mnem),
                            _loc("well", ln, mnemonic=mnem),
                        ],
                        blocked=["claim_acceptance"],
                    )
                )
                continue
            wellkv[key] = (unit, value, desc, ln)
            if mnem and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mnem):
                findings.append(
                    Finding(
                        "UNKNOWN_CODE",
                        "warning",
                        f"non-standard mnemonic '{mnem}' at line {ln}; kept verbatim.",
                        f"las_bad_mnemonic:{ln}",
                        [f"las_header.well.{mnem}"],
                        locators=[_loc("well", ln, mnemonic=mnem)],
                    )
                )
            if key in ("STRT", "STOP", "STEP", "NULL"):
                header_attrs.append(
                    quantity_attr(
                        f"las_header.{key.lower()}",
                        _loc("well", ln, mnemonic=mnem),
                        value,
                        unit or None,
                        unit_required=key != "NULL",
                    )
                )
            else:
                header_attrs.append(
                    text_attr(
                        f"las_header.well.{key.lower()}", _loc("well", ln, mnemonic=mnem), value
                    )
                )
        well_label = wellkv.get("WELL", ("", "", "", 0))[1] or None
        date_text = wellkv.get("DATE", ("", "", "", 0))[1] or None
        eff = None
        if date_text:
            iso = _parse_date(date_text)
            eff = event_time(iso, "DATE") if iso else event_time(date_text, "DATE")
        subject = {
            "well_name": well_label,
            "wellbore_name": None,
            "well_key": well_key(well_label),
            "field_name": wellkv.get("FLD", ("", "", "", 0))[1] or None,
        }
        head = Rec("las_header", subject, _loc("well", 1, n_lines), header_attrs, eff, None)
        records.append(head)
        if well_label and subject["well_key"] and not re.search(r"-[A-Z]-\d", well_label.upper()):
            findings.append(
                Finding(
                    IDENTITY_MISMATCH,
                    "info",
                    f"WELL label '{well_label}' is not in the canonical 'quad/block-slot-number' form; "
                    f"it is grouped as {subject['well_key']} for coverage only and the original is kept.",
                    "las_label_variant",
                    ["las_header.well.well"],
                    [0],
                    [_loc("well", wellkv["WELL"][3], mnemonic="WELL")],
                )
            )
        if not well_label or not subject["well_key"]:
            findings.append(
                Finding(
                    IDENTITY_MISMATCH,
                    "warning",
                    "WELL is blank or unrecognizable; identity not established.",
                    "las_well_unknown",
                    ["las_header.well.well"],
                    [0],
                    blocked=["claim_acceptance"],
                )
            )
        if date_text and eff is not None and eff.precision == "unknown":
            findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "info",
                    f"log DATE '{date_text}' has an unrecognized format; kept verbatim.",
                    "las_date_format",
                    ["las_header.well.date"],
                    [0],
                    blocked=["temporal_state"],
                )
            )
        elif not date_text:
            findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "info",
                    "log DATE is blank; the log has no effective date.",
                    "las_date_blank",
                    ["las_header.well.date"],
                    [0],
                    blocked=["temporal_state"],
                )
            )
        # curves --------------------------------------------------------------------------
        curves = items.get("curve", [])
        info_names = [c[0] for c in curves]
        if info_names != data_header:
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "error",
                    f"the ~Curve block lists {len(info_names)} curve(s) but the ~A header names {len(data_header)}; "
                    "names/units come from the ~A header, curve-block descriptions are attached only where names match.",
                    "las_curve_block_mismatch",
                    ["las_curve.mnemonic"],
                    [0],
                    [
                        _loc("curve", curves[0][4] if curves else data_start),
                        _loc("data", data_start, mnemonic="~A"),
                    ],
                    ["claim_acceptance"],
                )
            )
        cinfo = {c[0]: c for c in curves}
        ncols = len(data_header)
        null_value = parse_number(wellkv.get("NULL", ("", "", "", 0))[1])
        ok_rows = len(lines)
        line_np = np.frombuffer(lines, dtype=np.int32) if ok_rows else np.zeros(0, np.int32)
        col_np = [np.frombuffer(c, dtype=np.float64) for c in cols] if ok_rows else []
        stats: list[dict[str, Any]] = []
        for i in range(ncols):
            st: dict[str, Any] = {
                "valid": 0,
                "null": 0,
                "min": None,
                "max": None,
                "first": None,
                "last": None,
            }
            if ok_rows:
                arr = col_np[i]
                nulls = (
                    arr == null_value if null_value is not None else np.zeros(ok_rows, dtype=bool)
                )
                good = np.flatnonzero(~nulls)
                st["null"] = int(ok_rows - good.size)
                st["valid"] = int(good.size)
                if good.size:
                    vals_ok = arr[good]
                    st["min"] = float(vals_ok.min())
                    st["max"] = float(vals_ok.max())
                    st["first"] = int(line_np[good[0]])
                    st["last"] = int(line_np[good[-1]])
            stats.append(st)
        index_back: list[int] = []
        steps: set[float] = set()
        first_idx = last_idx = None
        if ok_rows:
            idx_np = col_np[0]
            first_idx, last_idx = float(idx_np[0]), float(idx_np[-1])
            diffs = np.diff(idx_np)
            index_back = [int(x) for x in line_np[1:][diffs <= 0]]
            steps = {round(float(x), 6) for x in np.unique(diffs[diffs > 0])}
        first_line = first_data_line or data_start
        last_line = last_data_line or data_start
        # index unit/reference
        idx_unit = cinfo.get(data_header[0], ("", "", "", "", 0))[1] if data_header else ""
        index_desc = cinfo.get(data_header[0], ("", "", "", "", 0))[3] if data_header else ""
        head.attrs.append(
            Attr(
                "las_header.data_rows",
                _loc("data", first_line, last_line),
                original_text=str(n_data),
                number=float(ok_rows),
                unit_status="not_applicable",
            )
        )
        for key, val in (("first_index", first_idx), ("last_index", last_idx)):
            a = quantity_attr(
                f"las_header.{key}",
                _loc(
                    "data",
                    first_line if key == "first_index" else last_line,
                    mnemonic=data_header[0] if data_header else None,
                ),
                None if val is None else repr(val),
                idx_unit or None,
            )
            a.reference = None
            head.attrs.append(a)
        if not any(
            w in index_desc.lower() for w in ("md", "measured")
        ) and idx_unit.upper() not in ("",):
            pass
        findings.append(
            Finding(
                MISSING_REFERENCE,
                "warning",
                f"the index curve '{data_header[0] if data_header else ''}' ({index_desc or 'no description'}) states no depth datum "
                "(MD vs TVD, rotary table vs sea level); depth is not referenced and not normalized.",
                "las_index_reference",
                ["las_header.first_index", "las_header.last_index"],
                [0],
                [
                    _loc(
                        "curve",
                        cinfo[data_header[0]][4]
                        if data_header and data_header[0] in cinfo
                        else data_start,
                    )
                ],
                ["placement", "calculation"],
            )
        )
        strt = parse_number(wellkv.get("STRT", ("", "", "", 0))[1])
        stop = parse_number(wellkv.get("STOP", ("", "", "", 0))[1])
        step = parse_number(wellkv.get("STEP", ("", "", "", 0))[1])
        for label, declared, actual in (("STRT", strt, first_idx), ("STOP", stop, last_idx)):
            if declared is None or actual is None:
                if label in wellkv and declared is None:
                    findings.append(
                        Finding(
                            "EXTRACTION_PARTIAL",
                            "warning",
                            f"{label} is non-numeric in the well block; declared range unknown.",
                            f"las_{label.lower()}_unusable",
                            [f"las_header.{label.lower()}"],
                            [0],
                            blocked=["calculation"],
                        )
                    )
            elif abs(declared - actual) > 1e-3:
                findings.append(
                    Finding(
                        REFERENCE_CONFLICT,
                        "warning",
                        f"declared {label} {declared:g} differs from the data's {actual:g}; both values are kept.",
                        f"las_{label.lower()}_mismatch",
                        [
                            f"las_header.{label.lower()}",
                            f"las_header.{'first' if label == 'STRT' else 'last'}_index",
                        ],
                        [0],
                        [
                            _loc("well", wellkv[label][3], mnemonic=label),
                            _loc("data", first_line if label == "STRT" else last_line),
                        ],
                        ["calculation"],
                    )
                )
        if "STOP" not in wellkv:
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "warning",
                    "no STOP item could be parsed in the well block (malformed or missing); the declared range is unknown.",
                    "las_stop_missing",
                    ["las_header.stop"],
                    [0],
                    blocked=["calculation"],
                )
            )
        if step not in (None, 0.0) and steps and any(abs(s - step) > 1e-3 for s in steps):
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "warning",
                    f"declared STEP {step:g} is not the observed spacing ({len(steps)} distinct step sizes).",
                    "las_step_mismatch",
                    ["las_header.step"],
                    [0],
                    [_loc("well", wellkv["STEP"][3], mnemonic="STEP")],
                )
            )
        if index_back:
            findings.append(
                Finding(
                    SUSPICIOUS_VALUE,
                    "error",
                    f"index is not strictly increasing at {len(index_back)} data line(s); order kept, nothing re-sorted.",
                    "las_index_not_monotonic",
                    ["las_header.first_index"],
                    [0],
                    [_loc("data", ln) for ln in index_back[:5]],
                    ["calculation"],
                )
            )
        # curve records ---------------------------------------------------------------------
        no_unit: list[int] = []
        curve_meta: dict[int, tuple[str | None, str | None, int, Locator, Locator]] = {}
        for i, name in enumerate(data_header):
            info = cinfo.get(name)
            unit = info[1] if info else ""
            usable = bool(re.search(r"[A-Za-z0-9%]", unit))
            line_ref = info[4] if info else data_start
            st = stats[i]
            loc = _loc("curve", line_ref, mnemonic=name, column_name=name)
            attrs: list[Attr] = [
                text_attr("las_curve.mnemonic", loc, name),
                Attr(
                    "las_curve.unit",
                    loc,
                    original_text=unit or None,
                    text=unit if usable else None,
                    unit_status="stated" if usable else "missing",
                    unknown_reason=None
                    if usable
                    else ("unit missing" if not unit else "unit is not a recognizable token"),
                ),
                text_attr("las_curve.description", loc, info[3] if info else None),
            ]
            drange = _loc(
                "data",
                st["first"] or first_line,
                st["last"] or last_line,
                mnemonic=name,
                column_name=name,
            )
            for k, label in (("valid", "valid_count"), ("null", "null_count")):
                attrs.append(
                    Attr(
                        f"las_curve.{label}",
                        drange,
                        original_text=str(st[k]),
                        number=float(st[k]),
                        unit_status="not_applicable",
                    )
                )
            for k in ("min", "max"):
                v = st[k]
                a = quantity_attr(
                    f"las_curve.{k}",
                    drange,
                    None if v is None else repr(v),
                    unit if usable else None,
                )
                if v is None:
                    a.unknown_reason = "no valid samples"
                attrs.append(a)
            records.append(Rec("las_curve", subject, loc, attrs, eff, None))
            curve_meta[i] = (
                unit if usable else None,
                info[3] if info and info[3] else None,
                len(records) - 1,
                loc,
                drange,
            )
            if not usable and i > 0:
                no_unit.append(len(records) - 1)
            if st["valid"] == 0 and i > 0:
                findings.append(
                    Finding(
                        SUSPICIOUS_VALUE,
                        "info",
                        f"curve {name} has no valid samples (all null).",
                        f"las_curve_empty:{name}",
                        ["las_curve.valid_count"],
                        [len(records) - 1],
                        [loc],
                    )
                )
        if no_unit:
            findings.append(
                Finding(
                    MISSING_UNIT,
                    "warning",
                    f"{len(no_unit)} curve(s) have a missing or unrecognizable unit (e.g. '.----'); the original text is kept and no unit is assumed.",
                    "las_curve_units",
                    ["las_curve.unit"],
                    no_unit[:50],
                    [records[o].locator for o in no_unit[:5]],
                    ["calculation"],
                )
            )
        for ordinal, rec in enumerate(records):
            rec.ordinal = ordinal
        reasons: list[str] = []
        missing: list[str] = []
        if bad_width or bad_token:
            reasons.append(
                f"{len(bad_width)} data line(s) with a wrong column count and {len(bad_token)} with non-numeric tokens were skipped"
            )
            missing = [str(n) for n in (bad_width + bad_token)[:20]]
            findings.append(
                Finding(
                    "EXTRACTION_PARTIAL",
                    "warning",
                    "; ".join(reasons) + ".",
                    "las_data_lines_skipped",
                    ["las_curve.valid_count"],
                    [],
                    [_loc("data", n) for n in (bad_width + bad_token)[:5]],
                    ["calculation"],
                )
            )
        series: list[AxisOut] = []
        if ok_rows and ok_rows * ncols > MAX_SERIES_CELLS:
            reasons.append(
                f"full-resolution samples were not stored: {ok_rows} rows x {ncols} columns "
                f"exceeds the {MAX_SERIES_CELLS} cell limit (per-curve summaries are kept)"
            )
            findings.append(
                Finding(
                    "EXTRACTION_PARTIAL",
                    "warning",
                    reasons[-1] + ".",
                    "las_series_too_large",
                    ["las_curve.valid_count"],
                    [],
                    [_loc("data", first_line, last_line)],
                    ["calculation"],
                )
            )
        elif (
            ok_rows
            and ncols
            and (
                refusal := _series_refusal(
                    info_names, data_header, a_marker, len(bad_width) + len(bad_token), n_data
                )
            )
        ):
            findings.append(
                Finding(
                    "EXTRACTION_PARTIAL",
                    "warning",
                    f"full-resolution samples were not stored: {refusal}. The per-curve "
                    "summaries are kept.",
                    "las_series_refused",
                    ["las_curve.valid_count"],
                    [],
                    [_loc("data", first_line, last_line)],
                    ["calculation"],
                )
            )
        elif ok_rows and ncols:
            series.append(
                self._axis(
                    data_header,
                    subject,
                    idx_unit,
                    col_np,
                    line_np,
                    null_value,
                    curve_meta,
                    (first_line, last_line),
                )
            )
        cov = CoverageOut("line", ok_rows, n_data, missing, reasons)
        status: ProfileStatus = "succeeded" if cov.complete else "partial"
        return ProfileOutput(
            records,
            findings,
            cov,
            status,
            {"curves": data_header, "lines": n_lines, "series_samples": ok_rows if series else 0},
            series,
        )

    @staticmethod
    def _axis(
        data_header: list[str],
        subject: dict[str, Any],
        idx_unit: str,
        col_np: list[Any],
        line_np: Any,
        null_value: float | None,
        curve_meta: dict[int, tuple[str | None, str | None, int, Locator, Locator]],
        data_lines: tuple[int, int],
    ) -> AxisOut:
        name = data_header[0]
        usable_idx = bool(re.search(r"[A-Za-z0-9%]", idx_unit))
        axis = AxisOut(
            kind="log",
            index_type=classify_index(name, idx_unit),  # type: ignore[arg-type]
            index_encoding="numeric",
            index_name=name,
            index_unit=idx_unit if usable_idx else None,
            index=np.array(col_np[0], dtype=np.float64),
            positions=np.array(line_np, dtype=np.int32),
            position_kind="line",
            subject=dict(subject),
            evidence={"data_lines": {"first": data_lines[0], "last": data_lines[1]}},
        )
        for i in range(1, len(data_header)):
            unit, desc, record_ordinal, loc, drange = curve_meta[i]
            values = np.array(col_np[i], dtype=np.float64)
            if null_value is not None:
                values[values == null_value] = np.nan
            axis.curves.append(
                CurveOut(
                    measure=data_header[i],
                    column_ordinal=i,
                    values=values,
                    unit=unit,
                    unit_status="stated" if unit else "missing",
                    description=desc,
                    null_sentinel=null_value,
                    record_ordinal=record_ordinal,
                    evidence={
                        "curve_locator": loc,
                        "data_locator": drange,
                        "index_curve": name,
                        "header_record_ordinal": 0,
                    },
                )
            )
        return axis

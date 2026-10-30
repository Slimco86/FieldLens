"""LAS 2.0 well-log profile (small, safe, line-oriented reader; no third-party dependency).

Stores the header claims, the curve inventory and a per-curve summary (valid/null counts,
min/max, data line range) instead of every sample; every claim points at its LAS section and
line. Declared header values (STRT/STOP/STEP/NULL) are compared with the data and conflicts
are reported, never reconciled silently."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import event_time, parse_number, quantity_attr, text_attr, well_key
from .types import (
    IDENTITY_MISMATCH,
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
    ProfileStatus,
    Rec,
)

_HEADER = re.compile(r"^\s*([^\s.:]*)\s*\.([^\s:]*)\s+(.*?)\s*:(.*)$")
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
    version = "1"
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
        rows: list[tuple[int, list[str]]] = []
        n_lines = 0
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
                    continue
                if section == "data":
                    rows.append((n_lines, s.split()))
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
        if not data_header or "version" not in items:
            raise ProfileError("profile_mismatch", "LAS lacks ~V or ~A section")
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
        stats: list[dict[str, Any]] = [
            {"valid": 0, "null": 0, "min": None, "max": None, "first": None, "last": None}
            for _ in data_header
        ]
        null_value = parse_number(wellkv.get("NULL", ("", "", "", 0))[1])
        bad_width: list[int] = []
        bad_token: list[int] = []
        index_back: list[int] = []
        prev_index: float | None = None
        steps: set[float] = set()
        first_idx = last_idx = None
        ok_rows = 0
        for ln, toks in rows:
            if len(toks) != ncols:
                bad_width.append(ln)
                continue
            vals = [parse_number(t) for t in toks]
            if any(v is None for v in vals):
                bad_token.append(ln)
                continue
            ok_rows += 1
            idx = vals[0]
            assert idx is not None
            if first_idx is None:
                first_idx = idx
            last_idx = idx
            if prev_index is not None:
                if idx <= prev_index:
                    index_back.append(ln)
                else:
                    steps.add(round(idx - prev_index, 6))
            prev_index = idx
            for i, v in enumerate(vals):
                st = stats[i]
                if v is None:
                    continue
                if null_value is not None and v == null_value:
                    st["null"] += 1
                    continue
                st["valid"] += 1
                st["min"] = v if st["min"] is None else min(st["min"], v)
                st["max"] = v if st["max"] is None else max(st["max"], v)
                if st["first"] is None:
                    st["first"] = ln
                st["last"] = ln
        first_line = rows[0][0] if rows else data_start
        last_line = rows[-1][0] if rows else data_start
        # index unit/reference
        idx_unit = cinfo.get(data_header[0], ("", "", "", "", 0))[1] if data_header else ""
        index_desc = cinfo.get(data_header[0], ("", "", "", "", 0))[3] if data_header else ""
        head.attrs.append(
            Attr(
                "las_header.data_rows",
                _loc("data", first_line, last_line),
                original_text=str(len(rows)),
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
        cov = CoverageOut("line", ok_rows, len(rows), missing, reasons)
        status: ProfileStatus = "succeeded" if cov.complete else "partial"
        return ProfileOutput(
            records, findings, cov, status, {"curves": data_header, "lines": n_lines}
        )

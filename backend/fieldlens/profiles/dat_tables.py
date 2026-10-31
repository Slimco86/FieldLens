"""Fixed-width ``.dat`` table profiles: perforation intervals and formation (well) picks.

Layouts were read from the Volve ``Well_perforations_Volve.dat`` and ``Well_picks_Volve_v1.dat``
files: column boundaries come from the header line of the table itself (never from the file
name), so a re-exported table with shifted columns still parses. The files state no depth unit,
no MD datum and no CRS; those gaps are findings and nothing is assumed or normalized."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .common import event_time, parse_number, quantity_attr, text_attr, well_key, wellbore_suffix
from .types import (
    IDENTITY_MISMATCH,
    INTERVAL_CONFLICT,
    MAX_TEXT_LINES,
    MISSING_REFERENCE,
    MISSING_UNIT,
    REFERENCE_CONFLICT,
    SUSPICIOUS_VALUE,
    TEMPORAL_AMBIGUITY,
    UNKNOWN_CODE,
    Attr,
    CoverageOut,
    Finding,
    Locator,
    ParseContext,
    ProfileError,
    ProfileOutput,
    Rec,
)

_TITLE = re.compile(r"\S+(?: \S+)*")
PERF_REQUIRED = ("Well name", "Top MD", "Base MD", "Perf obs#")
PICK_REQUIRED = ("Well name", "Surface name", "Obs#", "Qlf", "MD")
PERF_TYPES = frozenset({"GUN", "UNKNOWN", "TCP", "OH GRAVEL"})
PERF_STATUS = frozenset({"OPEN", "CLOSED", "PLUGGED", "SQUEEZED"})
DEFAULT_QLF = frozenset({"ER", "FP", "FO", "NL", "NR"})


def _loc(line: int, column: str | None = None) -> Locator:
    loc: Locator = {"kind": "text", "line_start": line, "line_end": line}
    if column:
        loc["column_name"] = column
    return loc


def columns(header: str) -> list[tuple[str, int, int | None]]:
    found = [(m.group(0), m.start()) for m in _TITLE.finditer(header.rstrip())]
    return [
        (title, start, found[i + 1][1] if i + 1 < len(found) else None)
        for i, (title, start) in enumerate(found)
    ]


def split_row(line: str, cols: list[tuple[str, int, int | None]]) -> dict[str, str]:
    return {t: line[s:e].strip() if e is not None else line[s:].strip() for t, s, e in cols}


def _read(path: Path) -> list[str]:
    lines: list[str] = []
    with path.open("r", encoding="latin-1", errors="replace") as h:
        for i, raw in enumerate(h, 1):
            if i > MAX_TEXT_LINES:
                raise ProfileError("too_many_lines", "table exceeds the line limit")
            lines.append(raw.rstrip("\r\n"))
    return lines


def _head(path: Path, n: int = 120) -> list[str]:
    out: list[str] = []
    with path.open("r", encoding="latin-1", errors="replace") as h:
        for _, raw in zip(range(n), h, strict=False):
            out.append(raw.rstrip("\r\n"))
    return out


def sniff_dat_kind(path: Path) -> str | None:
    head = _head(path)
    if head and all(t in head[0] for t in PERF_REQUIRED):
        return "perforations"
    text = "\n".join(head)
    if re.search(r"^Well\s+\S", text, re.M) and "Surface name" in text and "Qlf" in text:
        return "picks"
    return None


# Depth attributes whose unit is not documented by the Volve tables. Owner decision (October 31):
# default to meters, a warning rather than a blocker; a unit the source states always wins (these
# tables state none). TWT is a time, dip/azimuth are angles, easting/northing are coordinates:
# none of those is defaulted.
DEFAULTED_DEPTH_KEYS = frozenset(
    {
        "perforation.top_md",
        "perforation.base_md",
        "perforation.top_tvd",
        "perforation.base_tvd",
        "perforation.top_tvdss",
        "perforation.base_tvdss",
        "pick.md",
        "pick.tvd",
        "pick.tvdss",
    }
)
MAX_DEFAULT_LOCATORS = 5


def _is_defaulted(a: Attr) -> bool:
    return (
        a.key in DEFAULTED_DEPTH_KEYS
        and a.unit is None
        and a.normalized_unit == "m"
        and a.validation_state == "unreviewed"
    )


def _missing_depth_findings(
    findings: list[Finding], recs: list[Rec], attr_prefix: str, reference_note: str, easting: bool
) -> None:
    if not recs:
        return
    idx = list(range(min(len(recs), 50)))
    keys = [f"{attr_prefix}.top_md" if attr_prefix == "perforation" else f"{attr_prefix}.md"]
    used: list[tuple[int, Attr]] = [
        (r.ordinal, a) for r in recs for a in r.attrs if _is_defaulted(a)
    ]
    skipped = sum(
        1
        for r in recs
        for a in r.attrs
        if a.key in DEFAULTED_DEPTH_KEYS
        and a.number is not None
        and a.unit is None
        and not _is_defaulted(a)
    )
    if used:
        by_key: dict[str, int] = {}
        for _, a in used:
            by_key[a.key] = by_key.get(a.key, 0) + 1
        detail = ", ".join(f"{k}={n}" for k, n in sorted(by_key.items()))
        findings.append(
            Finding(
                MISSING_UNIT,
                "warning",
                "the table states no unit for depth values; assumed meters (measured depth; "
                f"depth reference unspecified) by default for {len(used)} attribute(s) in "
                f"{len({o for o, _ in used})} record(s) ({detail})"
                + (
                    f"; {skipped} further value(s) stay unsupported (flagged by the source)"
                    if skipped
                    else ""
                )
                + ". A unit stated by a source always overrides this default; original text "
                "is kept.",
                f"{attr_prefix}_units_missing",
                keys,
                idx,
                [a.locator for _, a in used[:MAX_DEFAULT_LOCATORS]],
                [],
            )
        )
    elif skipped:
        findings.append(
            Finding(
                MISSING_UNIT,
                "warning",
                f"the table states no unit for depth values; {skipped} value(s) stay unsupported.",
                f"{attr_prefix}_units_missing",
                keys,
                idx,
                [recs[0].locator],
                ["calculation", "placement"],
            )
        )
    if used:
        findings.append(
            Finding(
                MISSING_REFERENCE,
                "warning",
                f"MD has no stated datum in this file ({reference_note}); reference unspecified, "
                "assumed the well's depth reference for the "
                f"{len(used)} defaulted depth value(s). TVD/TVDSS are labelled but the "
                "elevation they imply is not stated.",
                f"{attr_prefix}_reference_missing",
                keys,
                idx,
                [recs[0].locator],
                [],
            )
        )
    else:
        findings.append(
            Finding(
                MISSING_REFERENCE,
                "warning",
                f"MD has no stated datum in this file ({reference_note}); no usable depth value "
                "was found.",
                f"{attr_prefix}_reference_missing",
                keys,
                idx,
                [recs[0].locator],
                ["placement", "calculation"],
            )
        )
    has_xy = easting and any(
        a.number is not None
        for r in recs
        for a in r.attrs
        if a.key.endswith(("easting", "northing"))
    )
    if has_xy:
        findings.append(
            Finding(
                MISSING_REFERENCE,
                "warning",
                "easting/northing values carry no CRS or datum.",
                f"{attr_prefix}_crs_missing",
                [],
                idx,
                [recs[0].locator],
                ["placement"],
            )
        )


def _depth_attr(key: str, line: int, column: str, text: str | None, reference: str | None) -> Attr:
    a = quantity_attr(key, _loc(line, column), text or None, None, reference=reference)
    if not text:
        a.unknown_reason = "blank in source"
    if key in DEFAULTED_DEPTH_KEYS and a.number is not None:
        # Unit not documented: default to meters, keep the original text, flag via reference.
        a.normalized_number, a.normalized_unit = a.number, "m"
        a.validation_state = "unreviewed"
        a.reference = f"assumed {reference} (default)" if reference else "assumed (default)"
    return a


class PerforationTableProfile:
    name = "dat_perforations_volve"
    version = "3"  # 2: undocumented depth unit defaults to meters; 3: reference warning (TASK-046)
    method = "native_text_fixed_width"
    families = ("csv", "text")

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        return format_family in self.families and sniff_dat_kind(path) == "perforations"

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        lines = _read(path)
        cols = columns(lines[0]) if lines else []
        titles = [c[0] for c in cols]
        if not all(t in titles for t in PERF_REQUIRED):
            raise ProfileError("profile_mismatch", "perforation header not found")
        records: list[Rec] = []
        findings: list[Finding] = []
        no_date: list[int] = []
        inverted: list[int] = []
        bad_codes: Counter[str] = Counter()
        seen: dict[tuple[str, str, str], int] = {}
        dups: list[int] = []
        by_well: dict[str, list[int]] = defaultdict(list)
        skipped: list[int] = []
        for ln, line in enumerate(lines[1:], 2):
            if not line.strip():
                continue
            v = split_row(line, cols)
            well = v.get("Well name", "")
            if not well:
                skipped.append(ln)
                continue
            top = parse_number(v.get("Top MD"))
            base = parse_number(v.get("Base MD"))
            subject: dict[str, Any] = {
                "well_name": well,
                "wellbore_name": None,
                "wellbore_label": well,
                "well_key": well_key(well),
                "wellbore_suffix": wellbore_suffix(well),
            }
            attrs = [
                text_attr(
                    "perforation.formation", _loc(ln, "Top formation"), v.get("Top formation")
                ),
                text_attr("perforation.obs_no", _loc(ln, "Perf obs#"), v.get("Perf obs#")),
                text_attr(
                    "perforation.completion_obs_no", _loc(ln, "Compl obs#"), v.get("Compl obs#")
                ),
                _depth_attr("perforation.top_md", ln, "Top MD", v.get("Top MD"), "MD"),
                _depth_attr("perforation.base_md", ln, "Base MD", v.get("Base MD"), "MD"),
                _depth_attr("perforation.top_tvd", ln, "Top TVD", v.get("Top TVD"), "TVD"),
                _depth_attr("perforation.base_tvd", ln, "Base TVD", v.get("Base TVD"), "TVD"),
                _depth_attr("perforation.top_tvdss", ln, "Top TVDSS", v.get("Top TVDSS"), "TVDSS"),
                _depth_attr(
                    "perforation.base_tvdss", ln, "Base TVDSS", v.get("Base TVDSS"), "TVDSS"
                ),
                _depth_attr(
                    "perforation.top_easting", ln, "Top easting", v.get("Top easting"), None
                ),
                _depth_attr(
                    "perforation.top_northing", ln, "Top northing", v.get("Top northing"), None
                ),
                text_attr("perforation.perf_type", _loc(ln, "Perf type"), v.get("Perf type")),
                text_attr(
                    "perforation.current_status",
                    _loc(ln, "Current status"),
                    v.get("Current status"),
                ),
                text_attr("perforation.remark", _loc(ln, "Remark"), v.get("Remark")),
            ]
            perf_date = v.get("Perf date", "")
            status_date = v.get("Current status date", "")
            attrs.append(text_attr("perforation.perf_date", _loc(ln, "Perf date"), perf_date))
            attrs.append(
                text_attr(
                    "perforation.current_status_date", _loc(ln, "Current status date"), status_date
                )
            )
            eff = event_time(perf_date, "Perf date")
            rec = Rec("perforation_interval", subject, _loc(ln), attrs, eff, None)
            rec.ordinal = len(records)
            records.append(rec)
            by_well[well].append(rec.ordinal)
            if eff is None:
                no_date.append(rec.ordinal)
            elif eff.precision == "unknown":
                bad_codes[f"Perf date={perf_date}"] += 1
            if top is not None and base is not None and top >= base:
                inverted.append(rec.ordinal)
                for a in attrs:
                    if a.key in ("perforation.top_md", "perforation.base_md"):
                        a.validation_state = "conflicting"
            pt = v.get("Perf type", "")
            if pt and pt not in PERF_TYPES:
                bad_codes[f"Perf type={pt}"] += 1
            st = v.get("Current status", "")
            if st and st not in PERF_STATUS:
                bad_codes[f"Current status={st}"] += 1
            k = (well, v.get("Perf obs#", ""), v.get("Top MD", ""))
            if k in seen:
                dups.append(rec.ordinal)
            seen[k] = rec.ordinal
        _missing_depth_findings(
            findings, records, "perforation", "not stated; no RKB/datum column", True
        )
        if no_date:
            findings.append(
                Finding(
                    TEMPORAL_AMBIGUITY,
                    "warning",
                    f"{len(no_date)} perforation interval(s) have no perforation date; when each "
                    "was shot is unknown, so no installed-state date is derived and no "
                    "history is invented.",
                    "perf_date_blank",
                    ["perforation.perf_date"],
                    no_date[:50],
                    [records[o].locator for o in no_date[:5]],
                    ["temporal_state", "temporal_state"],
                )
            )
        if inverted:
            findings.append(
                Finding(
                    INTERVAL_CONFLICT,
                    "error",
                    f"{len(inverted)} interval(s) have Top MD >= Base MD.",
                    "perf_interval_inverted",
                    ["perforation.top_md", "perforation.base_md"],
                    inverted,
                    [records[o].locator for o in inverted[:5]],
                    ["temporal_state", "placement"],
                )
            )
        if dups:
            findings.append(
                Finding(
                    REFERENCE_CONFLICT,
                    "warning",
                    f"{len(dups)} interval row(s) repeat the same (well, obs#, top MD).",
                    "perf_duplicate",
                    ["perforation.obs_no"],
                    dups[:50],
                    [records[o].locator for o in dups[:5]],
                    ["temporal_state"],
                )
            )
        for well, ords in sorted(by_well.items()):
            spans = sorted(
                (
                    (
                        parse_number(records[o].attr("perforation.top_md").original_text)  # type: ignore[union-attr]
                        if records[o].attr("perforation.top_md")
                        else None,
                        parse_number(records[o].attr("perforation.base_md").original_text)  # type: ignore[union-attr]
                        if records[o].attr("perforation.base_md")
                        else None,
                        o,
                    )
                    for o in ords
                ),
                key=lambda t: (t[0] is None, t[0] or 0.0),
            )
            clash = [
                (a[2], b[2])
                for a, b in zip(spans, spans[1:], strict=False)
                if a[1] is not None and b[0] is not None and b[0] < a[1]
            ]
            if clash:
                findings.append(
                    Finding(
                        INTERVAL_CONFLICT,
                        "warning",
                        f"{well}: {len(clash)} pair(s) of perforation intervals overlap in MD.",
                        f"perf_overlap:{well}",
                        ["perforation.top_md", "perforation.base_md"],
                        [a for a, _ in clash][:50],
                        [records[a].locator for a, _ in clash[:5]],
                        ["temporal_state"],
                    )
                )
        for code, nbad in sorted(bad_codes.items()):
            findings.append(
                Finding(
                    UNKNOWN_CODE if "date" not in code else TEMPORAL_AMBIGUITY,
                    "info",
                    f"{code} in {nbad} row(s) is outside the reviewed code/date forms; kept verbatim.",
                    f"perf_unknown:{code}",
                )
            )
        reasons = [f"{len(skipped)} row(s) without a well name skipped"] if skipped else []
        if skipped:
            findings.append(
                Finding(
                    "EXTRACTION_PARTIAL",
                    "warning",
                    reasons[0] + ".",
                    "perf_rows_skipped",
                    locators=[_loc(n) for n in skipped[:5]],
                    blocked=["temporal_state"],
                )
            )
        data_rows = sum(1 for line in lines[1:] if line.strip())
        cov = CoverageOut("line", len(records), data_rows, [str(n) for n in skipped[:20]], reasons)
        return ProfileOutput(
            records,
            findings,
            cov,
            "succeeded" if cov.complete else "partial",
            {"columns": titles, "wells": sorted(by_well)},
        )


class PickTableProfile:
    name = "dat_well_picks_volve"
    version = "3"  # 2: undocumented depth unit defaults to meters; 3: reference warning (TASK-046)
    method = "native_text_fixed_width"
    families = ("csv", "text")

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        return format_family in self.families and sniff_dat_kind(path) == "picks"

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        lines = _read(path)
        qlf_known: dict[str, str] = {}
        for line in lines[:40]:
            m = re.match(r"#\s*([A-Z]{2}):\s*(.+)$", line)
            if m:
                qlf_known[m.group(1)] = m.group(2).strip()
        qlfs = frozenset(qlf_known) or DEFAULT_QLF
        records: list[Rec] = []
        findings: list[Finding] = []
        block = ""
        pending_header = ""
        cols: list[tuple[str, int, int | None]] = []
        seen: dict[tuple[str, str, str], int] = {}
        dups: list[int] = []
        id_mismatch: list[int] = []
        tvd_gt: list[int] = []
        bad_q: Counter[str] = Counter()
        flagged: Counter[str] = Counter()
        skipped: list[int] = []
        data_rows = 0
        blocks: set[str] = set()
        for ln, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if re.match(r"^Well\s+\S", line) and not line.startswith(" "):
                block = line[4:].strip()
                blocks.add(block)
                cols = []
                continue
            if "Surface name" in line and "Qlf" in line:
                cols = columns(line)
                pending_header = line
                continue
            if set(s) <= {"-", " "}:
                if pending_header:  # dashed rule gives exact column spans ("Qlf MD" has 1 space)
                    runs = [(m.start(), m.end()) for m in re.finditer(r"-+", line)]
                    cols = [
                        (
                            pending_header[
                                a : (runs[i + 1][0] if i + 1 < len(runs) else len(pending_header))
                            ].strip(),
                            a,
                            runs[i + 1][0] if i + 1 < len(runs) else None,
                        )
                        for i, (a, _) in enumerate(runs)
                    ]
                    pending_header = ""
                continue
            if not cols:
                skipped.append(ln)
                continue
            data_rows += 1
            v = split_row(line, cols)
            well = v.get("Well name", "")
            surface = v.get("Surface name", "")
            if not well or not surface:
                skipped.append(ln)
                continue
            subject: dict[str, Any] = {
                "well_name": well,
                "wellbore_name": None,
                "wellbore_label": well,
                "well_key": well_key(well),
                "wellbore_suffix": wellbore_suffix(well),
                "block_header": block,
            }
            qlf = v.get("Qlf", "")
            attrs = [
                text_attr("pick.surface_name", _loc(ln, "Surface name"), surface),
                text_attr("pick.obs_no", _loc(ln, "Obs#"), v.get("Obs#")),
                text_attr("pick.qualifier", _loc(ln, "Qlf"), qlf),
                _depth_attr("pick.md", ln, "MD", v.get("MD"), "MD"),
                _depth_attr("pick.tvd", ln, "TVD", v.get("TVD"), "TVD"),
                _depth_attr("pick.tvdss", ln, "TVDSS", v.get("TVDSS"), "TVDSS"),
                _depth_attr("pick.twt", ln, "TWT", v.get("TWT"), "TWT"),
                _depth_attr("pick.dip", ln, "Dip", v.get("Dip"), None),
                _depth_attr("pick.azi", ln, "Azi", v.get("Azi"), None),
                _depth_attr("pick.easting", ln, "Easting", v.get("Easting"), None),
                _depth_attr("pick.northing", ln, "Northing", v.get("Northing"), None),
                text_attr("pick.interpretation", _loc(ln, "Intrp"), v.get("Intrp")),
            ]
            rec = Rec("formation_pick", subject, _loc(ln), attrs, None, None)
            rec.ordinal = len(records)
            records.append(rec)
            if qlf:
                flagged[qlf] += 1
                if qlf not in qlfs:
                    bad_q[qlf] += 1
                else:
                    for a in attrs:
                        if a.key in ("pick.md", "pick.tvd", "pick.tvdss"):
                            a.validation_state = "unsupported"
                            a.normalized_number = a.normalized_unit = None  # not a usable top
            if block and well != block:
                id_mismatch.append(rec.ordinal)
            md, tvd = parse_number(v.get("MD")), parse_number(v.get("TVD"))
            if md is not None and tvd is not None and tvd > md + 1e-6:
                tvd_gt.append(rec.ordinal)
            k = (well, surface, v.get("Obs#", ""))
            if k in seen:
                dups.append(rec.ordinal)
            seen[k] = rec.ordinal
        _missing_depth_findings(
            findings, records, "pick", "not stated; picks carry no RKB/datum column", True
        )
        findings.append(
            Finding(
                TEMPORAL_AMBIGUITY,
                "info",
                "picks carry no date; they are interpretations of unknown vintage, not "
                "time-stamped observations.",
                "pick_no_time",
                ["pick.md"],
                [0] if records else [],
                blocked=["temporal_state"],
            )
        ) if records else None
        if flagged:
            findings.append(
                Finding(
                    UNKNOWN_CODE if bad_q else "HISTORY_INCOMPLETE",
                    "warning" if bad_q else "info",
                    "source qualifiers present: "
                    + ", ".join(f"{q}={n}" for q, n in sorted(flagged.items()))
                    + (f"; unreviewed qualifier(s) {sorted(bad_q)}" if bad_q else "")
                    + ". Picks flagged ER/FP/FO/NL/NR are eroded, faulted or not logged and their "
                    "depths are marked unsupported, not treated as formation tops.",
                    "pick_qualifiers",
                    ["pick.qualifier"],
                    [
                        r.ordinal
                        for r in records
                        if (qa := r.attr("pick.qualifier")) is not None
                        and (qa.text or "") in flagged
                    ][:50],
                    [],
                    ["claim_acceptance"],
                )
            )
        for key, ords, code, sev, msg in (
            (
                "pick_duplicate",
                dups,
                REFERENCE_CONFLICT,
                "warning",
                "pick row(s) repeat (well, surface, obs#); all kept.",
            ),
            (
                "pick_well_mismatch",
                id_mismatch,
                IDENTITY_MISMATCH,
                "error",
                "pick row(s) name a well different from their 'Well' block header.",
            ),
            (
                "pick_tvd_gt_md",
                tvd_gt,
                SUSPICIOUS_VALUE,
                "error",
                "pick row(s) have TVD greater than MD.",
            ),
        ):
            if ords:
                findings.append(
                    Finding(
                        code,
                        "error" if sev == "error" else "warning",
                        f"{len(ords)} {msg}",
                        key,
                        ["pick.md", "pick.tvd"],
                        ords[:50],
                        [records[o].locator for o in ords[:5]],
                        ["placement"],
                    )
                )
        if skipped:
            findings.append(
                Finding(
                    "EXTRACTION_PARTIAL",
                    "warning",
                    f"{len(skipped)} line(s) could not be read as picks.",
                    "pick_lines_skipped",
                    locators=[_loc(n) for n in skipped[:5]],
                    blocked=["claim_acceptance"],
                )
            )
        cov = CoverageOut(
            "line",
            len(records),
            len(records) + len(skipped),
            [str(n) for n in skipped[:20]],
            [f"{len(skipped)} line(s) skipped"] if skipped else [],
        )
        return ProfileOutput(
            records,
            findings,
            cov,
            "succeeded" if cov.complete else "partial",
            {"well_blocks": sorted(blocks), "qualifiers": dict(qlf_known)},
        )

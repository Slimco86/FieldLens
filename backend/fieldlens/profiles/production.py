"""Production workbook profile (Volve-style ``Daily Production Data`` / ``Monthly Production
Data`` sheets). Selected from workbook content: sheet names plus header cells.

Scoping: every record is bound to the wellbore named on its own row (``WELL_BORE_CODE``) and the
well label (``NPD_WELL_BORE_NAME``); rows are never pooled across wellbores. Blank cells and the
literal ``NULL`` are unknown, never zero. Daily quantities carry no unit cell in the source, so
no unit is assumed (units on the monthly sheet are not copied across)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from .common import event_time, parse_number, quantity_attr, text_attr, well_key
from .types import (
    MISSING_UNIT,
    REFERENCE_CONFLICT,
    SUSPICIOUS_VALUE,
    UNKNOWN_CODE,
    Attr,
    AxisOut,
    CoverageOut,
    CurveOut,
    Finding,
    Locator,
    ParseContext,
    ProfileError,
    ProfileOutput,
    Rec,
)
from .xlsx import Cell, Workbook

_EPOCH = date(1970, 1, 1)
DAILY = "Daily Production Data"
MONTHLY = "Monthly Production Data"
DAILY_REQUIRED = {"DATEPRD", "WELL_BORE_CODE", "BORE_OIL_VOL", "ON_STREAM_HRS"}
MONTHLY_REQUIRED = {"Wellbore name", "Year", "Month", "Oil"}
FLOW_KINDS = frozenset({"production", "injection"})
WELL_TYPES = frozenset({"OP", "WI"})

DAILY_QUANTITIES = {
    "ON_STREAM_HRS": "on_stream_hrs",
    "AVG_DOWNHOLE_PRESSURE": "avg_downhole_pressure",
    "AVG_DOWNHOLE_TEMPERATURE": "avg_downhole_temperature",
    "AVG_DP_TUBING": "avg_dp_tubing",
    "AVG_ANNULUS_PRESS": "avg_annulus_press",
    "AVG_CHOKE_SIZE_P": "avg_choke_size_p",
    "AVG_WHP_P": "avg_whp_p",
    "AVG_WHT_P": "avg_wht_p",
    "DP_CHOKE_SIZE": "dp_choke_size",
    "BORE_OIL_VOL": "bore_oil_vol",
    "BORE_GAS_VOL": "bore_gas_vol",
    "BORE_WAT_VOL": "bore_wat_vol",
    "BORE_WI_VOL": "bore_wi_vol",
}
DAILY_TEXT = {"FLOW_KIND": "flow_kind", "WELL_TYPE": "well_type"}
MONTHLY_QUANTITIES = {
    "On Stream": "on_stream",
    "Oil": "oil",
    "Gas": "gas",
    "Water": "water",
    "GI": "gi",
    "WI": "wi",
}


def _loc(sheet: str, ref: str) -> Locator:
    return {"kind": "xlsx", "sheet": sheet, "cell_range": ref}


def _val(cell: Cell | None) -> str | None:
    """Stored text; the literal NULL is a missing value."""
    if cell is None or cell.text is None:
        return None
    return None if cell.text.strip().upper() == "NULL" else cell.text


def _header(cells: list[Cell]) -> dict[str, str]:
    return {(c.text or "").strip(): c.column for c in cells if c.text}


def _q(
    sheet: str, key: str, cell: Cell | None, ref: str, unit: str | None, unit_ref: str | None
) -> Attr:
    text = _val(cell)
    attr = quantity_attr(key, _loc(sheet, ref), text, unit, unit_required=True)
    if text is None:
        attr.original_text = None if cell is None else cell.text
        attr.unknown_reason = "NULL in source" if cell is not None else "blank in source"
        attr.unit_status = "stated" if unit else "missing"
    if unit and unit_ref:
        attr.reference = f"unit cell {sheet}!{unit_ref}"
    return attr


def _epoch_day(iso: str) -> int | None:
    try:
        return (date.fromisoformat(iso[:10]) - _EPOCH).days
    except ValueError:
        return None


class _Group:
    """Daily rows of one (wellbore, well) in source order; becomes one series axis."""

    def __init__(self, subject: dict[str, Any], header: dict[str, str]) -> None:
        self.subject = subject
        self.header = header
        self.days: list[int] = []
        self.rows: list[int] = []
        self.ordinals: list[int] = []
        self.values: dict[str, list[float]] = defaultdict(list)
        self.units: dict[str, set[str | None]] = defaultdict(set)

    def add(self, day: int, row: int, ordinal: int, attrs: list[Attr]) -> None:
        self.days.append(day)
        self.rows.append(row)
        self.ordinals.append(ordinal)
        by_key = {a.key: a for a in attrs}
        for col_name, key in DAILY_QUANTITIES.items():
            if col_name not in self.header:
                continue
            a = by_key.get(f"production_day.{key}")
            number = None if a is None else a.number
            self.values[col_name].append(float("nan") if number is None else number)
            if number is not None:  # the unit is judged from rows that carry a value
                self.units[col_name].add(
                    a.unit if a is not None and a.unit_status == "stated" else None
                )


def _production_axes(groups: dict[tuple[str, str | None], _Group]) -> list[AxisOut]:
    """One axis per wellbore (day index, source row order kept for equal days) with one curve
    per measure column present in the sheet. Missing days stay absent and blank/NULL cells stay
    NaN (never zero); no unit is assumed when the source states none."""
    axes: list[AxisOut] = []
    for (wellbore, _well), g in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1] or "")):
        order = np.argsort(np.array(g.days, dtype=np.int64), kind="stable")
        index = np.array(g.days, dtype=np.float64)[order]
        rows = np.array(g.rows, dtype=np.int32)[order]
        ordinals = np.array(g.ordinals, dtype=np.int64)[order]
        axis = AxisOut(
            kind="production",
            index_type="time",
            index_encoding="epoch_days",
            index_name="DATEPRD",
            index_unit="days since 1970-01-01",
            index=index,
            positions=rows,
            position_kind="row",
            subject=dict(g.subject),
            evidence={
                "kind": "xlsx",
                "sheet": DAILY,
                "first_record_ordinal": int(ordinals.min()),
                "last_record_ordinal": int(ordinals.max()),
                "record_count": int(index.size),
                "wellbore": wellbore,
            },
        )
        for col_name, key in DAILY_QUANTITIES.items():
            if col_name not in g.header:
                continue
            values = np.array(g.values[col_name], dtype=np.float64)[order]
            units = g.units[col_name]
            stated = {u for u in units if u}
            if len(stated) == 1 and None not in units:
                unit, status = next(iter(stated)), "stated"
            elif stated:
                unit, status = None, "mixed"
            else:
                unit, status = None, "missing"
            column = g.header[col_name]
            axis.curves.append(
                CurveOut(
                    measure=key,
                    column_ordinal=len(axis.curves),
                    values=values,
                    unit=unit,
                    unit_status=status,  # type: ignore[arg-type]
                    description=col_name,
                    null_sentinel=None,
                    record_ordinal=int(ordinals.min()),
                    evidence={
                        "kind": "xlsx",
                        "sheet": DAILY,
                        "column": column,
                        "column_header": col_name,
                        "first_row": int(rows.min()),
                        "last_row": int(rows.max()),
                        "cell_range": f"{column}{int(rows.min())}:{column}{int(rows.max())}",
                        "first_record_ordinal": int(ordinals.min()),
                        "last_record_ordinal": int(ordinals.max()),
                    },
                )
            )
        axes.append(axis)
    return axes


class ProductionWorkbookProfile:
    name = "production_workbook_volve"
    version = "2"
    method = "native_xlsx_stdlib"
    families = ("xlsx",)

    def detect(self, path: Path, format_family: str, filename: str) -> bool:
        if format_family != "xlsx":
            return False
        try:
            wb = Workbook(path)
        except ProfileError:
            return False
        try:
            member = wb.sheet_member(DAILY)
            if member is None:
                return False
            first = next(iter(wb.rows(member, stop_after=1)), None)
            return first is not None and DAILY_REQUIRED <= set(_header(first[1]))
        except ProfileError:
            return False
        finally:
            wb.close()

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput:
        wb = Workbook(path)
        try:
            records: list[Rec] = []
            findings: list[Finding] = []
            counts: dict[str, int] = {}
            sums: dict[tuple[str, str], dict[str, list[float | None]]] = defaultdict(
                lambda: defaultdict(list)
            )
            groups = self._daily(wb, records, findings, counts, sums)
            self._monthly(wb, records, findings, counts, sums)
        finally:
            wb.close()
        for i, r in enumerate(records):
            r.ordinal = i
        total_rows = counts.get("daily_rows", 0) + counts.get("monthly_rows", 0)
        out = ProfileOutput(
            records,
            findings,
            CoverageOut("record", total_rows, total_rows),
            "succeeded",
            {"counts": counts, "wellbores": sorted({r.subject["wellbore_label"] for r in records})},
            _production_axes(groups),
        )
        return out

    # -- daily ---------------------------------------------------------------------------
    def _daily(
        self,
        wb: Workbook,
        records: list[Rec],
        findings: list[Finding],
        counts: dict[str, int],
        sums: dict[tuple[str, str], dict[str, list[float | None]]],
    ) -> dict[tuple[str, str | None], _Group]:
        groups: dict[tuple[str, str | None], _Group] = {}
        member = wb.sheet_member(DAILY)
        if member is None:
            raise ProfileError("profile_mismatch", f"sheet '{DAILY}' missing")
        header: dict[str, str] = {}
        seen: dict[tuple[str, str], int] = {}
        dups: list[int] = []
        negative: list[int] = []
        hours: list[int] = []
        unknown_codes: dict[str, int] = defaultdict(int)
        n = 0
        n_dated = 0
        for rown, cells in wb.rows(member):
            by_col = {c.column: c for c in cells}
            if not header:
                header = _header(cells)
                missing = DAILY_REQUIRED - set(header)
                if missing:
                    raise ProfileError("profile_mismatch", f"missing columns {sorted(missing)}")
                continue
            code_cell = by_col.get(header["WELL_BORE_CODE"])
            date_cell = by_col.get(header["DATEPRD"])
            if code_cell is None or date_cell is None:
                findings.append(
                    Finding(
                        "EXTRACTION_PARTIAL",
                        "warning",
                        f"row {rown} lacks a wellbore code or date and was not extracted.",
                        f"daily_row_unscoped:{rown}",
                        locators=[_loc(DAILY, f"A{rown}:X{rown}")],
                        blocked=["claim_acceptance"],
                    )
                )
                continue
            n += 1
            wellbore = (code_cell.text or "").strip()
            well_name = (
                by_col.get(header.get("NPD_WELL_BORE_NAME", "")) or Cell("", "", 0, None)
            ).text
            subject: dict[str, Any] = {
                "well_name": well_name,
                "wellbore_name": wellbore,
                "wellbore_label": wellbore,
                "well_key": well_key(well_name) or well_key(wellbore),
                "npd_wellbore_code": (
                    by_col.get(header.get("NPD_WELL_BORE_CODE", "")) or Cell("", "", 0, None)
                ).text,
                "field_name": (
                    by_col.get(header.get("NPD_FIELD_NAME", "")) or Cell("", "", 0, None)
                ).text,
                "facility_name": (
                    by_col.get(header.get("NPD_FACILITY_NAME", "")) or Cell("", "", 0, None)
                ).text,
            }
            if date_cell.is_date and date_cell.iso:
                eff = event_time(date_cell.iso, "DATEPRD")
                if eff is not None and date_cell.precision == "day":
                    eff.timezone_known = False
            else:
                eff = event_time(None)
            attrs: list[Attr] = []
            date_attr = Attr(
                "production_day.date",
                _loc(DAILY, date_cell.ref),
                original_text=date_cell.raw or date_cell.text,
                text=date_cell.iso if date_cell.is_date else None,
                unknown_reason=None
                if date_cell.is_date
                else "DATEPRD is not a date-formatted cell",
                reference="excel_serial_1900" if date_cell.is_date else None,
            )
            attrs.append(date_attr)
            for col_name, key in DAILY_QUANTITIES.items():
                col = header.get(col_name)
                if col is None:
                    continue
                cell = by_col.get(col)
                attrs.append(_q(DAILY, f"production_day.{key}", cell, f"{col}{rown}", None, None))
            for col_name, key in DAILY_TEXT.items():
                col = header.get(col_name)
                cell = by_col.get(col) if col else None
                if cell is not None:
                    attrs.append(
                        text_attr(f"production_day.{key}", _loc(DAILY, cell.ref), cell.text)
                    )
            uom = by_col.get(header.get("AVG_CHOKE_UOM", ""))
            if uom is not None:
                attrs.append(
                    text_attr("production_day.avg_choke_uom", _loc(DAILY, uom.ref), uom.text)
                )
                choke = next((a for a in attrs if a.key == "production_day.avg_choke_size_p"), None)
                if choke is not None and uom.text:
                    choke.unit, choke.unit_status = uom.text.strip(), "stated"
                    choke.reference = f"unit cell {DAILY}!{uom.ref}"
                    choke.unit_status = "stated"
                    if choke.number is not None:
                        # A header-stated unit is evidence of the unit, like other stated columns.
                        choke.validation_state = "unreviewed"
            rec = Rec(
                "production_day",
                subject,
                _loc(DAILY, f"A{rown}:X{rown}"),
                attrs,
                eff,
                None,
            )
            records.append(rec)
            ordinal = len(records) - 1
            if date_cell.is_date and date_cell.iso:
                day = _epoch_day(date_cell.iso)
                if day is not None:
                    groups.setdefault((wellbore, well_name), _Group(subject, header)).add(
                        day, rown, ordinal, attrs
                    )
                    n_dated += 1
            key2 = (wellbore, date_cell.iso or date_cell.text or "")
            if key2 in seen:
                dups.append(ordinal)
            seen[key2] = ordinal
            for a in attrs:
                if a.number is not None and a.key.endswith(("_vol", "_hrs")) and a.number < 0:
                    negative.append(ordinal)
                if a.key.endswith("on_stream_hrs") and a.number is not None and a.number > 24.0001:
                    hours.append(ordinal)
            for a in attrs:
                if a.key.endswith(("flow_kind",)) and a.text and a.text not in FLOW_KINDS:
                    unknown_codes[f"FLOW_KIND={a.text}"] += 1
                if a.key.endswith(("well_type",)) and a.text and a.text not in WELL_TYPES:
                    unknown_codes[f"WELL_TYPE={a.text}"] += 1
            if date_cell.iso:
                month = date_cell.iso[:7]
                for qk in ("bore_oil_vol", "bore_gas_vol", "bore_wat_vol", "bore_wi_vol"):
                    qa = next((x for x in attrs if x.key == f"production_day.{qk}"), None)
                    sums[(str(subject["npd_wellbore_code"]), month)][qk].append(
                        None if qa is None else qa.number
                    )
        counts["daily_rows"] = n
        counts["daily_rows_without_date"] = n - n_dated
        _unit_missing(findings, "daily", records)
        _aggregate(
            findings,
            "daily_duplicate",
            REFERENCE_CONFLICT,
            "error",
            dups,
            records,
            "daily row(s) repeat an existing (wellbore, date); both are kept and none is summed away.",
            ["production_day.date"],
            ["calculation"],
        )
        _aggregate(
            findings,
            "daily_negative",
            SUSPICIOUS_VALUE,
            "warning",
            negative,
            records,
            "daily row(s) have a negative volume or hours value.",
            ["production_day.bore_oil_vol"],
            ["calculation"],
        )
        _aggregate(
            findings,
            "daily_hours_gt_24",
            SUSPICIOUS_VALUE,
            "warning",
            hours,
            records,
            "daily row(s) report more than 24 on-stream hours.",
            ["production_day.on_stream_hrs"],
            ["calculation"],
        )
        for code, k in sorted(unknown_codes.items()):
            findings.append(
                Finding(
                    UNKNOWN_CODE,
                    "info",
                    f"{code} occurs in {k} row(s); not in the reviewed code list, kept verbatim.",
                    f"daily_unknown_code:{code}",
                    ["production_day.flow_kind"],
                )
            )
        return groups

    # -- monthly -------------------------------------------------------------------------
    def _monthly(
        self,
        wb: Workbook,
        records: list[Rec],
        findings: list[Finding],
        counts: dict[str, int],
        sums: dict[tuple[str, str], dict[str, list[float | None]]],
    ) -> None:
        member = wb.sheet_member(MONTHLY)
        if member is None:
            findings.append(
                Finding(
                    "EXTRACTION_PARTIAL",
                    "warning",
                    f"sheet '{MONTHLY}' is absent.",
                    "monthly_sheet_missing",
                    blocked=["calculation"],
                )
            )
            counts["monthly_rows"] = 0
            return
        header: dict[str, str] = {}
        units: dict[str, tuple[str, str]] = {}
        n = 0
        conflicts: list[int] = []
        for rown, cells in wb.rows(member):
            by_col = {c.column: c for c in cells}
            if not header:
                header = _header(cells)
                missing = MONTHLY_REQUIRED - set(header)
                if missing:
                    findings.append(
                        Finding(
                            "EXTRACTION_PARTIAL",
                            "error",
                            f"monthly sheet lacks columns {sorted(missing)}.",
                            "monthly_columns_missing",
                            blocked=["calculation"],
                        )
                    )
                    counts["monthly_rows"] = 0
                    return
                continue
            if not units and header["Year"] not in by_col and header["Wellbore name"] not in by_col:
                for name, col in header.items():
                    c = by_col.get(col)
                    if name in MONTHLY_QUANTITIES and c is not None and c.text:
                        units[name] = (c.text.strip(), c.ref)
                continue
            name_cell = by_col.get(header["Wellbore name"])
            year, month = by_col.get(header["Year"]), by_col.get(header["Month"])
            if name_cell is None or year is None or month is None:
                continue
            y, m = parse_number(year.text), parse_number(month.text)
            if y is None or m is None or not 1 <= m <= 12:
                findings.append(
                    Finding(
                        "EXTRACTION_PARTIAL",
                        "warning",
                        f"monthly row {rown} has an invalid year/month.",
                        f"monthly_bad_period:{rown}",
                        locators=[_loc(MONTHLY, f"A{rown}:J{rown}")],
                    )
                )
                continue
            n += 1
            label = (name_cell.text or "").strip()
            period = f"{int(y):04d}-{int(m):02d}"
            eff = event_time(period, "Year/Month")
            subject = {
                "well_name": label,
                "wellbore_name": label,
                "wellbore_label": label,
                "well_key": well_key(label),
                "npd_wellbore_code": (
                    by_col.get(header.get("NPDCode", "")) or Cell("", "", 0, None)
                ).text,
            }
            attrs = [
                Attr(
                    "production_month.period",
                    _loc(MONTHLY, f"{year.column}{rown}:{month.column}{rown}"),
                    original_text=f"{year.text}/{month.text}",
                    text=period,
                )
            ]
            for col_name, key in MONTHLY_QUANTITIES.items():
                mcol = header.get(col_name)
                if mcol is None:
                    continue
                unit, uref = units.get(col_name, (None, None))
                attrs.append(
                    _q(
                        MONTHLY,
                        f"production_month.{key}",
                        by_col.get(mcol),
                        f"{mcol}{rown}",
                        unit,
                        uref,
                    )
                )
            rec = Rec(
                "production_month", subject, _loc(MONTHLY, f"A{rown}:J{rown}"), attrs, eff, None
            )
            records.append(rec)
            ordinal = len(records) - 1
            daily = sums.get((str(subject["npd_wellbore_code"]), period))
            oil = next((a for a in attrs if a.key == "production_month.oil"), None)
            vals = daily.get("bore_oil_vol") if daily else None
            if oil and oil.number is not None and vals and all(v is not None for v in vals):
                total = sum(v for v in vals if v is not None)
                if abs(total - oil.number) > max(1.0, 0.01 * abs(oil.number)):
                    conflicts.append(ordinal)
                    oil.validation_state = "conflicting"
        counts["monthly_rows"] = n
        if "Oil" in header and not units:
            findings.append(
                Finding(
                    MISSING_UNIT,
                    "warning",
                    "monthly sheet has no unit row; units are not assumed.",
                    "monthly_units_missing",
                    ["production_month.oil"],
                    blocked=["calculation"],
                )
            )
        _aggregate(
            findings,
            "monthly_vs_daily_oil",
            REFERENCE_CONFLICT,
            "warning",
            conflicts,
            records,
            "monthly oil total(s) differ from the sum of the daily rows for the same wellbore and month "
            "(>1%); both values are kept, neither is preferred.",
            ["production_month.oil", "production_day.bore_oil_vol"],
            ["calculation"],
        )


def _unit_missing(findings: list[Finding], sheet: str, records: list[Rec]) -> None:
    idx = [i for i, r in enumerate(records) if r.kind == "production_day"]
    if idx:
        findings.append(
            Finding(
                MISSING_UNIT,
                "warning",
                "the daily sheet gives no unit for volumes, pressures, temperatures or hours "
                "(only the choke size has one); units are not copied from the monthly sheet and "
                "daily values are not normalized.",
                "daily_units_missing",
                [f"production_day.{k}" for k in ("bore_oil_vol", "bore_gas_vol", "avg_whp_p")],
                idx[:50],
                [records[i].locator for i in idx[:3]],
                ["calculation", "calculation"],
            )
        )


def _aggregate(
    findings: list[Finding],
    key: str,
    code: str,
    severity: Any,
    ordinals: list[int],
    records: list[Rec],
    message: str,
    attribute_keys: list[str],
    blocked: list[str],
) -> None:
    if not ordinals:
        return
    findings.append(
        Finding(
            code,
            severity,
            f"{len(ordinals)} {message}",
            key,
            attribute_keys,
            ordinals[:50],
            [records[o].locator for o in ordinals[:5]],
            blocked,
        )
    )

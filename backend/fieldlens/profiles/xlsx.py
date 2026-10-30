"""Stdlib-only streaming ``.xlsx`` reader (zip + hardened expat; no formulas evaluated).

Zip members are size-capped while being read (decompression-bomb guard) and names are never
used as filesystem paths. Excel date serials are interpreted only for date-formatted cells and
the raw serial is kept beside the ISO date."""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import IO

from .safexml import split_name, stream_xml
from .types import MAX_XLSX_MEMBER_BYTES, ProfileError

_BUILTIN_DATE_IDS = frozenset(set(range(14, 23)) | {45, 46, 47})
_DATE_TOKEN = re.compile(r"[dmyhs]", re.IGNORECASE)
_QUOTED = re.compile(r'"[^"]*"|\\.|\[[^\]]*\]')
_COL = re.compile(r"^([A-Z]+)(\d+)$")


@dataclass(frozen=True)
class Cell:
    ref: str
    column: str
    row: int
    text: str | None  # displayed/stored text, None when empty
    is_date: bool = False
    raw: str | None = None  # raw numeric serial when is_date
    iso: str | None = None
    precision: str | None = None  # day | instant


class _StopRows(Exception):
    pass


class _Capped:
    def __init__(self, handle: IO[bytes], limit: int) -> None:
        self.handle, self.limit, self.read_total = handle, limit, 0

    def read(self, n: int = -1) -> bytes:
        data = self.handle.read(n)
        self.read_total += len(data)
        if self.read_total > self.limit:
            raise ProfileError("zip_member_too_large", "xlsx member exceeds the size limit")
        return data


def _member(zf: zipfile.ZipFile, name: str) -> _Capped:
    info = zf.getinfo(name)
    if info.file_size > MAX_XLSX_MEMBER_BYTES:
        raise ProfileError("zip_member_too_large", f"{name} exceeds the size limit")
    return _Capped(zf.open(info), MAX_XLSX_MEMBER_BYTES)


def _is_date_format(code: str) -> bool:
    return bool(_DATE_TOKEN.search(_QUOTED.sub("", code)))


def serial_to_iso(serial: float, date1904: bool) -> tuple[str, str]:
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    dt = base + timedelta(days=serial)
    if abs(serial - round(serial)) < 1e-9:
        return date(dt.year, dt.month, dt.day).isoformat(), "day"
    return dt.replace(microsecond=0).isoformat(), "instant"


class Workbook:
    def __init__(self, path: Path) -> None:
        try:
            self.zf = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise ProfileError("xlsx_malformed", "not a valid xlsx container") from exc
        names = set(self.zf.namelist())
        if "xl/workbook.xml" not in names:
            raise ProfileError("xlsx_malformed", "xl/workbook.xml is missing")
        self.date1904 = False
        self.sheets: list[tuple[str, str]] = []  # (name, member path)
        self._read_workbook(names)
        self.shared = self._read_shared(names)
        self.date_styles = self._read_styles(names)

    def close(self) -> None:
        self.zf.close()

    def _read_workbook(self, names: set[str]) -> None:
        sheets: list[tuple[str, str]] = []

        def start(name: str, attrs: dict[str, str], depth: int, line: int) -> None:
            _, local = split_name(name)
            if local == "workbookPr":
                self.date1904 = attrs.get("date1904") in ("1", "true")
            elif local == "sheet":
                rid = next((v for k, v in attrs.items() if split_name(k)[1] == "id"), "")
                sheets.append((attrs.get("name", ""), rid))

        stream_xml(_member(self.zf, "xl/workbook.xml"), on_start=start, on_end=lambda *a: None)
        rels: dict[str, str] = {}

        def rel_start(name: str, attrs: dict[str, str], depth: int, line: int) -> None:
            if split_name(name)[1] == "Relationship":
                rels[attrs.get("Id", "")] = attrs.get("Target", "")

        if "xl/_rels/workbook.xml.rels" in names:
            stream_xml(
                _member(self.zf, "xl/_rels/workbook.xml.rels"),
                on_start=rel_start,
                on_end=lambda *a: None,
            )
        for name, rid in sheets:
            target = rels.get(rid, "")
            member = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
            if member in names:
                self.sheets.append((name, member))

    def _read_shared(self, names: set[str]) -> list[str]:
        out: list[str] = []
        if "xl/sharedStrings.xml" not in names:
            return out
        buf: list[str] = []
        in_rph = 0

        def start(name: str, attrs: dict[str, str], depth: int, line: int) -> None:
            nonlocal in_rph
            if split_name(name)[1] == "rPh":
                in_rph += 1

        def end(name: str, text: str, depth: int) -> None:
            nonlocal in_rph
            local = split_name(name)[1]
            if local == "rPh":
                in_rph -= 1
            elif local == "t" and not in_rph:
                buf.append(text)
            elif local == "si":
                out.append("".join(buf))
                buf.clear()

        stream_xml(_member(self.zf, "xl/sharedStrings.xml"), on_start=start, on_end=end)
        return out

    def _read_styles(self, names: set[str]) -> frozenset[int]:
        if "xl/styles.xml" not in names:
            return frozenset()
        custom: dict[int, str] = {}
        xfs: list[int] = []
        in_cell_xfs = False

        def start(name: str, attrs: dict[str, str], depth: int, line: int) -> None:
            nonlocal in_cell_xfs
            local = split_name(name)[1]
            if local == "numFmt":
                custom[int(attrs.get("numFmtId", "-1"))] = attrs.get("formatCode", "")
            elif local == "cellXfs":
                in_cell_xfs = True
            elif local == "xf" and in_cell_xfs:
                xfs.append(int(attrs.get("numFmtId", "0")))

        def end(name: str, text: str, depth: int) -> None:
            nonlocal in_cell_xfs
            if split_name(name)[1] == "cellXfs":
                in_cell_xfs = False

        stream_xml(_member(self.zf, "xl/styles.xml"), on_start=start, on_end=end)
        return frozenset(
            i
            for i, fid in enumerate(xfs)
            if fid in _BUILTIN_DATE_IDS or (fid in custom and _is_date_format(custom[fid]))
        )

    def sheet_member(self, name: str) -> str | None:
        return next((m for n, m in self.sheets if n == name), None)

    def rows(
        self, member: str, max_rows: int = 2_000_000, stop_after: int | None = None
    ) -> Iterator[tuple[int, list[Cell]]]:
        """Yield (row number, non-empty cells). Materialized per row via a buffered list."""
        result: list[tuple[int, list[Cell]]] = []
        state: dict[str, object] = {"cur": None, "row": 0}
        cells: list[Cell] = []
        in_is = 0

        def start(name: str, attrs: dict[str, str], depth: int, line: int) -> None:
            nonlocal in_is
            local = split_name(name)[1]
            if local == "row":
                cells.clear()
                state["row"] = int(attrs.get("r", "0") or 0)
            elif local == "c":
                state["cur"] = (attrs.get("r", ""), attrs.get("t", "n"), int(attrs.get("s", "0")))
                state["v"] = None
                state["is"] = []
            elif local == "is":
                in_is += 1

        def end(name: str, text: str, depth: int) -> None:
            nonlocal in_is
            local = split_name(name)[1]
            if local == "v":
                state["v"] = text
            elif local == "t" and in_is:
                state["is"].append(text)  # type: ignore[attr-defined]
            elif local == "is":
                in_is -= 1
            elif local == "c" and state["cur"] is not None:
                ref, typ, style = state["cur"]  # type: ignore[misc]
                m = _COL.match(ref)
                col, row = (m.group(1), int(m.group(2))) if m else ("", int(state["row"]))  # type: ignore[arg-type]
                cell = self._cell(ref, col, row, typ, style, state.get("v"), state.get("is"))  # type: ignore[arg-type]
                if cell is not None:
                    cells.append(cell)
                state["cur"] = None
            elif local == "row":
                if cells:
                    result.append((int(state["row"]), list(cells)))  # type: ignore[arg-type]
                    if stop_after is not None and len(result) >= stop_after:
                        raise _StopRows
                    if len(result) > max_rows:
                        raise ProfileError("xlsx_too_many_rows", "sheet exceeds the row limit")

        try:
            stream_xml(_member(self.zf, member), on_start=start, on_end=end)
        except _StopRows:
            pass
        yield from result

    def _cell(
        self,
        ref: str,
        col: str,
        row: int,
        typ: str,
        style: int,
        v: str | None,
        inline: list[str] | None,
    ) -> Cell | None:
        if typ == "inlineStr":
            text = "".join(inline or [])
            return Cell(ref, col, row, text) if text.strip() else None
        if v is None or v == "":
            return None
        if typ == "s":
            try:
                text = self.shared[int(v)]
            except (ValueError, IndexError):
                return Cell(ref, col, row, None)
            return Cell(ref, col, row, text) if text.strip() else None
        if typ in ("str", "b", "e"):
            return Cell(ref, col, row, v)
        if style in self.date_styles:
            try:
                iso, prec = serial_to_iso(float(v), self.date1904)
            except (ValueError, OverflowError):
                return Cell(ref, col, row, v)
            return Cell(ref, col, row, v, True, v, iso, prec)
        return Cell(ref, col, row, v)

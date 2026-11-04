"""Sections of stored non-PDF documents for the model step (TASK-115).

A stored document of family ``text``/``csv``/``xml``/``las``/``xlsx``/``ole`` becomes a list of text
*sections* (section ``n`` plays the role of page ``n``):

* text-decodable content (the stored encoding or content detection; the file name is never used) is
  cut into sections of at most :data:`SECTION_CHARS` characters on line boundaries;
* ``xlsx`` is rendered to tab-separated text per sheet with the standard library only (``zipfile`` +
  ``xml.etree``): no formula is evaluated, an XML entry that declares a DTD/entity is refused,
  and sheets, rows, columns, entries and sizes are capped;
* ``ole`` and files that are mostly not text give ONE bounded "binary preview" section (hex + ASCII
  of the first bytes, then printable-string runs). Nothing is executed or handed to a program.

Every reader is bounded in bytes, entries and time-proportional work. Content is untrusted data.
"""

from __future__ import annotations

import io
import re
import threading
import zipfile
from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal
from xml.etree import ElementTree as ET

from fieldlens.evidence.storage import BlobStore
from fieldlens.textenc import ENCODINGS, HEAD_BYTES, detect_encoding

SECTION_CHARS = 12_000
MAX_READ_BYTES = 8 * 1024 * 1024
MAX_SECTIONS = 500
FAMILIES = frozenset({"text", "csv", "xml", "las", "xlsx", "ole"})

PREVIEW_HEX_BYTES = 4096
PREVIEW_STRING_BYTES = 8192
PREVIEW_SCAN_BYTES = 2 * 1024 * 1024
PREVIEW_MIN_RUN = 6
PREVIEW_LABEL = (
    "[BINARY PREVIEW: unknown binary file, not text. First 4 KiB as hex + ASCII, then printable "
    "strings. Answer category null with no identities unless the strings name a well or wellbore.]"
)

XLSX_MAX_SHEETS = 20
XLSX_MAX_ROWS = 200
XLSX_MAX_COLS = 30
XLSX_MAX_ENTRIES = 2000
XLSX_MAX_ENTRY_BYTES = 16 * 1024 * 1024
XLSX_MAX_TOTAL_BYTES = 64 * 1024 * 1024
XLSX_MAX_SHARED_STRINGS = 100_000
XLSX_MAX_CELL_CHARS = 1000

ReadKind = Literal["text", "binary_preview"]
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_RUN = re.compile(rb"[\x20-\x7e]{%d,}" % PREVIEW_MIN_RUN)


class DocumentTextError(Exception):
    """A typed, non-sensitive refusal (``code`` is stable)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DocumentSections:
    sections: tuple[str, ...]
    kind: ReadKind
    truncated: bool = False


def split_sections(text: str, limit: int = SECTION_CHARS) -> list[str]:
    """Cut on line boundaries into pieces of at most ``limit`` characters (an over-long line is
    cut hard). Blank-only pieces are dropped."""
    text = _CONTROL.sub("", text.replace("\r\n", "\n").replace("\r", "\n"))
    out: list[str] = []
    buffer: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal buffer, size
        piece = "".join(buffer)
        if piece.strip():
            out.append(piece.rstrip("\n"))
        buffer, size = [], 0

    for line in text.splitlines(keepends=True):
        while len(line) > limit:  # a single huge line: hard cut
            if size:
                flush()
            out.append(line[:limit])
            line = line[limit:]
        if size + len(line) > limit:
            flush()
        buffer.append(line)
        size += len(line)
    flush()
    return out


# -- binary preview ---------------------------------------------------------------------------
def binary_preview(data: bytes) -> str:
    """Bounded preview of an unknown binary: hex+ASCII of the first 4 KiB, then printable runs."""
    lines: list[str] = []
    head = data[:PREVIEW_HEX_BYTES]
    for offset in range(0, len(head), 16):
        chunk = head[offset : offset + 16]
        hexes = " ".join(f"{b:02x}" for b in chunk).ljust(47)
        ascii_ = "".join(chr(b) if 0x20 <= b <= 0x7E else "." for b in chunk)
        lines.append(f"{offset:08x}  {hexes}  |{ascii_}|")
    runs: list[str] = []
    budget = PREVIEW_STRING_BYTES
    for match in _RUN.finditer(data[:PREVIEW_SCAN_BYTES]):
        run = match.group().decode("ascii")[:200]
        if len(run) + 1 > budget:
            break
        runs.append(run)
        budget -= len(run) + 1
    return "\n".join([PREVIEW_LABEL, *lines, "--- printable strings ---", *runs])


# -- xlsx -------------------------------------------------------------------------------------
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _iterparse(data: bytes) -> Iterator[tuple[str, ET.Element]]:
    # every part was screened for <!DOCTYPE/<!ENTITY by _refuse_dtd first, and expat never
    # fetches external entities, so there is nothing to expand
    return ET.iterparse(io.BytesIO(data), events=("end",))  # noqa: S314


def _read_entry(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    if info.file_size > XLSX_MAX_ENTRY_BYTES:
        raise DocumentTextError("workbook_too_large", "a workbook part is too large")
    with zf.open(info) as handle:
        data = handle.read(XLSX_MAX_ENTRY_BYTES + 1)
    if len(data) > XLSX_MAX_ENTRY_BYTES:
        raise DocumentTextError("workbook_too_large", "a workbook part is too large")
    return data


def _refuse_dtd(name: str, data: bytes) -> None:
    probe = data.lower()
    if b"<!doctype" in probe or b"<!entity" in probe:
        raise DocumentTextError(
            "unsafe_workbook", "the workbook declares an XML DTD/entity and was refused"
        )
    # UTF-16 encoded parts: look at the decoded text too
    if probe[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16", errors="replace").lower()
        if "<!doctype" in text or "<!entity" in text:
            raise DocumentTextError(
                "unsafe_workbook", "the workbook declares an XML DTD/entity and was refused"
            )


def _cell_text(value: str | None) -> str:
    return _CONTROL.sub("", (value or "").replace("\t", " ").replace("\n", " ").replace("\r", " "))[
        :XLSX_MAX_CELL_CHARS
    ]


def _column_index(ref: str) -> int | None:
    letters = re.match(r"[A-Za-z]+", ref)
    if not letters:
        return None
    value = 0
    for ch in letters.group().upper():
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def _shared_strings(data: bytes) -> list[str]:
    out: list[str] = []
    for _, elem in _iterparse(data):
        if _local(elem.tag) == "si":
            out.append(
                _cell_text("".join(t.text or "" for t in elem.iter() if _local(t.tag) == "t"))
            )
            elem.clear()
            if len(out) >= XLSX_MAX_SHARED_STRINGS:
                break
    return out


def _sheet_rows(data: bytes, shared: list[str]) -> list[str]:
    rows: list[str] = []
    for _, elem in _iterparse(data):
        if _local(elem.tag) != "row":
            continue
        cells: dict[int, str] = {}
        next_col = 0
        for cell in elem:
            if _local(cell.tag) != "c":
                continue
            col = _column_index(cell.get("r", ""))
            col = next_col if col is None else col
            next_col = col + 1
            if col >= XLSX_MAX_COLS:
                continue
            kind = cell.get("t", "n")
            value = ""
            for child in cell:
                name = _local(child.tag)
                if name == "v" and kind != "inlineStr":
                    value = child.text or ""
                elif name == "is":
                    value = "".join(t.text or "" for t in child.iter() if _local(t.tag) == "t")
            if kind == "s":
                try:
                    value = shared[int(value)]
                except (ValueError, IndexError):
                    value = ""
            elif kind == "b":
                value = "TRUE" if value.strip() == "1" else "FALSE"
            cells[col] = _cell_text(value)  # a formula's <f> is never read, only its stored <v>
        elem.clear()
        if not cells:
            continue
        last = max(cells)
        rows.append("\t".join(cells.get(i, "") for i in range(last + 1)))
        if len(rows) >= XLSX_MAX_ROWS:
            break
    return rows


def xlsx_text(data: bytes) -> str:
    """Tab-separated text per sheet (names included). Raises :class:`DocumentTextError`."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentTextError("not_a_workbook", "the file is not a readable workbook") from exc
    with zf:
        infos = zf.infolist()
        if len(infos) > XLSX_MAX_ENTRIES:
            raise DocumentTextError("workbook_too_large", "the workbook has too many parts")
        if sum(i.file_size for i in infos) > XLSX_MAX_TOTAL_BYTES:
            raise DocumentTextError("workbook_too_large", "the workbook expands too large")
        by_name = {i.filename: i for i in infos}
        loaded: dict[str, bytes] = {}
        for info in infos:  # every XML part is screened, parsed or not
            if info.filename.lower().endswith((".xml", ".rels")):
                payload = _read_entry(zf, info)
                _refuse_dtd(info.filename, payload)
                loaded[info.filename] = payload
        workbook = loaded.get("xl/workbook.xml")
        if workbook is None:
            raise DocumentTextError("not_a_workbook", "the file is not a readable workbook")
        rels: dict[str, str] = {}
        rels_data = loaded.get("xl/_rels/workbook.xml.rels")
        try:
            if rels_data is not None:
                for _, elem in _iterparse(rels_data):
                    if _local(elem.tag) == "Relationship":
                        rels[elem.get("Id", "")] = elem.get("Target", "")
            sheets: list[tuple[str, str]] = []
            for _, elem in _iterparse(workbook):
                if _local(elem.tag) == "sheet":
                    rid = next((v for k, v in elem.attrib.items() if _local(k) == "id"), "")
                    sheets.append((elem.get("name", "sheet"), rels.get(rid, "")))
            shared = (
                _shared_strings(loaded["xl/sharedStrings.xml"])
                if ("xl/sharedStrings.xml" in loaded)
                else []
            )
            parts: list[str] = []
            for name, target in sheets[:XLSX_MAX_SHEETS]:
                path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
                data_part = loaded.get(path)
                if data_part is None and path in by_name:
                    data_part = _read_entry(zf, by_name[path])
                    _refuse_dtd(path, data_part)
                rows = _sheet_rows(data_part, shared) if data_part is not None else []
                parts.append("\n".join([f"SHEET: {_cell_text(name)}", *rows]))
        except ET.ParseError as exc:
            raise DocumentTextError("not_a_workbook", "the workbook XML is not readable") from exc
    return "\n\n".join(parts)


# -- reader -----------------------------------------------------------------------------------
class DocumentTextReader:
    """Sections of stored non-PDF documents, memoized by (storage key, family, encoding).
    Stored documents are immutable, so the key is the content."""

    def __init__(self, store: BlobStore, limit: int = 8) -> None:
        self._store = store
        self._cache: OrderedDict[tuple[str, str, str | None], DocumentSections] = OrderedDict()
        self._lock = threading.Lock()
        self._limit = limit

    def sections(
        self, storage_key: str, family: str, encoding: str | None = None
    ) -> DocumentSections:
        if family not in FAMILIES:
            raise DocumentTextError("unsupported_family", "this document family is not readable")
        key = (storage_key, family, encoding)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        value = self._build(storage_key, family, encoding)
        with self._lock:
            self._cache[key] = value
            while len(self._cache) > self._limit:
                self._cache.popitem(last=False)
        return value

    def count(self, storage_key: str, family: str, encoding: str | None = None) -> int:
        return len(self.sections(storage_key, family, encoding).sections)

    def _read(self, storage_key: str) -> tuple[bytes, bool]:
        try:
            path = self._store.path_for(storage_key)
            with path.open("rb") as handle:
                data = handle.read(MAX_READ_BYTES + 1)
        except (ValueError, OSError) as exc:
            raise DocumentTextError(
                "document_unavailable", "document content is unavailable"
            ) from exc
        return data[:MAX_READ_BYTES], len(data) > MAX_READ_BYTES

    def _build(self, storage_key: str, family: str, encoding: str | None) -> DocumentSections:
        data, cut = self._read(storage_key)
        if not data:
            raise DocumentTextError("empty_document", "the document is empty")
        if family == "xlsx":
            if cut:
                raise DocumentTextError("workbook_too_large", "the workbook is too large to read")
            try:
                text = xlsx_text(data)
            except DocumentTextError as exc:
                if exc.code != "not_a_workbook":
                    raise
                return self._preview(data, cut)
            return self._text_sections(text, cut)
        if family != "ole":
            codec = encoding if encoding in ENCODINGS else detect_encoding(data[:HEAD_BYTES])
            if codec is not None:
                return self._text_sections(
                    data.decode(codec, errors="replace").lstrip("\ufeff"), cut
                )
        return self._preview(data, cut)

    @staticmethod
    def _text_sections(text: str, cut: bool) -> DocumentSections:
        parts = split_sections(text)
        if not parts:
            raise DocumentTextError("empty_document", "the document has no readable text")
        truncated = cut or len(parts) > MAX_SECTIONS
        return DocumentSections(tuple(parts[:MAX_SECTIONS]), "text", truncated)

    @staticmethod
    def _preview(data: bytes, cut: bool) -> DocumentSections:
        return DocumentSections((binary_preview(data),), "binary_preview", cut)

"""Inert inspection of a staged upload: signature, hostile-structure and size checks.

Nothing here parses engineering content, decompresses archives to disk, evaluates XML, opens a
network connection or runs file content. ZIP containers are judged from their central directory
(plus a 4-byte magic peek per entry); XML is scanned for DTD/entity markers byte-wise, never
parsed. Failures are explicit ``ContractError``s (413 size, 415 signature, 422 structure).
"""

from __future__ import annotations

import codecs
import re
import stat
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path

from fieldlens.contracts.errors import ContractError, ErrorCode

HEAD_BYTES = 64 * 1024
SCAN_CHUNK = 1024 * 1024
MAX_ZIP_ENTRIES = 2000
MAX_COMPRESSION_RATIO = 1000
CLASSIFICATION_METHOD = "local_signature"
CLASSIFICATION_VERSION = "1"

_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_EXECUTABLE_MAGICS = (
    b"MZ",
    b"\x7fELF",
    b"#!",
    b"\xfe\xed\xfa\xce",
    b"\xfe\xed\xfa\xcf",
    b"\xce\xfa\xed\xfe",
    b"\xcf\xfa\xed\xfe",
    b"\xca\xfe\xba\xbe",
)
_NESTED_EXTENSIONS = (".zip", ".jar", ".war", ".7z", ".rar", ".gz", ".tgz", ".tar", ".bz2", ".xz")
_ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_DTD_MARKERS = (b"<!doctype", b"<!entity")
_LAS_HEADER = re.compile(rb"^[ \t]*~[Vv]", re.MULTILINE)
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_MAX_MARKER = max(len(m) for m in _DTD_MARKERS) * 2


@dataclass(frozen=True)
class Detected:
    """Detection result. ``extraction_state`` is never 'extracted': no reader exists yet."""

    format_family: str
    media_type: str
    extraction_state: str  # pending_extraction | unsupported
    suggested_categories: tuple[str, ...] = ()
    expanded_bytes: int = 0


def reject(
    status: int, code: ErrorCode, reason: str, message: str, **details: object
) -> ContractError:
    return ContractError(code, message, status, {"reason": reason, **details})


def validate_filename(raw: str) -> str:
    """Filenames are hints, never paths: separators, dot-segments and controls are refused."""
    if (
        not raw
        or len(raw) > 512
        or _CONTROL.search(raw)
        or "/" in raw
        or "\\" in raw
        or raw in {".", ".."}
        or raw != raw.strip()
        or any(0xD800 <= ord(ch) <= 0xDFFF for ch in raw)
    ):
        raise reject(
            422,
            ErrorCode.VALIDATION_ERROR,
            "unsafe_filename",
            "file name must be a plain name without path segments or control characters",
        )
    return raw


def inspect_file(
    path: Path, filename: str, *, max_file_bytes: int, remaining_batch_bytes: int
) -> Detected:
    size = path.stat().st_size
    if size == 0:
        raise reject(422, ErrorCode.VALIDATION_ERROR, "empty_file", "empty files are not accepted")
    with path.open("rb") as handle:
        head = handle.read(HEAD_BYTES)

    if head.startswith(_ZIP_MAGICS):
        return _inspect_zip(path, max_file_bytes, remaining_batch_bytes)
    if head.startswith(b"%PDF-"):
        return Detected("pdf", "application/pdf", "pending_extraction")
    if head.startswith(_OLE):
        return Detected("ole", "application/x-ole-storage", "pending_extraction")
    if head.startswith(_EXECUTABLE_MAGICS):
        raise reject(
            415,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "executable_content",
            "executable or script content is not accepted",
        )
    text_kind = _text_kind(head)
    if text_kind is None:
        raise reject(
            415,
            ErrorCode.UNSUPPORTED_MEDIA_TYPE,
            "unsupported_signature",
            "file signature is not a supported source format",
        )
    stripped = head
    for bom in (codecs.BOM_UTF8, codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE):
        if stripped.startswith(bom):
            stripped = stripped[len(bom) :]
            break
    stripped = stripped.lstrip()
    if text_kind == "utf16":
        stripped = _ascii_of_utf16(head).lstrip().encode()
    if stripped.startswith(b"<"):
        _reject_dtd(path)
        return Detected("xml", "application/xml", "pending_extraction")
    if _LAS_HEADER.search(stripped[:HEAD_BYTES]):
        return Detected("las", "text/x-las", "pending_extraction", ("well_logs",))
    sniffed = _fixed_width_table(stripped)
    if sniffed is not None:
        return Detected("csv", "text/plain", "pending_extraction", sniffed)
    if filename.lower().endswith((".csv", ".dat")):
        return Detected("csv", "text/csv", "pending_extraction")
    return Detected("text", "text/plain", "unsupported")


def _fixed_width_table(head: bytes) -> tuple[str, ...] | None:
    """Content (not file name) recognizes the perforation / well-pick fixed-width tables."""
    text = head.decode("latin-1", "replace")
    first = text.splitlines()[0] if text else ""
    if all(t in first for t in ("Well name", "Top MD", "Base MD", "Perf obs#")):
        return ("perforation_history",)
    if re.search(r"^Well\s+\S", text, re.M) and "Surface name" in text and "Qlf" in text:
        return ("geology_reservoir",)
    return None


def _text_kind(head: bytes) -> str | None:
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf16"
    if b"\x00" in head:
        return None
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(head, final=False)  # a multibyte character may be cut at the 64 KiB edge
    except UnicodeDecodeError:
        return None
    return "utf8"


def _ascii_of_utf16(head: bytes) -> str:
    try:
        return head.decode("utf-16", errors="ignore")
    except UnicodeDecodeError:  # pragma: no cover - errors='ignore' never raises
        return ""


def _reject_dtd(path: Path) -> None:
    """DTD/entity declarations are forbidden outright: no external entity can ever be resolved."""
    patterns: list[bytes] = []
    for marker in _DTD_MARKERS:
        patterns += [
            marker,
            marker.decode().encode("utf-16-le"),
            marker.decode().encode("utf-16-be"),
        ]
    tail = b""
    with path.open("rb") as handle:
        while chunk := handle.read(SCAN_CHUNK):
            window = (tail + chunk).lower()
            if any(p in window for p in patterns):
                raise reject(
                    422,
                    ErrorCode.VALIDATION_ERROR,
                    "xml_dtd_forbidden",
                    "XML with a DOCTYPE or entity declaration is not accepted",
                )
            tail = window[-_MAX_MARKER:]


def _unsafe_entry_name(name: str) -> str | None:
    if "\x00" in name or _CONTROL.search(name):
        return "unsafe_entry_name"
    if name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name) or "\\" in name:
        return "absolute_entry_path"
    if ".." in name.split("/"):
        return "path_traversal"
    return None


def _inspect_zip(path: Path, max_file_bytes: int, remaining_batch_bytes: int) -> Detected:
    try:
        archive = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError, EOFError, NotImplementedError) as exc:
        raise reject(
            422, ErrorCode.VALIDATION_ERROR, "corrupt_archive", "archive is not readable"
        ) from exc
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise reject(
                422, ErrorCode.VALIDATION_ERROR, "too_many_entries", "archive has too many entries"
            )
        expanded = 0
        names: set[str] = set()
        for info in infos:
            bad = _unsafe_entry_name(info.filename)
            if bad:
                raise reject(422, ErrorCode.VALIDATION_ERROR, bad, "archive entry path is unsafe")
            if info.flag_bits & 0x1:
                raise reject(
                    422,
                    ErrorCode.VALIDATION_ERROR,
                    "encrypted_entry",
                    "encrypted archive entries are not accepted",
                )
            if info.create_system == 3 and stat.S_ISLNK(info.external_attr >> 16):
                raise reject(
                    422,
                    ErrorCode.VALIDATION_ERROR,
                    "symlink_entry",
                    "symbolic-link archive entries are not accepted",
                )
            if info.is_dir():
                continue
            names.add(info.filename)
            if info.filename.lower().endswith(_NESTED_EXTENSIONS):
                raise reject(
                    422,
                    ErrorCode.VALIDATION_ERROR,
                    "nested_archive",
                    "nested archives are not accepted",
                )
            if info.file_size > max_file_bytes:
                raise reject(
                    413,
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    "expanded_size",
                    "an archive entry expands beyond the per-file limit",
                    limit_bytes=max_file_bytes,
                )
            if (
                info.file_size > 1024 * 1024
                and info.compress_size > 0
                and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO
            ):
                raise reject(
                    422,
                    ErrorCode.VALIDATION_ERROR,
                    "compression_ratio",
                    "archive entry has an implausible compression ratio",
                )
            expanded += info.file_size
            if expanded > remaining_batch_bytes:
                raise reject(
                    413,
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    "expanded_size",
                    "archive expands beyond the remaining batch limit",
                    limit_bytes=remaining_batch_bytes,
                )
            try:
                with archive.open(info) as member:
                    peek = member.read(4)
            except (
                zipfile.BadZipFile,
                RuntimeError,
                NotImplementedError,
                EOFError,
                zlib.error,
            ) as exc:
                raise reject(
                    422, ErrorCode.VALIDATION_ERROR, "corrupt_archive", "archive is not readable"
                ) from exc
            if peek.startswith(_ZIP_MAGICS):
                raise reject(
                    422,
                    ErrorCode.VALIDATION_ERROR,
                    "nested_archive",
                    "nested archives are not accepted",
                )
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise reject(
                415,
                ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                "macro_content",
                "macro-enabled workbooks are not accepted",
            )
        if "[Content_Types].xml" in names and "xl/workbook.xml" in names:
            return Detected(
                "xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "pending_extraction",
                expanded_bytes=expanded,
            )
    raise reject(
        415,
        ErrorCode.UNSUPPORTED_MEDIA_TYPE,
        "unsupported_archive",
        "only XLSX workbooks are accepted as ZIP containers",
    )

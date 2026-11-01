"""Content-based text encoding detection (IN-11). The filename is never consulted.

Accepted: UTF-8 (with/without BOM), UTF-16 LE/BE (BOM, or BOM-less detected from the NUL-byte
pattern of mostly-ASCII text) and Windows-1252/Latin-1 style 8-bit text. An 8-bit stream is
refused when it contains NUL bytes or more than ``MAX_CONTROL_SHARE`` control bytes (anything
below 0x20 except TAB/LF/FF/CR, DEL, and the C1 bytes cp1252 leaves undefined), so real
binaries stay refused. BOM-less UTF-16 is only recognised for text whose code units are mostly
below U+0100 (ASCII/Latin); other BOM-less UTF-16 scripts remain unsupported. An 8-bit stream
is also refused when more than ``MAX_HIGH_SHARE`` of its bytes are >= 0x80: real Latin/cp1252 text
is mostly ASCII, while BOM-less UTF-16 CJK/other scripts look like high-byte-heavy mojibake.

Encoding is recorded from the whole file: a UTF-8 head is verified over the entire file in
bounded chunks (``refine_encoding``), so a late non-UTF-8 byte yields ``cp1252``.
"""

from __future__ import annotations

import codecs
from pathlib import Path
from typing import TextIO

HEAD_BYTES = 64 * 1024
MAX_CONTROL_SHARE = 0.01
_ALLOWED_CONTROLS = frozenset(b"\t\n\x0c\r")
_ASCII_CONTROLS = frozenset(
    b for b in range(256) if (b < 0x20 and b not in _ALLOWED_CONTROLS) or b == 0x7F
)
_CP1252_UNDEFINED = frozenset((0x81, 0x8D, 0x8F, 0x90, 0x9D))
_BAD_8BIT = _ASCII_CONTROLS | _CP1252_UNDEFINED
_ASCII_CONTROL_BYTES = bytes(sorted(_ASCII_CONTROLS))
_BAD_8BIT_BYTES = bytes(sorted(_BAD_8BIT))
_NUL_PATTERN_SHARE = 0.3
MAX_HIGH_SHARE = 0.25
SCAN_CHUNK = 1024 * 1024

ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252")


def _control_share_ok(data: bytes, bad: frozenset[int]) -> bool:
    if not data:
        return True
    count = sum(1 for b in data if b in bad)
    return count / len(data) <= MAX_CONTROL_SHARE


def _high_share_ok(data: bytes) -> bool:
    if not data:
        return True
    return sum(1 for b in data if b >= 0x80) / len(data) <= MAX_HIGH_SHARE


def _utf16_ok(data: bytes, codec: str) -> bool:
    decoder = codecs.getincrementaldecoder(codec)(errors="strict")
    try:
        text = decoder.decode(data, final=False)
    except UnicodeDecodeError:
        return False
    controls = sum(1 for ch in text if ord(ch) < 0x20 and ch not in "\t\n\x0c\r")
    return not text or controls / len(text) <= MAX_CONTROL_SHARE


def detect_encoding(head: bytes) -> str | None:
    """Return a Python codec name for text content, or ``None`` when the bytes are not text."""
    if head.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if head.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return "utf-16" if _utf16_ok(head, "utf-16") else None
    if b"\x00" in head:
        pairs = len(head) // 2
        if pairs < 2:
            return None
        even_zero = sum(1 for i in range(0, pairs * 2, 2) if head[i] == 0)
        odd_zero = sum(1 for i in range(1, pairs * 2, 2) if head[i] == 0)
        if odd_zero / pairs >= _NUL_PATTERN_SHARE and even_zero / pairs <= 0.01:
            return "utf-16-le" if _utf16_ok(head, "utf-16-le") else None
        if even_zero / pairs >= _NUL_PATTERN_SHARE and odd_zero / pairs <= 0.01:
            return "utf-16-be" if _utf16_ok(head, "utf-16-be") else None
        return None
    decoder = codecs.getincrementaldecoder("utf-8")()
    try:
        decoder.decode(head, final=False)  # a multibyte character may be cut at the head edge
    except UnicodeDecodeError:
        ok = _control_share_ok(head, _BAD_8BIT) and _high_share_ok(head)
        return "cp1252" if ok else None
    return "utf-8" if _control_share_ok(head, _ASCII_CONTROLS) else None


def decode_head(head: bytes, encoding: str) -> str:
    """Decode a head slice leniently (never raises); a cut trailing character is dropped."""
    text = codecs.getincrementaldecoder(encoding)(errors="replace").decode(head, final=False)
    return text.lstrip("\ufeff")


def refine_encoding(path: Path, encoding: str | None) -> str | None:
    """Verify a head-detected UTF-8 over the whole file (chunked, bounded memory).

    A decode error anywhere falls back to cp1252 when the whole file passes the 8-bit checks,
    otherwise ``None``. Other encodings are returned unchanged.
    """
    if encoding not in ("utf-8", "utf-8-sig"):
        return encoding
    decoder = codecs.getincrementaldecoder("utf-8")()  # carries cut multibyte sequences
    total = bad = ctrl = nul = high = 0
    valid = True
    with path.open("rb") as handle:
        while chunk := handle.read(SCAN_CHUNK):
            total += len(chunk)
            if valid:
                try:
                    decoder.decode(chunk, final=False)
                except UnicodeDecodeError:
                    valid = False
            nul += chunk.count(0)
            ctrl += len(chunk) - len(chunk.translate(None, _ASCII_CONTROL_BYTES))
            bad += len(chunk) - len(chunk.translate(None, _BAD_8BIT_BYTES))
            if not chunk.isascii():
                high += sum(1 for b in chunk if b >= 0x80)
    if nul:
        return None  # NUL bytes anywhere: not text (UTF-16 never reaches this check)
    if valid and total and ctrl / total > MAX_CONTROL_SHARE:
        return None
    if valid:
        try:
            decoder.decode(b"", final=True)
        except UnicodeDecodeError:
            valid = False
    if valid:
        return encoding
    if total == 0 or bad / total > MAX_CONTROL_SHARE or high / total > MAX_HIGH_SHARE:
        return None
    return "cp1252"


def sniff_path(path: Path) -> str | None:
    with path.open("rb") as handle:
        head = handle.read(HEAD_BYTES)
    return refine_encoding(path, detect_encoding(head))


def open_text(path: Path) -> TextIO:
    """Open a staged text source with its content-detected encoding (Latin-1 if undetectable)."""
    encoding = sniff_path(path) or "latin-1"
    return path.open("r", encoding=encoding, errors="replace")


def read_head_text(path: Path, nbytes: int = 4096) -> str:
    """The first ``nbytes`` decoded with the content-detected encoding."""
    with path.open("rb") as handle:
        raw = handle.read(max(nbytes, HEAD_BYTES))
    encoding = refine_encoding(path, detect_encoding(raw[:HEAD_BYTES])) or "latin-1"
    return decode_head(raw, encoding)[:nbytes]

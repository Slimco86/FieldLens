"""Content-based text encoding detection (IN-11). The filename is never consulted.

Accepted: UTF-8 (with/without BOM), UTF-16 LE/BE (BOM, or BOM-less detected from the NUL-byte
pattern of mostly-ASCII text) and Windows-1252/Latin-1 style 8-bit text. An 8-bit stream is
refused when it contains NUL bytes or more than ``MAX_CONTROL_SHARE`` control bytes (anything
below 0x20 except TAB/LF/FF/CR, DEL, and the C1 bytes cp1252 leaves undefined), so real
binaries stay refused. BOM-less UTF-16 is only recognised for text whose code units are mostly
below U+0100 (ASCII/Latin); other BOM-less UTF-16 scripts remain unsupported.
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
_NUL_PATTERN_SHARE = 0.3

ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252")


def _control_share_ok(data: bytes, bad: frozenset[int]) -> bool:
    if not data:
        return True
    count = sum(1 for b in data if b in bad)
    return count / len(data) <= MAX_CONTROL_SHARE


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
        return "cp1252" if _control_share_ok(head, _BAD_8BIT) else None
    return "utf-8" if _control_share_ok(head, _ASCII_CONTROLS) else None


def decode_head(head: bytes, encoding: str) -> str:
    """Decode a head slice leniently (never raises); a cut trailing character is dropped."""
    text = codecs.getincrementaldecoder(encoding)(errors="replace").decode(head, final=False)
    return text.lstrip("\ufeff")


def sniff_path(path: Path) -> str | None:
    with path.open("rb") as handle:
        return detect_encoding(handle.read(HEAD_BYTES))


def open_text(path: Path) -> TextIO:
    """Open a staged text source with its content-detected encoding (Latin-1 if undetectable)."""
    encoding = sniff_path(path) or "latin-1"
    return path.open("r", encoding=encoding, errors="replace")


def read_head_text(path: Path, nbytes: int = 4096) -> str:
    """The first ``nbytes`` decoded with the content-detected encoding."""
    with path.open("rb") as handle:
        raw = handle.read(max(nbytes, HEAD_BYTES))
    encoding = detect_encoding(raw[:HEAD_BYTES]) or "latin-1"
    return decode_head(raw, encoding)[:nbytes]

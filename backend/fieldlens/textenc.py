"""Content-based text encoding detection (IN-11). The filename is never consulted.

Accepted: UTF-8 (with/without BOM), UTF-16 LE/BE (BOM, or BOM-less detected from the NUL-byte
pattern of mostly-ASCII text) and Windows-1252/Latin-1 style 8-bit text. An 8-bit stream is
refused when it contains NUL bytes or more than ``MAX_CONTROL_SHARE`` control bytes (anything
below 0x20 except TAB/LF/FF/CR, DEL, and the C1 bytes cp1252 leaves undefined), so real
binaries stay refused. BOM-less UTF-16 is only recognised for text whose code units are mostly
below U+0100 (ASCII/Latin); other BOM-less UTF-16 scripts remain unsupported. An 8-bit stream
is also screened for high-byte-heavy UTF-16 mojibake (BOM-less CJK/other scripts decode "cleanly"
under cp1252): up to ``LOW_HIGH_SHARE`` (25%) high bytes is accepted as before; between that and
``MAX_HIGH_SHARE`` (60%) it is accepted only when the high bytes are isolated, i.e. at most
``MAX_CLUSTERED_HIGH`` (45%) of them sit next to another high byte (accents sit between ASCII
letters in Spanish/French/Portuguese Latin-1 text, while UTF-16 CJK code units put high bytes
side by side: measured ~0.3 for very accent-dense Spanish, ~0.7 for UTF-16 CJK/Hangul);
above 60% it is always refused. In the same 25-60% range a byte-parity test also applies:
UTF-16 code units put a very regular byte at one parity (kana U+30xx -> constant 0x30, CJK
ideographs -> 0x4E-0x9F) and a broad one at the other, while cp1252 text has similar byte
distributions at both parities. The stream is refused when one parity's most common byte is at
least ``PARITY_TOP_SHARE`` (50%) of its bytes while the other parity's is at most
``PARITY_OTHER_TOP`` (25%) and under 40% of it, or when one parity keeps ``PARITY_WINDOW_SHARE``
(85%) of its bytes inside a 64-value window and the other at most ``PARITY_OTHER_WINDOW`` (60%)
(measured: 0.6-1.0 vs 0.02-0.2 for UTF-16 Japanese, <=0.29 vs the same value at both parities for
Spanish/French/accent-dense Latin-1, and equal at both parities for space-padded tables).
Run detection is per bounded chunk, so memory stays bounded and a run cut at a chunk edge is
under-counted by at most one byte.

Whole-file verification (``refine_encoding``) streams every 8-bit file, UTF-8-headed or
cp1252-headed: NUL bytes anywhere refuse it, control bytes are limited to ``MAX_CONTROL_SHARE`` of
the file, and the high-byte rules apply to the whole file and to every non-ASCII 64 KiB block of at
least ``MIN_CHUNK_CHECK`` bytes, so late BOM-less UTF-16 CJK is refused.

Encoding is recorded from the whole file: a UTF-8 head is verified over the entire file in
bounded chunks (``refine_encoding``), so a late non-UTF-8 byte yields ``cp1252``.
"""

from __future__ import annotations

import codecs
import re
from pathlib import Path
from typing import TextIO

import numpy as np

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
LOW_HIGH_SHARE = 0.25
MAX_HIGH_SHARE = 0.60
MAX_CLUSTERED_HIGH = 0.45
PARITY_TOP_SHARE = 0.50
PARITY_OTHER_TOP = 0.25
PARITY_WINDOW_SHARE = 0.85
PARITY_OTHER_WINDOW = 0.60
PARITY_WINDOW = 64
MIN_CHUNK_CHECK = 16 * 1024
_ASCII_BYTES = bytes(range(0x80))
_HIGH_RUN = re.compile(rb"[\x80-\xff]{2,}")
SCAN_CHUNK = 1024 * 1024

ENCODINGS = ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252")


def _control_share_ok(data: bytes, bad: frozenset[int]) -> bool:
    if not data:
        return True
    count = sum(1 for b in data if b in bad)
    return count / len(data) <= MAX_CONTROL_SHARE


def _clustered_high_bytes(data: bytes) -> int:
    """High bytes that sit in a run of two or more high bytes."""
    return sum(len(m) for m in _HIGH_RUN.findall(data))


def _parity_hist(data: bytes) -> np.ndarray:
    """Byte-value histograms at even/odd offsets (shape 2x256)."""
    arr = np.frombuffer(data, dtype=np.uint8)
    return np.stack([np.bincount(arr[p::2], minlength=256) for p in (0, 1)])


def _window_share(hist: np.ndarray) -> float:
    cum = np.concatenate(([0], np.cumsum(hist)))
    return float((cum[PARITY_WINDOW:] - cum[:-PARITY_WINDOW]).max() / cum[-1])


def _parity_regular(hist: np.ndarray) -> bool:
    """One parity strongly regular, the other broad: the signature of UTF-16 (see docstring)."""
    if hist[0].sum() == 0 or hist[1].sum() == 0:
        return False
    tops = [float(h.max() / h.sum()) for h in hist]
    wins = [_window_share(h) for h in hist]
    for a, b in ((0, 1), (1, 0)):
        if tops[a] >= PARITY_TOP_SHARE and tops[b] <= PARITY_OTHER_TOP and tops[b] <= tops[a] * 0.4:
            return True
        if wins[a] >= PARITY_WINDOW_SHARE and wins[b] <= PARITY_OTHER_WINDOW:
            return True
    return False


def _latin_share_ok(total: int, high: int, clustered: int, parity: np.ndarray | None) -> bool:
    """8-bit text is plausible Latin/cp1252 (not UTF-16 mojibake) - see the module docstring."""
    if total == 0 or high / total <= LOW_HIGH_SHARE:
        return True
    if high / total > MAX_HIGH_SHARE or clustered / high > MAX_CLUSTERED_HIGH:
        return False
    return parity is None or not _parity_regular(parity)


def _high_share_ok(data: bytes) -> bool:
    high = sum(1 for b in data if b >= 0x80)
    if not high:
        return True
    return _latin_share_ok(len(data), high, _clustered_high_bytes(data), _parity_hist(data))


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
    """Verify a head-detected 8-bit/UTF-8 encoding over the whole file (chunked, bounded memory).

    A UTF-8 decode error anywhere falls back to cp1252 when the whole file passes the 8-bit
    checks, otherwise ``None``; cp1252-headed files get the same NUL/control/high-byte/parity
    checks. Other encodings are returned unchanged.
    """
    if encoding not in ("utf-8", "utf-8-sig", "cp1252"):
        return encoding
    decoder = codecs.getincrementaldecoder("utf-8")()  # carries cut multibyte sequences
    total = bad = ctrl = nul = high = clustered = 0
    parity = np.zeros((2, 256), dtype=np.int64)
    valid = encoding != "cp1252"
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
            if chunk.isascii():
                continue
            for start in range(0, len(chunk), HEAD_BYTES):  # head-sized blocks: no dilution
                block = chunk[start : start + HEAD_BYTES]
                if block.isascii():
                    continue
                block_high = len(block.translate(None, _ASCII_BYTES))
                block_clustered = _clustered_high_bytes(block)
                block_parity = _parity_hist(block)
                high += block_high
                clustered += block_clustered
                parity += block_parity
                if (
                    len(block) >= MIN_CHUNK_CHECK
                    and not valid
                    and not _latin_share_ok(len(block), block_high, block_clustered, block_parity)
                ):
                    return None  # e.g. late BOM-less UTF-16 CJK after a clean head
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
    if total == 0 or bad / total > MAX_CONTROL_SHARE:
        return None
    return "cp1252" if _latin_share_ok(total, high, clustered, parity) else None


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

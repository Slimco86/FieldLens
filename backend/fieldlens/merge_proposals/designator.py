"""Well designators and name spellings for merge guards and quote checks. Pure functions.

A *designator* is block (optional), well slot (``F-12``) and suffix (``A``, ``T2``; none for the
base wellbore). It is extracted from free labels more loosely than the resolver's strict label
rule, but conservatively: a label with several different designators, or no slot, has none; a
trailing single letter or known bore token is read as a suffix (so ``F-12 A`` is never ``F-12``).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from fieldlens.identity.labels import parse_bore_label

_SPACES = re.compile(r"\s+")
_SLOT = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(?:(?P<b1>\d{1,2})\s*[/_]\s*(?P<b2>\d{1,2})\s*-\s*)?"
    r"(?P<letter>[A-Za-z])\s?-?\s?(?P<num>\d{1,3})(?!\d)"
)
_SUFFIX_WORD = r"(?:(?:st|bt|aht|t)\d{1,2}|pilot|sr|ah|h|[A-Za-z]\d{0,2})"
_GLUED = re.compile(rf"(?P<s>{_SUFFIX_WORD})(?![A-Za-z0-9])", re.IGNORECASE)
_SPACED = re.compile(rf"^[\s\-_]+(?P<s>{_SUFFIX_WORD})(?![A-Za-z0-9])", re.IGNORECASE)
# What may follow a base designator in prose without making it a sidetrack: used by quote checks.
_TRAILING_SUFFIX = rf"(?![\s\-_]?{_SUFFIX_WORD}(?![A-Za-z0-9]))"

_PLANNED = re.compile(r"\b(?:plan|planned|prognosis|prognosed|proposed|prog)\b", re.IGNORECASE)
_AS_BUILT = re.compile(r"\b(?:as[\s\-]?built|actual|final|drilled)\b|\basbuilt\b", re.IGNORECASE)


@dataclass(frozen=True)
class Designator:
    block: str | None  # "15/9" (numerically normalized) or None
    slot: str  # "F-12"
    suffix: str | None  # canonical upper-case, None = base wellbore

    @property
    def key(self) -> str:
        base = f"{self.block}-{self.slot}" if self.block else self.slot
        return f"{base} {self.suffix}" if self.suffix else base


def _block(b1: str | None, b2: str | None) -> str | None:
    return f"{int(b1)}/{int(b2)}" if b1 is not None and b2 is not None else None


def normalize_text(value: str) -> str:
    """NFKC, case-folded, whitespace-collapsed; the form used for quote containment."""
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", value)).strip().casefold()


def extract_designator(label: str) -> Designator | None:
    """The one designator a label carries, or None (no slot, or several different ones)."""
    text = unicodedata.normalize("NFKC", label)
    found: dict[tuple[str | None, str, str | None], Designator] = {}
    for hit in _SLOT.finditer(text):
        slot = f"{hit.group('letter').upper()}-{int(hit.group('num'))}"
        rest = text[hit.end() :]
        suffix_match = _GLUED.match(rest) or _SPACED.match(rest)
        suffix = suffix_match.group("s").upper() if suffix_match else None
        d = Designator(_block(hit.group("b1"), hit.group("b2")), slot, suffix)
        found[(d.block, d.slot, d.suffix)] = d
    if len(found) != 1:
        return None
    return next(iter(found.values()))


def designator_of(name: str) -> Designator | None:
    """Strict resolver parse first (so keys round-trip), else the loose extraction."""
    parsed = parse_bore_label(name)
    if parsed is not None:
        block = None
        if parsed.block:
            b1, _, b2 = parsed.block.partition("/")
            block = _block(b1, b2)
        slot = parsed.well_slot
        if slot[:1].isalpha():
            slot = f"{slot[0].upper()}-{int(slot[2:])}"
        return Designator(block, slot, parsed.suffix)
    return extract_designator(name)


def status_marker(name: str) -> str | None:
    """Lexical planned / as-built marker of a name (None when unmarked)."""
    planned, built = bool(_PLANNED.search(name)), bool(_AS_BUILT.search(name))
    if planned and built:
        return "mixed"
    return "planned" if planned else "as_built" if built else None


def _slot_pattern(slot: str) -> str:
    letter, sep, num = slot.partition("-")
    if not sep:
        return rf"{re.escape(slot)}(?!\d)"
    return rf"{re.escape(letter)}\s?-?\s?0*{re.escape(num)}(?!\d)"


def designator_pattern(d: Designator, *, allow_short: bool) -> re.Pattern[str]:
    """Regex for spellings of a designator inside normalized text. A block-less spelling is only
    accepted when ``allow_short``; a base designator never matches a suffixed spelling, and a
    suffixed one only matches its own suffix."""
    slot = _slot_pattern(d.slot)
    if d.block:
        b1, _, b2 = d.block.partition("/")
        block = rf"0*{b1}\s*[/_]\s*0*{b2}\s*-\s*"
        body = rf"(?:{block}{slot}|{slot})" if allow_short else rf"{block}{slot}"
    else:
        body = slot
    if d.suffix:
        tail = rf"[\s\-_]?{re.escape(d.suffix)}(?![A-Za-z0-9])"
    else:
        tail = _TRAILING_SUFFIX
    return re.compile(rf"(?<![A-Za-z0-9]){body}{tail}", re.IGNORECASE)


def literal_pattern(text: str) -> re.Pattern[str]:
    """Boundary-delimited exact spelling (whitespace-flexible, case-insensitive)."""
    parts = [re.escape(p) for p in _SPACES.split(normalize_text(text)) if p]
    return re.compile(r"(?<![A-Za-z0-9])" + r"\s+".join(parts) + r"(?![A-Za-z0-9])", re.IGNORECASE)

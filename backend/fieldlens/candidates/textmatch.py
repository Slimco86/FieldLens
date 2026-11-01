"""Token-boundary text matching and strict number parsing for the validators (D1, D3).

Matching never lets a claim hide inside a longer token: ``3000`` is not in ``13000``, ``9.625`` is
not in ``19.625``, ``2500`` is not in ``-2500`` and ``5/8`` is not in ``9 5/8``. Parsing never
guesses: a decimal comma is accepted only in the unambiguous ``1234,5``/``4160,50`` shape, and
thousands separators, ``1.234,5`` and the like are reported as ambiguous."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .units import parse_unit

_MINUS = str.maketrans({"−": "-", "–": "-", "‒": "-", "‐": "-", "‑": "-"})
_SPACE = re.compile(r"\s+")


def norm(value: str) -> str:
    """NFKC, Unicode minus/dashes to ASCII '-', casefold, single spaces."""
    return _SPACE.sub(
        " ", unicodedata.normalize("NFKC", value).translate(_MINUS).casefold()
    ).strip()


def _boundary_ok(hay: str, start: int, end: int, claim: str) -> bool:
    before = hay[start - 1] if start > 0 else ""
    after = hay[end] if end < len(hay) else ""
    if before.isalnum() or (before != "" and before in ".,"):
        return False
    if before == "-" and not claim.startswith("-"):
        # "4160-4165" is a range separator; "-2500" is a negative number; "9-5/8" a mixed fraction
        prior = hay[start - 2] if start >= 2 else ""
        if not prior.isdigit() or ("/" in claim and " " not in claim):
            return False
    if (
        "/" in claim
        and " " not in claim
        and before in " "
        and start >= 2
        and hay[start - 2].isdigit()
    ):
        return False  # the tail of a mixed fraction
    if after.isalnum():
        return False
    if after != "" and after in ".,/" and end + 1 < len(hay) and hay[end + 1].isdigit():
        return False
    if (
        after == " "
        and re.match(r" \d+/\d+", hay[end:])
        and claim[-1:].isdigit()
        and "/" not in claim
    ):
        return False  # the whole part of a mixed fraction
    return True


def find_token(claim: str, haystack: str) -> int | None:
    """Index in the normalized haystack of a boundary-respecting occurrence, or None."""
    c, h = norm(claim), norm(haystack)
    if not c:
        return None
    pos = h.find(c)
    while pos != -1:
        if _boundary_ok(h, pos, pos + len(c), c):
            return pos
        pos = h.find(c, pos + 1)
    return None


def supported_in(claim: str, haystack: str) -> bool:
    return find_token(claim, haystack) is not None


def value_end(claim: str, haystack: str) -> tuple[str, int] | None:
    """(normalized haystack, end index of the claim's first valid occurrence)."""
    pos = find_token(claim, haystack)
    if pos is None:
        return None
    h = norm(haystack)
    return h, pos + len(norm(claim))


_UNIT_WORD = re.compile(r"^\s*(?:-\s*)?(\"|″|[a-z°]+)", re.IGNORECASE)


def unit_after(claim: str, haystack: str) -> str | None:
    """The unit word that directly follows the claimed value in the haystack, if it is a known
    unit (``3000 ft MD`` -> ``ft``); None when no unit is stated there."""
    found = value_end(claim, haystack)
    if found is None:
        return None
    h, end = found
    m = _UNIT_WORD.match(h[end:])
    if m is None:
        return None
    word = m.group(1).replace("″", '"')
    return word if parse_unit(word) is not None else None


_BRACKET_UNIT = re.compile(r"[(\[]\s*([a-z°\"]+)\s*[)\]]", re.IGNORECASE)


def context_units(text: str) -> set[str]:
    """Units a table header or context states in brackets, e.g. ``Depth (ft)``."""
    out = set()
    for m in _BRACKET_UNIT.finditer(norm(text)):
        if parse_unit(m.group(1)) is not None:
            out.add(m.group(1))
    return out


SIZE_AMBIGUOUS = "ambiguous size fraction"
# Unit words that are unambiguous as words ("in" and "c" are ordinary words, never searched for).
_AWAY_UNITS = frozenset(
    "ft feet foot m meter meters metre metres mm cm km inch inches psi bar kpa mpa".split()
)
_BRACKETED = re.compile(r"[(\[][^)\]]*[)\]]")
_WORD = re.compile(r"[a-z]+")


def unit_words(text: str) -> list[str]:
    """Recognised unit words written anywhere in the text (bracketed table-header units, which
    are context rather than part of a value, are not included)."""
    return [w for w in _WORD.findall(_BRACKETED.sub(" ", norm(text))) if w in _AWAY_UNITS]


@dataclass(frozen=True)
class NumberResult:
    value: float | None
    problem: str | None = None


_PLAIN = re.compile(r"^[+-]?\d+(?:\.\d+)?$|^[+-]?\.\d+$")
_COMMA = re.compile(r"^[+-]?\d+,\d{1,2}$")
_MIXED = re.compile(r"^([+-]?)(\d+)[ -](\d+)/(\d+)$")
_FRAC = re.compile(r"^([+-]?)(\d+)/(\d+)$")


def parse_quantity(text: str, *, allow_fraction: bool = False) -> NumberResult:
    """Strict number from a claimed value. Ambiguous or non-numeric text is a problem, never
    a guess; a leading Unicode minus is a negative sign."""
    t = norm(text)
    if _PLAIN.match(t):
        return NumberResult(float(t))
    if _COMMA.match(t):
        return NumberResult(float(t.replace(",", ".")))
    if allow_fraction:
        m = _MIXED.match(t)
        if m and int(m.group(4)) != 0:
            v = int(m.group(2)) + int(m.group(3)) / int(m.group(4))
            return NumberResult(-v if m.group(1) == "-" else v)
        f = _FRAC.match(t)
        if f and int(f.group(3)) != 0:
            if int(f.group(2)) > int(f.group(3)):
                # "95/8" is far more likely a mixed number that lost its space (9 5/8); a size
                # is never guessed from it
                return NumberResult(None, SIZE_AMBIGUOUS)
            v = int(f.group(2)) / int(f.group(3))
            return NumberResult(-v if f.group(1) == "-" else v)
    if "," in t or re.search(r"\d\.\d+\.\d", t):
        return NumberResult(None, "ambiguous separator")
    return NumberResult(None, "not a plain number")

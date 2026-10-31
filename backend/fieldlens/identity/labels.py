"""The ONE well/wellbore label rule, shared by retrieval (exact identifiers) and identity
resolution (``well``/``wellbore`` rows). Pure functions, no I/O.

Rule (documented, deterministic):

* Normalize: NFKC, lowercase for lookup, single spaces; a country prefix (``NO``, ``NOR``,
  ``NORWAY``) is not part of the name (``NO 15/9-F-12`` and ``15/9-F-12`` are one naming).
* A bore label is ``[block-]well[ suffix]``. ``block`` is ``<quad>/<block>`` (``15/9``); ``well``
  is a letter-prefixed slot (``F-12``, written ``F12`` in some sources) or a bare number
  (``19`` in ``15/9-19``); the optional ``suffix`` after the well names a distinct wellbore
  (``B`` in ``15/9-F-11 B``, ``T2``, ``AHT2``, ``BT2``, ``SR``, ``pilot``). A label with no suffix
  names the well's base wellbore. ``F-12`` and ``F-12 A`` are never the same bore.
* A short alias (``F-12`` for ``15/9-F-12``) drops only the block prefix; two blocks with an
  ``F-12`` give an explicit ambiguity, never a silent pick. Aliases never broaden a well to its
  sidetracks.
* Field-level labels such as ``Volve F`` do not parse as a bore label and are never wells.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_SPACES = re.compile(r"\s+")
COUNTRY = re.compile(r"^(no|nor|norway)\s+")
BLOCK = re.compile(r"^(\d{1,2}/\d{1,2})-(.+)$")
# Retrieval's historic suffix test (letter-prefixed wells only); kept unchanged so stored
# retrieval identifiers do not move. Identity resolution uses ``parse_bore_label`` below.
SIDETRACK = re.compile(r"^(?:\d{1,2}/\d{1,2}-)?[a-z]{1,2}-?\d{1,3}\s+\S")
# A short bore suffix typed after a well identifier: "F-12 A", "F-14 T2", "F-5 ST1".
SUFFIX_TOKEN = re.compile(r"^(?:[A-Z]\d{0,2}|(?i:t|st)\d{1,2})$")

# [block-]well[ suffix] on the normalized (lowercase, country-free) form.
_BORE = re.compile(
    r"^(?:(?P<block>\d{1,2}/\d{1,2})-)?"
    r"(?P<well>[a-z]-?\d{1,3}|\d{1,3})"
    r"(?:\s+(?P<suffix>[a-z0-9]+(?: [a-z0-9]+)?))?$"
)
MAX_SUFFIX_CHARS = 16


def norm_identifier(value: str) -> str:
    """Identifier normalization for exact lookup: lowercase, trimmed, single spaces.
    Punctuation (``/``, ``-``, ``.``) is preserved because it is part of the identifier."""
    return _SPACES.sub(" ", unicodedata.normalize("NFKC", value)).strip().lower()


def strip_country(normalized: str) -> str:
    return COUNTRY.sub("", normalized)


def aliases(label: str) -> list[str]:
    """Normalized label plus its block-stripped / country-stripped forms (never a parent)."""
    full = norm_identifier(label)
    out = [full]
    stripped = COUNTRY.sub("", full)
    if stripped != full:
        out.append(stripped)
    block = BLOCK.match(stripped)
    if block:
        out.append(block.group(2))
    return list(dict.fromkeys(out))


def unqualified(canonical: str) -> str | None:
    """``15/9-f-12`` -> ``f-12`` (None when the label carries no block prefix)."""
    match = BLOCK.match(COUNTRY.sub("", canonical))
    return match.group(2) if match else None


def has_suffix(label: str) -> bool:
    """True for a bore label with a suffix after the well name (``15/9-F-12 A``, ``F-1 C``):
    a distinct wellbore, never the parent well."""
    return bool(SIDETRACK.match(COUNTRY.sub("", norm_identifier(label))))


@dataclass(frozen=True)
class BoreLabel:
    block: str | None  # "15/9" or None for an unqualified spelling
    well_slot: str  # canonical slot: "F-12", "19"
    suffix: str | None  # canonical upper-case suffix, None = the base wellbore

    @property
    def well_name(self) -> str:
        return f"{self.block}-{self.well_slot}" if self.block else self.well_slot

    @property
    def wellbore_name(self) -> str:
        return f"{self.well_name} {self.suffix}" if self.suffix else self.well_name


def _slot(raw: str) -> str:
    return f"{raw[0].upper()}-{raw[1:].lstrip('-')}" if raw[0].isalpha() else raw


def parse_bore_label(label: str, suffix_hint: str | None = None) -> BoreLabel | None:
    """Parse one label; None when it is not a bore label (field-level names, free text).

    ``suffix_hint`` is a structured source suffix (``wellbore_suffix``) for a label that carries
    only the well name; a suffix written in the label itself wins only if they agree."""
    normalized = COUNTRY.sub("", norm_identifier(label))
    match = _BORE.match(normalized)
    if not match:
        return None
    if match.group("block") is None and match.group("well").isdigit():
        return None  # a bare number without a block is not a well name
    suffix = match.group("suffix")
    hint = norm_identifier(suffix_hint) if suffix_hint and suffix_hint.strip() else None
    if hint and suffix and hint != suffix:
        return None  # contradictory suffix spellings: not parseable as one identity
    suffix = suffix or hint
    if suffix and len(suffix) > MAX_SUFFIX_CHARS:
        return None
    return BoreLabel(
        match.group("block"),
        _slot(match.group("well")),
        suffix.upper() if suffix else None,
    )

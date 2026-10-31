"""Exact-identifier extraction (index side) and candidate generation (query side).

Identifiers are never invented: they are values a source wrote (well/wellbore labels, name and
model/part/serial-style attributes). A short alias (``F-12`` for ``15/9-F-12``) is added only by
dropping the block prefix, so two blocks that both contain an ``F-12`` produce an explicit
ambiguity instead of a silent pick. Aliases never broaden a well to its sidetracks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .text import norm_identifier

_SUBJECT_KINDS = {
    "well_key": "well",
    "well_name": "well",
    "wellbore_label": "wellbore",
    "wellbore_name": "wellbore",
    "npd_wellbore_code": "wellbore_code",
    "field_name": "field",
}
_ATTR_KEY = re.compile(
    r"(^|[._])(model|model_number|part_number|part_no|serial|serial_number|catalog_number|"
    r"item_number|uid|uwi|name|label|id)$"
)
_COUNTRY = re.compile(r"^(no|nor|norway)\s+")
_BLOCK = re.compile(r"^(\d{1,2}/\d{1,2})-(.+)$")
MAX_IDENTIFIER_CHARS = 80
MAX_IDENTIFIERS_PER_CHUNK = 200


@dataclass(frozen=True)
class IdentifierRow:
    identifier: str  # normalized lookup form (label or alias)
    canonical: str  # normalized full label; aliases point at it
    id_kind: str


def aliases(label: str) -> list[str]:
    """Normalized label plus its block-stripped / country-stripped forms (never a parent)."""
    full = norm_identifier(label)
    out = [full]
    stripped = _COUNTRY.sub("", full)
    if stripped != full:
        out.append(stripped)
    block = _BLOCK.match(stripped)
    if block:
        out.append(block.group(2))
    return list(dict.fromkeys(out))


def unqualified(canonical: str) -> str | None:
    """``15/9-f-12`` -> ``f-12`` (None when the label carries no block prefix)."""
    match = _BLOCK.match(_COUNTRY.sub("", canonical))
    return match.group(2) if match else None


def _rows(label: str, kind: str) -> list[IdentifierRow]:
    full = norm_identifier(label)
    if not full or len(full) > MAX_IDENTIFIER_CHARS:
        return []
    canonical = _COUNTRY.sub("", full)  # "NO 15/9-F-12" and "15/9-F-12" are one naming
    return [IdentifierRow(a, canonical, kind) for a in aliases(label)]


def record_identifiers(
    subject: dict[str, Any], attributes: list[dict[str, Any]]
) -> list[IdentifierRow]:
    rows: list[IdentifierRow] = []
    for key, kind in _SUBJECT_KINDS.items():
        value = subject.get(key)
        if isinstance(value, str) and value.strip():
            rows.extend(_rows(value, kind))
    for attr in attributes:
        key = attr.get("key", "")
        value = attr.get("text") if attr.get("text") is not None else attr.get("original_text")
        if _ATTR_KEY.search(key) and isinstance(value, str) and value.strip():
            rows.extend(_rows(value, "attribute"))
    return rows


def unique_rows(rows: list[IdentifierRow]) -> list[IdentifierRow]:
    seen: dict[tuple[str, str], IdentifierRow] = {}
    for row in rows:
        seen.setdefault((row.identifier, row.id_kind), row)
    return list(seen.values())[:MAX_IDENTIFIERS_PER_CHUNK]


# --- query side ---------------------------------------------------------------------------

_TOKEN = re.compile(r"[^\s,;:()\[\]\"'`?!]+")
_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_ID_SHAPED = re.compile(r"^(?=.*\d)[a-z0-9][a-z0-9/_.\-]*[a-z0-9]$")
MAX_NGRAM = 4
MAX_CANDIDATES = 120
_STOP_IDS = frozenset({"a", "an", "the"})


@dataclass(frozen=True)
class Candidate:
    text: str
    start: int
    end: int  # exclusive token index


def query_tokens(query: str) -> list[str]:
    out = []
    for raw in _TOKEN.findall(query):
        token = raw.strip(".")
        if token:
            out.append(token)
    return out


def query_candidates(query: str) -> list[Candidate]:
    """Contiguous 1..4-token n-grams, normalized, longest first (bounded)."""
    tokens = query_tokens(query)
    found: dict[str, Candidate] = {}
    for n in range(min(MAX_NGRAM, len(tokens)), 0, -1):
        for start in range(len(tokens) - n + 1):
            text = norm_identifier(" ".join(tokens[start : start + n]))
            if text and text not in _STOP_IDS and text not in found:
                found[text] = Candidate(text, start, start + n)
            if len(found) >= MAX_CANDIDATES:
                return list(found.values())
    return list(found.values())


def query_uuids(query: str) -> list[str]:
    return list(dict.fromkeys(m.lower() for m in _UUID.findall(query)))[:5]


def id_shaped_tokens(query: str) -> list[str]:
    """Tokens that look like an identifier (digit-bearing, hyphen/slash/dot allowed)."""
    return list(
        dict.fromkeys(
            t for t in (norm_identifier(x) for x in query_tokens(query)) if _ID_SHAPED.match(t)
        )
    )[:20]

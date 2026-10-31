"""Deterministic evidence chunking of extracted source observations (pure; no I/O).

Rules (RETRIEVAL_ASSISTANT.md section 4):

* <= 480 estimated tokens per chunk (hard cap, well inside the spec's 800); the working target
  is 400 so a chunk also fits the 512-token window of the embedder instead of being silently
  truncated by it.
* Consecutive records of one kind and one subject (bore) form a *table*. Every chunk of that table repeats the table
  header (kind, subject values and a ``units`` line); every row restates each
  attribute as ``key=value unit``, so a number is never separated from its attribute or unit.
* Table chunks split only at row boundaries. A single oversized row splits at attribute
  boundaries, and only a single oversized text attribute splits at word boundaries, with a
  <= 50-token overlap and never between a number and the token that follows it.
* ``vector_policy``: numeric-dominated chunks (explicit kinds, or records whose attributes are
  almost all plain numbers) are excluded from embedding BY POLICY; they stay exact-identifier and
  full-text searchable. This is a deterministic function of the records, see ``vector_policy_of``.
* The original ``extracted_record`` stays the evidence authority: a chunk only carries record
  ids and locators, plus the extraction quality those records had.

Bump ``CHUNKER_VERSION`` whenever output could change; a new version builds a new index."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from .identifiers import IdentifierRow, record_identifiers, unique_rows
from .text import estimate_tokens, search_text

CHUNKER_VERSION = "chunker-2"
TARGET_TOKENS = 400
MAX_TOKENS = 480
OVERLAP_TOKENS = 50
MAX_COLUMNS = 40
MAX_LOCATORS_PER_CHUNK = 200
EMBED = "embed"
NUMERIC_TABLE = "numeric_table"
# Kinds that are numeric time series / station tables whatever their attribute mix.
NUMERIC_TABLE_KINDS = frozenset({"production_day", "production_month", "trajectory_station"})
NUMERIC_ATTR_RATIO = 0.8  # share of attributes that are plain numbers (or unknown numbers)
NUMERIC_MIN_RECORDS = 8  # a numeric TABLE has many rows; a few-record chunk keeps its vector
MAX_PROSE_CHARS = 24  # any longer text attribute makes the chunk prose, not a numeric table
_NUMERIC_WORD = re.compile(r"^[+-]?[\d.,]+(?:[eE][+-]?\d+)?%?$")


@dataclass(frozen=True)
class RecordIn:
    """One ``extracted_record`` row (JSON columns as stored)."""

    ordinal: int
    record_id: UUID
    kind: str
    subject: dict[str, Any]
    locator: dict[str, Any]
    effective_time: dict[str, Any] | None
    validation_state: str
    attributes: list[dict[str, Any]]


@dataclass
class ChunkDraft:
    ordinal: int
    kind: str
    text: str
    token_count: int
    record_ids: list[UUID]
    first_record_ordinal: int
    last_record_ordinal: int
    locators: list[dict[str, Any]]
    temporal_coverage: dict[str, Any] | None
    validation_states: dict[str, int]
    identifiers: list[IdentifierRow]
    vector_policy: str = EMBED
    fingerprint: str = ""
    search_text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


MAX_REFERENCE_CHARS = 24


def short_key(key: str, kind: str) -> str:
    """Attribute keys repeat the record kind (``production_day.date``); the chunk header already
    states the kind, so the cell uses the attribute name only."""
    prefix = kind + "."
    return key[len(prefix) :] if key.startswith(prefix) and len(key) > len(prefix) else key


def _cell(attr: dict[str, Any], kind: str = "") -> str:
    key = short_key(attr["key"], kind)
    original = attr.get("original_text")
    text = attr.get("text")
    number = attr.get("number")
    source = ""
    if number is None and text is not None and str(text).strip():
        value = str(text).strip()  # readable form (e.g. an ISO date), source text kept below
        if original is not None and str(original).strip() not in ("", value):
            source = f" (source {str(original).strip()[:24]})"
    elif original is not None and str(original).strip():
        value = str(original).strip()
    elif number is not None:
        value = repr(number)
    else:
        reason = attr.get("unknown_reason") or "no value in source"
        return f"{key}=unknown ({reason})"
    unit = attr.get("unit")
    if unit and unit.strip() and unit.strip() not in value.split():
        value = f"{value} {unit.strip()}"
    ref = attr.get("reference")
    cell = f"{key}={value}{source}"
    if ref and len(ref) <= MAX_REFERENCE_CHARS:
        cell += f" ref {ref}"
    state = attr.get("validation_state")
    if state and state != "unreviewed":
        cell += f" ({state})"
    return cell


def _split_words(text: str, budget: int) -> list[str]:
    """Word-boundary split with overlap; never leaves a number as the last word of a part."""
    words = text.split()
    parts: list[str] = []
    start = 0
    while start < len(words):
        end = start
        used = 0
        while end < len(words):
            cost = estimate_tokens(words[end])
            if used + cost > budget and end > start:
                break
            used += cost
            end += 1
        # do not end a part between a number and its unit/next word
        while end < len(words) and end - start > 1 and _NUMERIC_WORD.match(words[end - 1]):
            end -= 1
        parts.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        back, kept = end, 0
        while back > start + 1 and kept + estimate_tokens(words[back - 1]) <= OVERLAP_TOKENS:
            back -= 1
            kept += estimate_tokens(words[back])
        start = max(back, start + 1)
    return parts


def _subject_header(subject: dict[str, Any]) -> str:
    """Subject fields once, skipping a field whose value an earlier field already shows
    (``wellbore_name`` and ``wellbore_label`` often repeat each other)."""
    shown: set[str] = set()
    parts: list[str] = []
    for key, value in subject.items():
        if value is None or str(value).strip() == "":
            continue
        text = str(value)[:80]
        if text in shown:
            continue
        shown.add(text)
        parts.append(f"{key}={text}")
    return "; ".join(parts)


def _row_text(rec: RecordIn, cells: list[str]) -> str:
    when = rec.effective_time
    time = [f"time={when['literal']}"] if when and when.get("literal") else []
    return f"#{rec.ordinal} " + " | ".join([*time, *cells])


def _columns(rows: list[tuple[RecordIn, list[dict[str, Any]]]]) -> str:
    """Table header: the columns that carry a unit. Every row also restates ``key=value unit``,
    so key names are not repeated here (they would double the header of wide tables)."""
    units: dict[str, str] = {}
    for rec, attrs in rows:
        for attr in attrs:
            key = short_key(attr["key"], rec.kind)
            unit = (attr.get("unit") or "").strip()
            if unit and key not in units:
                units[key] = unit
            if len(units) >= MAX_COLUMNS:
                break
    cols = [f"{k} [{u}]" for k, u in units.items()]
    return "units: " + "; ".join(cols) if cols else ""


def _fingerprint(draft: ChunkDraft, content_sha: str) -> str:
    payload = json.dumps(
        [CHUNKER_VERSION, content_sha, draft.text, [str(r) for r in draft.record_ids]],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _distinct_locators(records: list[RecordIn]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rec in records:
        key = json.dumps(rec.locator, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append(rec.locator)
        if len(out) >= MAX_LOCATORS_PER_CHUNK:
            break
    return out


def _temporal(records: list[RecordIn]) -> dict[str, Any] | None:
    times = [r.effective_time for r in records if r.effective_time]
    if not times:
        return None
    return {
        "first_literal": times[0].get("literal"),
        "last_literal": times[-1].get("literal"),
        "precisions": sorted({t.get("precision", "unknown") for t in times}),
    }


def vector_policy_of(kind: str, records: list[RecordIn]) -> str:
    """``numeric_table`` when the chunk is numeric-dominated, else ``embed``.

    Deterministic rule (owner decision, October 31): the kind is one of ``NUMERIC_TABLE_KINDS``,
    or the chunk holds at least ``NUMERIC_MIN_RECORDS`` (8) records, at least 80% of whose attributes
    are plain numbers (a number, or an unknown numeric value with no text), and no attribute
    carries more than ``MAX_PROSE_CHARS`` of prose. Such chunks carry little semantic content
    for a text embedder and dominate the corpus (the production workbook is 97% of the approved
    subset), so they are skipped by policy; exact identifiers and full text still reach them."""
    if kind in NUMERIC_TABLE_KINDS:
        return NUMERIC_TABLE
    attrs = [a for r in records for a in r.attributes]
    if len(records) < NUMERIC_MIN_RECORDS or not attrs:
        return EMBED
    for a in attrs:
        text = a.get("text")
        if (
            a.get("number") is None
            and isinstance(text, str)
            and len(text.strip()) > MAX_PROSE_CHARS
        ):
            return EMBED
    numeric = sum(1 for a in attrs if a.get("number") is not None)
    return NUMERIC_TABLE if numeric / len(attrs) >= NUMERIC_ATTR_RATIO else EMBED


def _make(
    ordinal: int,
    kind: str,
    header: str,
    body: list[str],
    records: list[RecordIn],
    content_sha: str,
    doc_identifiers: Sequence[IdentifierRow] = (),
) -> ChunkDraft:
    text = "\n".join([header, *body])
    ids = unique_rows(
        [
            *doc_identifiers,
            *[i for r in records for i in record_identifiers(r.subject, r.attributes)],
        ]
    )
    draft = ChunkDraft(
        ordinal=ordinal,
        kind=kind,
        text=text,
        token_count=estimate_tokens(text),
        record_ids=[r.record_id for r in records],
        first_record_ordinal=records[0].ordinal,
        last_record_ordinal=records[-1].ordinal,
        locators=_distinct_locators(records),
        temporal_coverage=_temporal(records),
        validation_states=dict(Counter(r.validation_state for r in records)),
        identifiers=ids,
        vector_policy=vector_policy_of(kind, records),
    )
    draft.search_text = search_text(text)
    draft.fingerprint = _fingerprint(draft, content_sha)
    return draft


def _groups(records: Iterable[RecordIn]) -> Iterator[list[RecordIn]]:
    """Runs of consecutive records with the same kind AND subject (one table of one bore).
    Interleaved data degrades to smaller tables, never to a mixed-subject chunk."""
    group: list[RecordIn] = []
    key: tuple[str, str] | None = None
    for rec in records:
        rec_key = (rec.kind, json.dumps(rec.subject, sort_keys=True))
        if group and (rec_key != key or len(group) >= 5000):
            yield group
            group = []
        key = rec_key
        group.append(rec)
    if group:
        yield group


def _flush(
    ordinal: int,
    kind: str,
    header: str,
    plain_header: str,
    batch: list[tuple[RecordIn, list[dict[str, Any]], str]],
    content_sha: str,
    doc_identifiers: Sequence[IdentifierRow] = (),
) -> ChunkDraft:
    rows = [t for _, _, t in batch]
    members = [r for r, _, _ in batch]
    draft = _make(ordinal, kind, header, rows, members, content_sha, doc_identifiers)
    if draft.token_count > MAX_TOKENS:  # header too wide: keep the rows, drop the column line
        draft = _make(ordinal, kind, plain_header, rows, members, content_sha, doc_identifiers)
    return draft


def chunk_records(
    records: Iterable[RecordIn],
    content_sha: str,
    doc_identifiers: Sequence[IdentifierRow] = (),
) -> Iterator[ChunkDraft]:
    """Chunk records in ordinal order. Deterministic: same input -> identical chunks.
    ``doc_identifiers`` are the document-level well identity rows (``document_well_rows``),
    added to every chunk of a single-well document."""
    ordinal = 0
    for group in _groups(records):
        kind = group[0].kind
        subject = _subject_header(group[0].subject)
        plain_header = f"[{kind}] {subject}".rstrip()
        cols = _columns([(r, r.attributes) for r in group[:200]])
        header = f"{plain_header}\n{cols}" if cols else plain_header
        if estimate_tokens(header) > TARGET_TOKENS // 2:
            header = plain_header  # rows restate key=value unit; do not let the header eat the body
        budget = max(TARGET_TOKENS - estimate_tokens(header), 80)
        batch: list[tuple[RecordIn, list[dict[str, Any]], str]] = []
        used = 0
        for rec in group:
            cells = [_cell(a, kind) for a in rec.attributes]
            for part_attrs, text in _row_parts(rec, cells, rec.attributes, budget):
                cost = estimate_tokens(text) + 1
                if batch and used + cost > budget:
                    yield _flush(
                        ordinal, kind, header, plain_header, batch, content_sha, doc_identifiers
                    )
                    ordinal += 1
                    batch, used = [], 0
                batch.append((rec, part_attrs, text))
                used += cost
        if batch:
            yield _flush(ordinal, kind, header, plain_header, batch, content_sha, doc_identifiers)
            ordinal += 1


def _row_parts(
    rec: RecordIn,
    cells: list[str],
    attrs: list[dict[str, Any]],
    budget: int,
) -> Iterator[tuple[list[dict[str, Any]], str]]:
    """The row as one line, or - when the row alone exceeds the budget - attribute-boundary
    parts (``part i/n``), splitting a single oversized cell only at word boundaries."""
    whole = _row_text(rec, cells)
    if estimate_tokens(whole) <= budget:
        yield attrs, whole
        return
    pieces: list[tuple[dict[str, Any], str]] = []
    for attr, cell in zip(attrs, cells, strict=True):
        if estimate_tokens(cell) <= budget - 20:
            pieces.append((attr, cell))
        else:
            head, _, value = cell.partition("=")
            for part in _split_words(value, budget - 30):
                pieces.append((attr, f"{head}={part}"))
    groups: list[list[tuple[dict[str, Any], str]]] = [[]]
    used = 0
    for piece in pieces:
        cost = estimate_tokens(piece[1]) + 1
        if groups[-1] and used + cost > budget - 20:
            groups.append([])
            used = 0
        groups[-1].append(piece)
        used += cost
    total = len(groups)
    for i, grp in enumerate(groups, start=1):
        text = _row_text(rec, [c for _, c in grp]) + f" (part {i}/{total})"
        yield [a for a, _ in grp], text

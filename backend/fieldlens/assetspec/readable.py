"""Readable evidence for asset specs, composed at read time (EXPLORE_POLISH B-2).

Stored specs keep ``EvidenceRef`` as written (document id, page, quote). When a spec is read, each
reference is enriched with the document's filename, a human locator ("page 3, table 2, row 5") and,
for structured components, a short statement built from the stored ``extracted_record`` the quote
names. Two batched queries serve every component of every spec returned (documents, records): no
per-component queries, no document file I/O, no S5 rerun, and existing stored specs improve as is.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldlens.persistence import models as m

_RECORD_QUOTE = re.compile(r"^extracted_record ([0-9a-fA-F-]{36})\b")
_LOCATOR_KEYS = (
    ("page", "page"),
    ("sheet", "sheet"),
    ("table_id", "table"),
    ("row", "row"),
    ("column", "column"),
    ("cell_id", "cell"),
    ("line", "line"),
)
_KIND_LABEL = {
    "casing_point": "Casing",
    "tubular_assembly": "Tubular assembly",
    "tubular_component": "Tubular",
    "wb_geometry": "Wellbore geometry",
    "wb_geometry_section": "Hole/casing section",
    "bha_run": "BHA run",
    "perforation_interval": "Perforation interval",
}
_BAD = frozenset({"conflicting", "invalid", "unsupported"})
READABLE_EVIDENCE_FIELDS = ("filename", "locator", "statement")
MAX_STATEMENT = 300
MAX_LOCATOR = 200


def _short_key(key: str) -> str:
    return key.split(".", 1)[-1].replace("_", " ")


def human_locator(locator: dict[str, Any] | None, page: int | None = None) -> str | None:
    """'page 3, table 2, row 5' / 'line 14' / an XML path; never JSON, never a UUID."""
    loc = locator or {}
    parts: list[str] = []
    for key, label in _LOCATOR_KEYS:
        value = loc.get(key)
        if key == "page" and value in (None, ""):
            value = page
        if value in (None, "") or isinstance(value, bool | dict | list):
            continue
        parts.append(f"{label} {str(value)[:60]}")
    path = loc.get("element_path")
    if isinstance(path, str) and path:
        parts.append(path[-100:])
    return (", ".join(parts))[:MAX_LOCATOR] or None


def _printed(attr: dict[str, Any]) -> str:
    original = attr.get("original_text") or attr.get("text")
    if original in (None, ""):
        return ""
    unit = attr.get("unit") or ""
    text = " ".join(str(original).split())[:60]
    return f"{text} {unit}".strip() if unit and unit not in text else text


def _find(attrs: list[dict[str, Any]], suffix: str) -> dict[str, Any] | None:
    for a in attrs:
        key = str(a.get("key") or "")
        if (key == suffix or key.endswith("." + suffix)) and a.get("validation_state") not in _BAD:
            return a
    return None


def _val(attrs: list[dict[str, Any]], suffix: str) -> str:
    a = _find(attrs, suffix)
    return _printed(a) if a else ""


def compose_statement(kind: str, attrs: list[dict[str, Any]]) -> str | None:
    """A short statement from the record's own printed values; None when nothing is printed."""
    label = _KIND_LABEL.get(kind, kind.replace("_", " ").capitalize())
    if kind == "casing_point":
        diameter, md, name = (
            _val(attrs, "casing_diameter"),
            _val(attrs, "md"),
            _val(attrs, "name"),
        )
        head = f"Casing {diameter}" if diameter else (f"Casing point {name}" if name else label)
        text = f"{head} at {md} MD" if md else head
        if name and diameter and name not in text:
            text += f" ({name})"
        return text[:MAX_STATEMENT] if (diameter or md or name) else None
    parts: list[str] = []
    for a in attrs:
        if a.get("validation_state") in _BAD:
            continue
        value = _printed(a)
        if not value:
            continue
        key = _short_key(str(a.get("key") or ""))
        is_text = isinstance(a.get("text"), str) and a.get("number") is None
        parts.append(value if is_text and len(parts) == 0 else f"{key} {value}")
        if len(parts) == 4:
            break
    if not parts:
        return None
    return f"{label}: {'; '.join(parts)}"[:MAX_STATEMENT]


def _refs(specs: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        for component in spec.get("components") or []:
            if isinstance(component, dict):
                out.extend(e for e in component.get("evidence") or [] if isinstance(e, dict))
    return out


def _uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def enrich_specs(
    session: Session, project_id: UUID, specs: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Return deep copies of the spec dicts with readable evidence fields filled in.

    At most two queries regardless of component or spec count."""
    copies = [copy.deepcopy(s) for s in specs]
    refs = _refs(copies)
    if not refs:
        return copies
    doc_ids = {d for e in refs if (d := _uuid(e.get("document_id"))) is not None}
    record_ids: dict[int, UUID] = {}
    for i, e in enumerate(refs):
        match = _RECORD_QUOTE.match(str(e.get("quote") or ""))
        if match and (rid := _uuid(match.group(1))) is not None:
            record_ids[i] = rid
    names: dict[UUID, str] = {}
    if doc_ids:
        names = {
            r.document_id: r.original_filename
            for r in session.execute(
                select(
                    m.source_document.c.document_id, m.source_document.c.original_filename
                ).where(
                    m.source_document.c.project_id == project_id,
                    m.source_document.c.document_id.in_(doc_ids),
                )
            )
        }
    records: dict[UUID, Any] = {}
    if record_ids:
        er = m.extracted_record
        records = {
            r.record_id: r
            for r in session.execute(
                select(er.c.record_id, er.c.kind, er.c.locator, er.c.attributes).where(
                    er.c.project_id == project_id, er.c.record_id.in_(set(record_ids.values()))
                )
            )
        }
    for i, e in enumerate(refs):
        doc = _uuid(e.get("document_id"))
        if doc is not None and doc in names:
            e["filename"] = names[doc]
        page = e.get("page") if isinstance(e.get("page"), int) else None
        record = records.get(record_ids[i]) if i in record_ids else None
        locator = (
            record.locator if record is not None and isinstance(record.locator, dict) else None
        )
        text = human_locator(locator, page)
        if text:
            e["locator"] = text
        if record is not None:
            attrs = [a for a in (record.attributes or []) if isinstance(a, dict)]
            statement = compose_statement(record.kind, attrs)
            if statement:
                e["statement"] = statement
    return copies

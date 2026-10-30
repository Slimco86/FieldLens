"""Small pure helpers: numbers, units, event-time precision and locator builders."""

from __future__ import annotations

import math
import re
from typing import Any

from .types import Attr, EventTime, Locator

_SNAKE_1 = re.compile(r"(.)([A-Z][a-z]+)")
_SNAKE_2 = re.compile(r"([a-z0-9])([A-Z])")
_THOUSANDS = re.compile(r"^[+-]?\d{1,3}(?:,\d{3})+(?:\.\d*)?$")
_NUMBER = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$")

# Exact, lossless conversions only. Anything else is left un-normalized (original kept).
_NORMALIZATION: dict[str, tuple[str, float]] = {
    "m": ("m", 1.0),
    "ft": ("m", 0.3048),
    "in": ("m", 0.0254),
    "mm": ("m", 0.001),
    "dega": ("deg", 1.0),
    "deg": ("deg", 1.0),
    "°": ("deg", 1.0),
}


def snake(name: str) -> str:
    return _SNAKE_2.sub(r"\1_\2", _SNAKE_1.sub(r"\1_\2", name)).lower()


def parse_number(text: str | None) -> float | None:
    """Strict plain number. A comma is accepted only as an unambiguous thousands separator
    (``1,234`` / ``1,234,567.5``); ``1,5`` is a possible decimal comma and stays unknown.
    Never NaN/inf, never empty -> 0."""
    if text is None:
        return None
    cleaned = text.strip()
    if "," in cleaned:
        if not _THOUSANDS.match(cleaned):
            return None
        cleaned = cleaned.replace(",", "")
    if not _NUMBER.match(cleaned):
        return None
    value = float(cleaned)
    return value if math.isfinite(value) else None


def normalize(value: float, unit: str | None) -> tuple[float, str] | None:
    if unit is None:
        return None
    entry = _NORMALIZATION.get(unit.strip().lower() if unit != "°" else unit)
    if entry is None:
        return None
    return value * entry[1], entry[0]


def quantity_attr(
    key: str,
    locator: Locator,
    text: str | None,
    unit: str | None,
    *,
    reference: str | None = None,
    unit_required: bool = True,
) -> Attr:
    """Numeric attribute with original text/unit; non-numeric or empty text stays unknown."""
    original = text
    number = parse_number(text)
    if number is None:
        stripped = (text or "").strip()
        if not stripped:
            reason = "empty in source"
        elif "," in stripped and re.fullmatch(r"[+-]?[\d,.]+", stripped):
            reason = "ambiguous comma (decimal or thousands separator)"
        else:
            reason = "not a plain number"
        return Attr(
            key,
            locator,
            original_text=original,
            unit=unit,
            unit_status="stated" if unit else "missing" if unit_required else "not_applicable",
            reference=reference,
            unknown_reason=reason,
        )
    attr = Attr(
        key,
        locator,
        original_text=original,
        number=number,
        unit=unit,
        unit_status="stated" if unit else "missing" if unit_required else "not_applicable",
        reference=reference,
    )
    if unit:
        norm = normalize(number, unit)
        if norm is not None:
            attr.normalized_number, attr.normalized_unit = norm
    else:
        attr.validation_state = "unsupported" if unit_required else "unreviewed"
    return attr


def text_attr(key: str, locator: Locator, text: str | None) -> Attr:
    if text is None or not text.strip():
        return Attr(key, locator, original_text=text, unknown_reason="empty in source")
    return Attr(key, locator, original_text=text, text=text.strip())


_ISO_FULL = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})?$")
_ISO_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ISO_MONTH = re.compile(r"^\d{4}-\d{2}$")
_ISO_YEAR = re.compile(r"^\d{4}$")


def event_time(literal: str | None, field_name: str | None = None) -> EventTime | None:
    """Classify precision from the literal only; a date is never promoted to an instant."""
    if literal is None or not literal.strip():
        return None
    text = literal.strip()
    if _ISO_FULL.match(text):
        if text.endswith("Z"):
            return EventTime(text, "instant", True, field_name, "UTC")
        off = re.search(r"([+-])(\d{2}):?(\d{2})$", text)
        if off:
            zone = f"UTC{off.group(1)}{off.group(2)}:{off.group(3)}"
            return EventTime(text, "instant", True, field_name, zone)
        return EventTime(text, "instant", False, field_name)
    if _ISO_DAY.match(text):
        return EventTime(text, "day", False, field_name)
    if _ISO_MONTH.match(text):
        return EventTime(text, "month", False, field_name)
    if _ISO_YEAR.match(text):
        return EventTime(text, "year", False, field_name)
    return EventTime(text, "unknown", False, field_name)


def well_key(label: str | None) -> str | None:
    """Stable well key from a source label: ``NO 15/9-F-12 pilot`` -> ``15/9-F-12``.

    The original label stays on the record; this key is only for coverage grouping and never
    merges a pilot/sidetrack into its parent identity (``wellbore_label`` keeps the suffix)."""
    if not label:
        return None
    m = re.search(r"(\d{1,2}/\d{1,2})-([A-Z])-?(\d{1,3})(?!\d)", label.upper())
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def wellbore_suffix(label: str | None) -> str | None:
    if not label:
        return None
    m = re.search(r"\d{1,2}/\d{1,2}-[A-Za-z]-\d{1,3}\s*(.*)$", label)
    suffix = m.group(1).strip() if m else ""
    return suffix or None


def jsonable(value: Any) -> Any:
    return value

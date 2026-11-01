"""Small deterministic unit table and attribute dimensions for the validators.

Only what the generic proof class needs; TASK-041 extends the attribute table. An unknown unit
never converts: it is rejected, not guessed. Depths without a unit default to meters (a warning,
owner decision October 31)."""

from __future__ import annotations

import re
from dataclasses import dataclass

# unit spelling (lower case, no spaces) -> (dimension, factor to the dimension's base unit)
_UNITS: dict[str, tuple[str, float]] = {}


def _add(dimension: str, factor: float, *names: str) -> None:
    for name in names:
        _UNITS[name] = (dimension, factor)


_add("length", 1.0, "m", "meter", "meters", "metre", "metres")
_add("length", 0.3048, "ft", "feet", "foot")
_add("length", 0.0254, "in", "inch", "inches", '"')
_add("length", 0.001, "mm")
_add("length", 0.01, "cm")
_add("length", 1000.0, "km")
_add("pressure", 1.0, "pa")
_add("pressure", 1000.0, "kpa")
_add("pressure", 1_000_000.0, "mpa")
_add("pressure", 100_000.0, "bar")
_add("pressure", 6894.757293168, "psi")
_add("temperature", 1.0, "degc", "°c", "c")
_add("angle", 1.0, "deg", "°", "degree", "degrees")

BASE_UNIT = {"length": "m", "pressure": "Pa", "temperature": "degC", "angle": "deg"}


@dataclass(frozen=True)
class Parsed:
    dimension: str
    factor: float


def parse_unit(text: str | None) -> Parsed | None:
    if text is None:
        return None
    entry = _UNITS.get(re.sub(r"\s+", "", text).lower())
    return Parsed(*entry) if entry else None


_NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?|[-+]?\.\d+")


def parse_number(text: str) -> float | None:
    """First plain number in the text as written (no thousands separators are guessed)."""
    match = _NUMBER.search(text.replace(",", "") if re.search(r"\d,\d{3}\b", text) else text)
    return float(match.group(0)) if match else None


@dataclass(frozen=True)
class AttributeSpec:
    dimension: str
    low: float  # plausible range in base units
    high: float
    reference: str | None = None  # MD | TVD | TVDSS when the suffix names it


_DEPTH_RANGE = (0.0, 15_000.0)
_SIZE_RANGE = (0.001, 3.0)
_SPECS: dict[str, AttributeSpec] = {
    "md": AttributeSpec("length", *_DEPTH_RANGE, "MD"),
    "top_md": AttributeSpec("length", *_DEPTH_RANGE, "MD"),
    "base_md": AttributeSpec("length", *_DEPTH_RANGE, "MD"),
    "tvd": AttributeSpec("length", *_DEPTH_RANGE, "TVD"),
    "top_tvd": AttributeSpec("length", *_DEPTH_RANGE, "TVD"),
    "base_tvd": AttributeSpec("length", *_DEPTH_RANGE, "TVD"),
    "tvdss": AttributeSpec("length", -500.0, 15_000.0, "TVDSS"),
    "depth": AttributeSpec("length", *_DEPTH_RANGE),
    "length": AttributeSpec("length", 0.0, 15_000.0),
    "od": AttributeSpec("length", *_SIZE_RANGE),
    "id": AttributeSpec("length", *_SIZE_RANGE),
    "diameter": AttributeSpec("length", *_SIZE_RANGE),
    "easting": AttributeSpec("length", -1.0e7, 1.0e8),
    "northing": AttributeSpec("length", -1.0e7, 1.0e8),
    "pressure": AttributeSpec("pressure", 0.0, 2.0e9),
    "temperature": AttributeSpec("temperature", -60.0, 450.0),
    "inclination": AttributeSpec("angle", 0.0, 180.0),
    "azimuth": AttributeSpec("angle", 0.0, 360.0),
}
COORDINATE_SUFFIXES = frozenset({"easting", "northing", "x", "y", "latitude", "longitude"})


def attribute_spec(key: str) -> AttributeSpec | None:
    return _SPECS.get(key.rsplit(".", 1)[-1])


def is_coordinate(key: str) -> bool:
    return key.rsplit(".", 1)[-1] in COORDINATE_SUFFIXES or key.startswith("coordinate.")

"""Line-level patterns shared by the Compass "Standard Survey Report" profiles (PDF and text).

Pure helpers (no I/O): the number/row regexes, the ten standard station columns, the elevation
pattern, header-value extraction and the well-key derivation. Both profiles import these so the
two renderings of the same report are parsed by the same rules."""

from __future__ import annotations

import re

NUM = r"-?\d[\d,]*\.\d+|-?\.\d+"
SURVEY_ROW = re.compile(rf"^\s*((?:{NUM})(?:\s+(?:{NUM})){{9}})\s*$")
PROGRAM_ROW = re.compile(rf"^\s*({NUM})\s+({NUM})\s{{2,}}(.+?)\s{{2,}}(.+?)\s{{2,}}(.+?)\s*$")
CASING_ROW = re.compile(
    rf'^(?P<name>[\d /]+")\s*(?P<md>{NUM})\s+(?P<tvd>{NUM})\s+(?P<csg>{NUM})\s+(?P<hole>{NUM})$'
)
SURVEY_COLUMNS = (
    ("md", "m"),
    ("incl", "deg"),
    ("azi", "deg"),
    ("tvd", "m"),
    ("dispNs", "m"),
    ("dispEw", "m"),
    ("vertSect", "m"),
    ("dls", "deg/30m"),
    ("build_rate", "deg/30m"),
    ("turn_rate", "deg/30m"),
)
EXPECTED_HEADER_UNITS = "(m)", "(°)", "(°/30m)"
ELEVATION = re.compile(r"@\s*(\d+(?:\.\d+)?)\s*m")


def collapse(line: str) -> str:
    return re.sub(r" {3,}", "   ", line.strip())


def after(pattern: str, text: str, flags: int = 0) -> str | None:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def well_key(wellbore: str | None, text: str) -> str | None:
    """``<quadrant>-<letter>-<number>`` from the Site line and the wellbore name; the wellbore
    (sidetrack) name is never merged into its parent."""
    quad = after(r"Site\s+[^\n]*?,\s*(\d{1,2}/\d{1,2})\s*$", text, re.M)
    m = re.fullmatch(r"([A-Z])-?(\d{1,3})", (wellbore or "").strip().upper())
    return f"{quad}-{m.group(1)}-{m.group(2)}" if quad and m else None

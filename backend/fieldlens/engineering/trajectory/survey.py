"""Survey input types and blocking validation (TR-2).

Nothing here assumes, defaults or zero-fills a missing reference. Any issue blocks the
affected survey geometry: :func:`validate_survey` reports every issue, and the
trajectory computation raises :class:`SurveyBlockedError` instead of producing coordinates.
MD (path length) is never mixed with TVD; original values and units are preserved.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

METERS_PER_FOOT = 0.3048
_MD_UNIT_TO_METERS = {"m": 1.0, "ft": METERS_PER_FOOT}
_MIN_STATIONS = 2


class NorthReference(StrEnum):
    TRUE = "true"
    GRID = "grid"
    MAGNETIC = "magnetic"


class SurveyIssueCode(StrEnum):
    MISSING_CRS = "missing_crs"
    MISSING_VERTICAL_DATUM = "missing_vertical_datum"
    MISSING_DEPTH_REFERENCE = "missing_depth_reference"
    MISSING_NORTH_REFERENCE = "missing_north_reference"
    UNRESOLVED_NORTH_CONVERSION = "unresolved_north_conversion"
    UNSUPPORTED_UNIT = "unsupported_md_unit"
    NONFINITE_START = "nonfinite_start_position"
    TOO_FEW_STATIONS = "too_few_stations"
    NONFINITE_MD = "nonfinite_md"
    NONFINITE_ANGLE = "nonfinite_angle"
    INCLINATION_OUT_OF_RANGE = "inclination_out_of_range"
    MD_DECREASING = "md_decreasing"
    MD_DUPLICATE_CONFLICT = "md_duplicate_conflict"
    DOGLEG_REVERSAL = "dogleg_reversal"


@dataclass(frozen=True, slots=True)
class SurveyIssue:
    code: SurveyIssueCode
    message: str
    station_index: int | None = None


class SurveyBlockedError(Exception):
    """Affected survey geometry is blocked; ``issues`` lists every reason."""

    def __init__(self, issues: tuple[SurveyIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.code.value}: {i.message}" for i in issues))


@dataclass(frozen=True, slots=True)
class SurveyReference:
    """Explicit reference metadata. ``None``/blank means *unknown*, never a default.

    ``grid_convergence_deg``: grid azimuth = true azimuth - convergence (positive when grid
    north is clockwise/east of true north). ``magnetic_declination_deg``: true azimuth =
    magnetic azimuth + declination (east positive). Output coordinates are always in the
    grid of ``crs``, so TRUE needs convergence and MAGNETIC needs both.
    """

    crs: str | None
    vertical_datum: str | None
    depth_reference: str | None
    north_reference: NorthReference | None
    grid_convergence_deg: float | None = None
    magnetic_declination_deg: float | None = None


@dataclass(frozen=True, slots=True)
class SurveyStation:
    """Original as-supplied values: MD in ``Survey.md_unit``, angles in degrees."""

    md: float
    inclination_deg: float
    azimuth_deg: float


@dataclass(frozen=True, slots=True)
class Survey:
    """Survey stations plus reference metadata and the physical start position.

    ``start_east_m``/``start_north_m``/``start_z_m`` are metres in the CRS grid, with z up
    relative to ``reference.vertical_datum`` (so positive TVD down is ``-z``).
    """

    stations: tuple[SurveyStation, ...]
    reference: SurveyReference
    md_unit: str = "m"
    start_east_m: float = math.nan
    start_north_m: float = math.nan
    start_z_m: float = math.nan


def _blank(value: str | None) -> bool:
    return value is None or not value.strip()


def _finite(value: float | None) -> bool:
    return value is not None and math.isfinite(value)


def validate_survey(survey: Survey) -> tuple[SurveyIssue, ...]:
    """Return every blocking issue (empty tuple means geometry may be computed)."""
    issues: list[SurveyIssue] = []
    ref = survey.reference

    def add(code: SurveyIssueCode, msg: str, idx: int | None = None) -> None:
        issues.append(SurveyIssue(code, msg, idx))

    if _blank(ref.crs):
        add(SurveyIssueCode.MISSING_CRS, "horizontal CRS is not stated")
    if _blank(ref.vertical_datum):
        add(SurveyIssueCode.MISSING_VERTICAL_DATUM, "vertical datum is not stated")
    if _blank(ref.depth_reference):
        add(SurveyIssueCode.MISSING_DEPTH_REFERENCE, "depth reference is not stated")
    if ref.north_reference is None:
        add(SurveyIssueCode.MISSING_NORTH_REFERENCE, "north reference is not stated")
    elif ref.north_reference is NorthReference.TRUE and not _finite(ref.grid_convergence_deg):
        add(SurveyIssueCode.UNRESOLVED_NORTH_CONVERSION, "true->grid needs grid convergence")
    elif ref.north_reference is NorthReference.MAGNETIC:
        if not _finite(ref.magnetic_declination_deg):
            add(SurveyIssueCode.UNRESOLVED_NORTH_CONVERSION, "magnetic->true needs declination")
        if not _finite(ref.grid_convergence_deg):
            add(SurveyIssueCode.UNRESOLVED_NORTH_CONVERSION, "true->grid needs grid convergence")
    if survey.md_unit not in _MD_UNIT_TO_METERS:
        add(SurveyIssueCode.UNSUPPORTED_UNIT, f"unsupported MD unit {survey.md_unit!r}")
    if not all(
        math.isfinite(v) for v in (survey.start_east_m, survey.start_north_m, survey.start_z_m)
    ):
        add(SurveyIssueCode.NONFINITE_START, "start position must be explicit and finite")

    st = survey.stations
    if len(st) < _MIN_STATIONS:
        add(SurveyIssueCode.TOO_FEW_STATIONS, "at least two stations are required")
    for i, s in enumerate(st):
        if not math.isfinite(s.md):
            add(SurveyIssueCode.NONFINITE_MD, "MD is not finite", i)
        if not (math.isfinite(s.inclination_deg) and math.isfinite(s.azimuth_deg)):
            add(SurveyIssueCode.NONFINITE_ANGLE, "inclination/azimuth not finite", i)
        elif not 0.0 <= s.inclination_deg <= 180.0:
            add(SurveyIssueCode.INCLINATION_OUT_OF_RANGE, "inclination outside [0, 180]", i)
    for i in range(1, len(st)):
        a, b = st[i - 1], st[i]
        if not (math.isfinite(a.md) and math.isfinite(b.md)):
            continue
        if b.md < a.md:
            add(SurveyIssueCode.MD_DECREASING, "MD decreases", i)
        elif b.md == a.md and (
            b.inclination_deg != a.inclination_deg or b.azimuth_deg != a.azimuth_deg
        ):
            add(SurveyIssueCode.MD_DUPLICATE_CONFLICT, "duplicate MD with differing angles", i)
    return tuple(issues)


def md_to_meters(survey: Survey) -> float:
    return _MD_UNIT_TO_METERS[survey.md_unit]

"""Record kind -> exposure category, finding classification and the pure gate rules.

No I/O. The kinds are the ones the native profiles emit today plus ``well_surface_location``
(Statoil survey profile, TASK-051; not in every checkout - an absent kind simply yields no
records, never an error). An unknown kind is ``other``, never dropped."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Final

from fieldlens.contracts.exposure import FindingKind, GateReason, SurveyStatus

GATE_VERSION: Final = "1"

CATEGORIES: Final = (
    "trajectory",
    "surface_location",
    "logs",
    "production",
    "equipment_completion",
    "perforations",
    "other",
)

KIND_CATEGORY: Final[dict[str, str]] = {
    "trajectory": "trajectory",
    "trajectory_station": "trajectory",
    "survey_program_entry": "trajectory",
    "survey_report_header": "trajectory",
    "well_surface_location": "surface_location",
    "las_header": "logs",
    "las_curve": "logs",
    "logical_record": "logs",
    "block_header": "logs",
    "column_header": "logs",
    "index_curve": "logs",
    "production_day": "production",
    "production_month": "production",
    "production_workbook_volve": "production",
    "casing_point": "equipment_completion",
    "tubular_assembly": "equipment_completion",
    "tubular_component": "equipment_completion",
    "bha_run": "equipment_completion",
    "wb_geometry": "equipment_completion",
    "wb_geometry_section": "equipment_completion",
    "perforation_interval": "perforations",
    "perforation": "perforations",
    "formation_pick": "other",
}
# Attribute-key prefixes that differ from the record kind they sit on (issue classification).
_KEY_PREFIX_CATEGORY: Final[dict[str, str]] = {
    **KIND_CATEGORY,
    "pick": "other",
    "equipment": "equipment_completion",
}

CONFLICT_CODES: Final = frozenset(
    {
        "REFERENCE_CONFLICT",
        "INTERVAL_CONFLICT",
        "IDENTITY_MISMATCH",
        "DIMENSION_CONFLICT",
        "TEMPORAL_AMBIGUITY",
    }
)
GAP_CODES: Final = frozenset(
    {
        "MISSING_EQUIPMENT_DIMENSIONS",
        "UNKNOWN_PLACEMENT",
        "HISTORY_INCOMPLETE",
        "EXTRACTION_PARTIAL",
        "MISSING_REFERENCE",
        "MISSING_UNIT",
        "UNKNOWN_CODE",
    }
)
BAD_STATES: Final = frozenset({"invalid", "conflicting", "unsupported"})
BLOCKING_OPERATIONS: Final = frozenset({"physical_geometry", "calculation"})
MIN_STATIONS: Final = 2

# Owner decision (November 1): an explicit ``planned`` (or conflicting) status fails the
# condition; an UNSTATED status (real Statoil exports state none; file names never decide it)
# passes with the per-wellbore warning SURVEY_STATUS_UNSTATED. Planned and as-built stay separate.
GATE_STATUSES: Final[frozenset[str]] = frozenset({"as_built", "unstated", "not_applicable"})


def category_of_kind(kind: str) -> str:
    return KIND_CATEGORY.get(kind, "other")


def category_of_key(attribute_key: str) -> str | None:
    return _KEY_PREFIX_CATEGORY.get(attribute_key.split(".", 1)[0])


def finding_kind(code: str) -> FindingKind:
    if code in CONFLICT_CODES:
        return "conflict"
    if code in GAP_CODES:
        return "gap"
    return "finding"


def normalize_survey_status(header_present: bool, texts: list[str | None]) -> SurveyStatus:
    """``texts``: one entry per survey_status attribute found in the run's header records."""
    if not header_present:
        return "not_applicable"
    explicit: set[str] = set()
    for t in texts:
        v = (t or "").strip().lower()
        if v in ("planned", "plan", "proposed"):
            explicit.add("planned")
        elif v in ("as_built", "as-built", "actual"):
            explicit.add("as_built")
        elif v:
            explicit.add("other:" + v)
    if len(explicit) > 1:
        return "conflicting"
    if explicit == {"planned"}:
        return "planned"
    if explicit == {"as_built"}:
        return "as_built"
    return "unstated"


@dataclass
class Station:
    ordinal: int
    state: str
    md: float | None
    md_state: str | None
    incl: float | None
    incl_state: str | None
    azi: float | None
    azi_state: str | None


@dataclass
class SetVerdict:
    station_count: int
    usable: int
    validated: bool
    reasons: list[GateReason] = field(default_factory=list)


def _usable(s: Station) -> bool:
    if s.state in BAD_STATES:
        return False
    if s.md is None or s.incl is None or s.azi is None:
        return False
    if (s.md_state or "") in BAD_STATES or (s.incl_state or "") in BAD_STATES:
        return False
    if (s.azi_state or "") in BAD_STATES:
        return False
    return 0.0 <= s.incl <= 180.0 and -360.0 <= s.azi <= 360.0 and s.md >= 0.0


def judge_station_set(
    stations: list[Station], status: SurveyStatus, blocking_issue: bool
) -> SetVerdict:
    """Validated = usable status, >=2 stations, every station has finite in-range
    MD/inclination/azimuth with no invalid/conflicting state, MD strictly increasing, and no
    error issue that blocks geometry/calculation on the trajectory."""
    ordered = sorted(stations, key=lambda s: s.ordinal)
    reasons: list[GateReason] = []
    usable = sum(1 for s in ordered if _usable(s))
    if len(ordered) < MIN_STATIONS:
        reasons.append(
            GateReason(
                code="TRAJECTORY_TOO_FEW_STATIONS",
                message=f"{len(ordered)} station(s); at least {MIN_STATIONS} are required.",
            )
        )
    if usable != len(ordered):
        reasons.append(
            GateReason(
                code="TRAJECTORY_INVALID_STATIONS",
                message=f"{len(ordered) - usable} of {len(ordered)} station(s) lack a finite, "
                "in-range MD/inclination/azimuth or are invalid/conflicting.",
            )
        )
    mds = [s.md for s in ordered if s.md is not None]
    if any(b <= a for a, b in zip(mds, mds[1:], strict=False)):
        reasons.append(
            GateReason(
                code="TRAJECTORY_MD_NOT_MONOTONIC",
                message="Measured depth does not strictly increase along the stations.",
            )
        )
    if status == "planned":
        reasons.append(
            GateReason(
                code="TRAJECTORY_PLANNED_ONLY",
                message="The survey is stated as planned; planned and as-built are never mixed.",
            )
        )
    elif status not in GATE_STATUSES:
        reasons.append(
            GateReason(
                code="TRAJECTORY_STATUS_CONFLICTING",
                message="The source states conflicting survey statuses; as-built is required.",
            )
        )
    if blocking_issue:
        reasons.append(
            GateReason(
                code="TRAJECTORY_BLOCKING_ISSUE",
                message="An error finding blocks geometry or calculation for this trajectory.",
            )
        )
    return SetVerdict(len(ordered), usable, not reasons, reasons)


def surface_location_usable(attrs: list[tuple[str, float | None, str | None]]) -> bool:
    """attrs: (key without prefix, numeric value, attribute validation state)."""
    good = {k for k, n, s in attrs if n is not None and (s or "") not in BAD_STATES}
    return {"easting", "northing"} <= good or {"latitude", "longitude"} <= good

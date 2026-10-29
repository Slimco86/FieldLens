"""Typed internal models for the perforation state engine (no persistence, no API DTOs)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

FEET_TO_METRES = Decimal("0.3048")
INSTANT_WIDTH = timedelta(microseconds=1)


class EventKind(StrEnum):
    BASELINE = "baseline"
    PERFORATE = "perforate"
    REPERFORATE = "reperforate"
    OPEN = "open"
    REOPEN = "reopen"
    ISOLATE = "isolate"
    WELLBORE_STATUS = "wellbore_status"
    INTERVAL_FLOW = "interval_flow"
    RETRACT = "retract"
    UNMAPPED = "unmapped"


# Source codes mapped to canonical kinds. Anything else is retained as UNMAPPED and blocks
# dependent state instead of inventing a transition.
CODE_TO_KIND: dict[str, EventKind] = {
    "baseline": EventKind.BASELINE,
    "perforate": EventKind.PERFORATE,
    "reperforate": EventKind.REPERFORATE,
    "open": EventKind.OPEN,
    "reopen": EventKind.REOPEN,
    "isolate": EventKind.ISOLATE,
    "squeeze": EventKind.ISOLATE,
    "plug": EventKind.ISOLATE,
    "shut_off": EventKind.ISOLATE,
    "wellbore_status": EventKind.WELLBORE_STATUS,
    "interval_flow": EventKind.INTERVAL_FLOW,
    "retract": EventKind.RETRACT,
}

DEPTH_KINDS = frozenset(
    {
        EventKind.PERFORATE,
        EventKind.REPERFORATE,
        EventKind.OPEN,
        EventKind.REOPEN,
        EventKind.ISOLATE,
        EventKind.INTERVAL_FLOW,
    }
)


class Precision(StrEnum):
    INSTANT = "instant"
    DAY = "day"


class Access(StrEnum):
    OPEN = "open"
    ISOLATED = "isolated"
    UNKNOWN = "unknown"


class FlowStatus(StrEnum):
    PRODUCING = "producing"
    INJECTING = "injecting"
    SHUT_IN = "shut_in"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TvdRecord:
    """Recorded (source) TVD values, carried verbatim and never used in calculations."""

    from_value: str
    to_value: str
    unit: str
    datum: str | None


@dataclass(frozen=True)
class RecordedDepth:
    """Original recorded MD endpoints plus the exact metre normalisation."""

    from_value: str
    to_value: str
    unit: str
    reference: str
    datum: str
    from_md_m: Decimal
    to_md_m: Decimal
    recorded_tvd: TvdRecord | None = None
    derived_tvd: None = None  # PH-4 (trajectory inversion) is out of scope: never filled.


@dataclass(frozen=True)
class BaselineInterval:
    depth: RecordedDepth
    access: Access


@dataclass(frozen=True)
class EffectiveTime:
    """Effective time window ``[start, end)`` in UTC; instants have a 1 microsecond window."""

    precision: Precision
    start: datetime
    end: datetime
    original: str
    timezone: str | None


@dataclass(frozen=True)
class PerforationEvent:
    event_id: str
    wellbore_id: str
    kind: EventKind
    source_code: str
    effective: EffectiveTime
    dataset_revision: int
    depth: RecordedDepth | None = None
    status: FlowStatus | None = None
    baseline_intervals: tuple[BaselineInterval, ...] = ()
    supersedes: str | None = None
    recorded_at: datetime | None = None
    source_locator: str | None = None


@dataclass(frozen=True)
class EventRejection:
    event_id: str | None
    code: str
    message: str


@dataclass(frozen=True)
class RecordedDepthEvidence:
    event_id: str
    kind: str
    source_code: str
    from_value: str
    to_value: str
    unit: str
    reference: str
    datum: str
    from_md: float  # normalised MD in the result unit
    to_md: float
    recorded_tvd: TvdRecord | None
    derived_tvd: None


@dataclass(frozen=True)
class IntervalState:
    from_md: float
    to_md: float
    perforated: bool | None
    access: str
    flow: str
    unresolved_axes: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]


@dataclass(frozen=True)
class UnresolvedCoverage:
    reason: str
    axis: str
    md_intervals: tuple[tuple[float, float], ...]
    time_from: datetime
    time_to: datetime
    event_ids: tuple[str, ...]


@dataclass(frozen=True)
class PerforationState:
    wellbore_id: str
    as_of: datetime
    dataset_revision: int
    unit: str
    status: str  # resolved | partial | unknown | conflicting
    baseline_established: bool
    total_length: float | None
    total_length_lower_bound: float | None
    total_length_upper_bound: float | None
    open_length: float | None
    open_length_lower_bound: float | None
    open_length_upper_bound: float | None
    wellbore_status: str
    intervals: tuple[IntervalState, ...]
    unresolved: tuple[UnresolvedCoverage, ...]
    limitations: tuple[str, ...]
    evidence_event_ids: tuple[str, ...]
    recorded_depths: tuple[RecordedDepthEvidence, ...]
    correction_event_ids: tuple[str, ...]
    superseded_event_ids: tuple[str, ...]
    unmapped_event_ids: tuple[str, ...]
    rejected_events: tuple[EventRejection, ...] = ()

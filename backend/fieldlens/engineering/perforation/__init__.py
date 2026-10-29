"""Deterministic perforation state and unique-MD-interval union engine (FL-008-A)."""

from .engine import PerforationHistory, derive_event_id
from .models import (
    EventKind,
    EventRejection,
    IntervalState,
    PerforationEvent,
    PerforationState,
    RecordedDepthEvidence,
    UnresolvedCoverage,
)

__all__ = [
    "EventKind",
    "EventRejection",
    "IntervalState",
    "PerforationEvent",
    "PerforationHistory",
    "PerforationState",
    "RecordedDepthEvidence",
    "UnresolvedCoverage",
    "derive_event_id",
]

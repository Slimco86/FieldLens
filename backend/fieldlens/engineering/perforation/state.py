"""Piecewise-constant MD-interval state (exact Decimal metres, no float snapping)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any

from .models import Access, EventKind, FlowStatus, PerforationEvent

_U = Access.UNKNOWN.value
_F = FlowStatus.UNKNOWN.value


@dataclass(frozen=True)
class Segment:
    start: Decimal
    end: Decimal
    perforated: bool = False
    access: str = _U
    flow: str = _F

    def is_default(self) -> bool:
        return not self.perforated and self.access == _U and self.flow == _F

    def attrs(self) -> tuple[bool, str, str]:
        return (self.perforated, self.access, self.flow)


@dataclass(frozen=True)
class CoverageState:
    segments: tuple[Segment, ...] = ()
    baseline: bool = False
    wellbore_status: str | None = None


def _normalise(segments: list[Segment]) -> tuple[Segment, ...]:
    out: list[Segment] = []
    for seg in sorted(segments, key=lambda s: s.start):
        if seg.is_default() or seg.start >= seg.end:
            continue
        if out and out[-1].end == seg.start and out[-1].attrs() == seg.attrs():
            out[-1] = replace(out[-1], end=seg.end)
        else:
            out.append(seg)
    return tuple(out)


def assign(
    segments: tuple[Segment, ...], lo: Decimal, hi: Decimal, **changes: Any
) -> tuple[Segment, ...]:
    out: list[Segment] = []
    cursor = lo
    for seg in segments:
        if seg.end <= lo or seg.start >= hi:
            out.append(seg)
            continue
        if seg.start < lo:
            out.append(replace(seg, end=lo))
        a, b = max(seg.start, lo), min(seg.end, hi)
        if cursor < a:
            out.append(Segment(cursor, a, **changes))
        out.append(replace(seg, start=a, end=b, **changes))
        cursor = b
        if seg.end > hi:
            out.append(replace(seg, start=hi))
    if cursor < hi:
        out.append(Segment(cursor, hi, **changes))
    return _normalise(out)


def apply_event(state: CoverageState, event: PerforationEvent) -> CoverageState:
    kind = event.kind
    if kind is EventKind.BASELINE:
        segs: tuple[Segment, ...] = ()
        for item in event.baseline_intervals:
            segs = assign(
                segs, item.depth.from_md_m, item.depth.to_md_m,
                perforated=True, access=item.access.value,
            )  # fmt: skip
        status = event.status.value if event.status else None
        return CoverageState(segs, True, status)
    if kind is EventKind.WELLBORE_STATUS:
        assert event.status is not None
        return replace(state, wellbore_status=event.status.value)
    if event.depth is None:
        return state  # retract / unmapped: no state transition
    lo, hi = event.depth.from_md_m, event.depth.to_md_m
    if kind in (EventKind.PERFORATE, EventKind.REPERFORATE):
        return replace(state, segments=assign(state.segments, lo, hi, perforated=True))
    if kind in (EventKind.OPEN, EventKind.REOPEN):
        return replace(state, segments=assign(state.segments, lo, hi, access=Access.OPEN.value))
    if kind is EventKind.ISOLATE:
        return replace(state, segments=assign(state.segments, lo, hi, access=Access.ISOLATED.value))
    if kind is EventKind.INTERVAL_FLOW:
        assert event.status is not None
        return replace(state, segments=assign(state.segments, lo, hi, flow=event.status.value))
    return state


def measure(
    segments: tuple[Segment, ...], *, access: str | None = None, not_access: str = ""
) -> Decimal:
    total = Decimal(0)
    for seg in segments:
        if not seg.perforated:
            continue
        if access is not None and seg.access != access:
            continue
        if not_access and seg.access == not_access:
            continue
        total += seg.end - seg.start
    return total

"""Piecewise-constant MD-interval state (exact Decimal metres, no float snapping)."""

from __future__ import annotations

from bisect import bisect_left, bisect_right
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
    """Set attributes over [lo, hi); O(log S + k) search, only the touched slice is rebuilt."""
    i = bisect_right(segments, lo, key=lambda s: s.end)  # first segment ending after lo
    j = bisect_left(segments, hi, key=lambda s: s.start)  # first segment starting at/after hi
    out: list[Segment] = []
    cursor = lo
    for seg in segments[i:j]:
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
    left = max(i - 1, 0)
    right = min(j + 1, len(segments))
    merged = _normalise([*segments[left:i], *out, *segments[j:right]])
    return segments[:left] + merged + segments[right:]


def extract(state: CoverageState, lo: Decimal, hi: Decimal) -> CoverageState:
    """Local copy of the state clipped to [lo, hi) (for sub-component exploration)."""
    i = bisect_right(state.segments, lo, key=lambda s: s.end)
    j = bisect_left(state.segments, hi, key=lambda s: s.start)
    clipped = [replace(s, start=max(s.start, lo), end=min(s.end, hi)) for s in state.segments[i:j]]
    return CoverageState(tuple(clipped), state.baseline, state.wellbore_status)


def splice(state: CoverageState, lo: Decimal, hi: Decimal, local: CoverageState) -> CoverageState:
    """Replace the [lo, hi) part of ``state`` with ``local`` (inverse of ``extract``)."""
    i = bisect_right(state.segments, lo, key=lambda s: s.end)
    j = bisect_left(state.segments, hi, key=lambda s: s.start)
    mid: list[Segment] = []
    for seg in state.segments[i:j]:
        if seg.start < lo:
            mid.append(replace(seg, end=lo))
    mid.extend(local.segments)
    for seg in state.segments[i:j]:
        if seg.end > hi:
            mid.append(replace(seg, start=hi))
    left = max(i - 1, 0)
    right = min(j + 1, len(state.segments))
    merged = _normalise([*state.segments[left:i], *mid, *state.segments[j:right]])
    segs = state.segments[:left] + merged + state.segments[right:]
    return CoverageState(segs, local.baseline, local.wellbore_status)


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

"""Deterministic as-of perforation state: unique-MD union, scoped state, honest unknowns.

Pure Python, no I/O, no network/provider calls. Persistence, DTOs and PH-4 (MD<->TVD
inversion) are out of scope; recorded TVD is carried verbatim and derived TVD is never filled.
"""

from __future__ import annotations

import hashlib
import json
from bisect import bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from fieldlens.engineering.provenance import MARKER_REASON, is_model_proposal

from .models import (
    FEET_TO_METRES,
    EventKind,
    EventRejection,
    IntervalState,
    PerforationEvent,
    PerforationState,
    Precision,
    RecordedDepth,
    RecordedDepthEvidence,
    UnresolvedCoverage,
)
from .parsing import parse_event
from .state import CoverageState, apply_event, extract, measure, splice

MAX_GROUP_EVENTS = 12  # interacting (non-commuting/optional) events explored exactly
MAX_CANDIDATES = 32
_AXES = ("perforation", "access", "flow")


def derive_event_id(source_record_id: str, wellbore_id: str, kind: str, *parts: str) -> str:
    """Stable content-addressed event id (same source record -> same id on re-import)."""
    payload = json.dumps([source_record_id, wellbore_id, kind, *parts], separators=(",", ":"))
    return "pev_" + hashlib.sha256(payload.encode()).hexdigest()[:24]


def _ambiguity_reason(events: Iterable[PerforationEvent]) -> str:
    if any(e.effective.precision is Precision.DAY for e in events):
        return "date_precision_order_unresolved"
    return "same_time_order_unresolved"


class PerforationHistory:
    """Validated, wellbore-scoped event history. Build once; query any (as_of, revision)."""

    def __init__(
        self,
        wellbore_id: str,
        md_datum: str,
        events: tuple[PerforationEvent, ...],
        rejections: tuple[EventRejection, ...],
    ) -> None:
        self.wellbore_id = wellbore_id
        self.md_datum = md_datum
        self.events = events
        self.rejections = rejections

    @classmethod
    def build(
        cls, records: Iterable[Mapping[str, Any]], *, wellbore_id: str, md_datum: str
    ) -> PerforationHistory:
        """Parse records; the result is independent of record order and duplicate imports."""
        rejected: set[EventRejection] = set()
        by_id: dict[str, set[PerforationEvent]] = defaultdict(set)
        for raw in records:
            if is_model_proposal(raw):  # AX-13: a model proposal never feeds a calculation
                rejected.add(
                    EventRejection(
                        str(raw.get("event_id")) if raw.get("event_id") is not None else None,
                        MARKER_REASON,
                        "model-proposed or model-read records are not calculation inputs",
                    )
                )
                continue
            parsed = parse_event(raw, wellbore_id, md_datum)
            if isinstance(parsed, EventRejection):
                rejected.add(parsed)
            else:
                by_id[parsed.event_id].add(parsed)
        accepted: dict[str, PerforationEvent] = {}
        for event_id, variants in by_id.items():
            if len(variants) == 1:
                accepted[event_id] = next(iter(variants))
            else:
                rejected.add(
                    EventRejection(
                        event_id,
                        "duplicate_event_id_conflict",
                        f"{len(variants)} different records share event id {event_id!r}",
                    )
                )
        _validate_supersession(accepted, rejected)
        ordered = tuple(sorted(accepted.values(), key=lambda e: e.event_id))
        ordered_rej = tuple(sorted(rejected, key=lambda r: (r.event_id or "", r.code, r.message)))
        return cls(wellbore_id, md_datum, ordered, ordered_rej)

    # ------------------------------------------------------------------ query
    def state_at(self, as_of: datetime, dataset_revision: int, unit: str = "m") -> PerforationState:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware (no implicit 'today' or local time)")
        if unit not in ("m", "ft"):
            raise ValueError("unit must be 'm' or 'ft'")
        if dataset_revision < 1:
            raise ValueError("dataset_revision must be >= 1")
        asof = as_of.astimezone(UTC)
        active = [e for e in self.events if e.dataset_revision <= dataset_revision]
        superseded = sorted({e.supersedes for e in active if e.supersedes})
        corrections = sorted(e.event_id for e in active if e.supersedes)
        dropped = set(superseded)
        live = [e for e in active if e.event_id not in dropped]
        started = [e for e in live if e.effective.start <= asof]
        unmapped = [e for e in started if e.kind is EventKind.UNMAPPED]
        stateful = [e for e in started if e.kind not in (EventKind.UNMAPPED, EventKind.RETRACT)]
        cands, ambiguities, forced = _resolve(stateful, asof)
        return self._assemble(
            as_of, dataset_revision, unit, asof, stateful, unmapped, cands, ambiguities, forced,
            tuple(corrections), tuple(superseded),
        )  # fmt: skip

    # --------------------------------------------------------------- assembly
    def _assemble(
        self,
        as_of: datetime,
        revision: int,
        unit: str,
        asof: datetime,
        stateful: list[PerforationEvent],
        unmapped: list[PerforationEvent],
        cands: list[CoverageState],
        ambiguities: list[tuple[str, list[PerforationEvent]]],
        forced: list[list[PerforationEvent]],
        corrections: tuple[str, ...],
        superseded: tuple[str, ...],
    ) -> PerforationState:
        divisor = FEET_TO_METRES if unit == "ft" else Decimal(1)

        def out(value: Decimal) -> float:
            return float(value / divisor)

        cand_list = list(cands)
        baseline_all = all(c.baseline for c in cand_list)
        limitations: list[str] = []
        unresolved: list[UnresolvedCoverage] = []
        blocked = bool(unmapped) or bool(forced)
        intervals, differing = _merge_intervals(cand_list, baseline_all, stateful, out)

        if forced:
            intervals = _mark_forced(intervals, forced, out)
        flagged = [iv for iv in intervals if iv.unresolved_axes]
        # unresolved coverage per ambiguity record (only where candidates still differ).
        for reason, events in ambiguities:
            has_baseline = any(e.kind is EventKind.BASELINE for e in events)
            ranges = _event_ranges(events)
            for axis in _AXES:
                hits = [
                    (iv.from_md, iv.to_md)
                    for iv in flagged
                    if axis_in(iv, axis) and (has_baseline or _overlaps_any(iv, ranges, out))
                ]
                if hits:
                    unresolved.append(_entry(reason, axis, hits, events))
            if differing["wellbore_status"] and any(
                e.kind in (EventKind.WELLBORE_STATUS, EventKind.BASELINE) for e in events
            ):
                unresolved.append(_entry(reason, "wellbore_status", [], events))
        for events in forced:
            hits = [(out(a), out(b)) for a, b in _event_ranges(events)]
            unresolved.append(_entry("ambiguous_component_too_large", "all", hits, events))
        for event in unmapped:
            hits = [] if event.depth is None else [_depth_range(event.depth, out)]
            unresolved.append(_entry("unmapped_event_code", "all", hits, [event]))

        statuses = {c.wellbore_status for c in cand_list}
        wellbore_status = "unknown"
        status_forced = any(
            e.kind in (EventKind.WELLBORE_STATUS, EventKind.BASELINE)
            for group in forced
            for e in group
        )
        if len(statuses) == 1 and not status_forced:
            wellbore_status = next(iter(statuses)) or "unknown"

        conflicting = bool(unresolved) and bool(ambiguities or forced)
        if not stateful and not unmapped:
            status = "unknown"
            limitations.append("no_known_event_at_or_before_as_of")
        elif conflicting:
            status = "conflicting"
        else:
            status = "resolved"
        if not baseline_all:
            limitations.append("baseline_not_established")
        if unmapped:
            limitations.append("unmapped_event_code_blocks_dependent_state")
        if conflicting:
            limitations.append("event_order_unresolved")

        total_lo = total_hi = total = None
        open_lo = open_hi = open_exact = None
        if status != "unknown":
            totals = [measure(c.segments) for c in cand_list]
            opens = [measure(c.segments, access="open") for c in cand_list]
            not_iso = [measure(c.segments, not_access="isolated") for c in cand_list]
            unknown_access = [measure(c.segments, access="unknown") for c in cand_list]
            exact_ok = baseline_all and not blocked
            total_lo, total_hi_raw = out(min(totals)), out(max(totals))
            total_hi = total_hi_raw if exact_ok else None
            total = total_lo if exact_ok and total_lo == total_hi_raw else None
            open_lo = out(min(opens))
            open_hi = out(max(not_iso)) if exact_ok else None
            if forced:  # candidate set is not exhaustive: open bounds would be unsound
                open_lo = open_hi = None
            if any(e.kind is EventKind.BASELINE for group in forced for e in group):
                total_lo = total_hi = None
            if exact_ok and not forced and not any(unknown_access) and min(opens) == max(opens):
                open_exact = open_lo
            elif exact_ok and any(unknown_access):
                limitations.append("access_state_unknown_for_perforated_interval")
            if status == "resolved" and (not baseline_all or blocked or open_exact is None):
                status = "partial"

        evidence = sorted({e.event_id for e in stateful})
        recorded = tuple(_evidence(e, out) for e in stateful if e.depth is not None) + tuple(
            _evidence_baseline(e, i, out) for e in stateful for i in e.baseline_intervals
        )
        return PerforationState(
            wellbore_id=self.wellbore_id,
            as_of=as_of,
            dataset_revision=revision,
            unit=unit,
            status=status,
            baseline_established=baseline_all,
            total_length=total,
            total_length_lower_bound=total_lo,
            total_length_upper_bound=total_hi,
            open_length=open_exact,
            open_length_lower_bound=open_lo,
            open_length_upper_bound=open_hi,
            wellbore_status=wellbore_status,
            intervals=intervals,
            unresolved=tuple(unresolved),
            limitations=tuple(dict.fromkeys(limitations)),
            evidence_event_ids=tuple(evidence),
            recorded_depths=recorded,
            correction_event_ids=corrections,
            superseded_event_ids=superseded,
            unmapped_event_ids=tuple(sorted(e.event_id for e in unmapped)),
            rejected_events=self.rejections,
        )


# ---------------------------------------------------------------------- helpers
def _mark_forced(
    intervals: tuple[IntervalState, ...],
    forced: list[list[PerforationEvent]],
    out: Any,
) -> tuple[IntervalState, ...]:
    """Over-budget groups: the candidate set is a bracket, not exhaustive, so every row touched
    by a forced group (all rows if it holds a baseline, which resets everything) carries no
    definite value; its affected axes are unresolved."""
    everything = any(e.kind is EventKind.BASELINE for g in forced for e in g)
    merged: list[list[float]] = []
    for lo, hi in sorted(
        (out(a), out(b)) for a, b in _event_ranges([e for g in forced for e in g])
    ):
        if merged and lo <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], hi)
        else:
            merged.append([lo, hi])
    ends = [m[1] for m in merged]
    marked: list[IntervalState] = []
    for iv in intervals:
        k = bisect_right(ends, iv.from_md)  # first merged range ending after the row starts
        if everything or (k < len(merged) and merged[k][0] < iv.to_md):
            marked.append(
                replace(
                    iv, perforated=None, access="unknown", flow="unknown", unresolved_axes=_AXES
                )
            )
        else:
            marked.append(iv)
    return tuple(marked)


def axis_in(iv: IntervalState, axis: str) -> bool:
    return axis in iv.unresolved_axes


def _validate_supersession(
    accepted: dict[str, PerforationEvent], rejected: set[EventRejection]
) -> None:
    changed = True
    while changed:
        changed = False
        bad: dict[str, tuple[str, str]] = {}
        for event in accepted.values():
            target = accepted.get(event.supersedes) if event.supersedes else None
            if event.kind is EventKind.RETRACT and not event.supersedes:
                bad[event.event_id] = ("malformed_event", "retract needs a supersedes target")
            elif event.supersedes and event.supersedes == event.event_id:
                bad[event.event_id] = ("invalid_supersession", "event cannot supersede itself")
            elif event.supersedes and target is None:
                bad[event.event_id] = ("invalid_supersession", "superseded event is unknown")
            elif target is not None and event.dataset_revision <= target.dataset_revision:
                bad[event.event_id] = (
                    "invalid_supersession",
                    "correction must belong to a later dataset revision",
                )
        by_target: dict[str, list[PerforationEvent]] = defaultdict(list)
        for event in accepted.values():
            if event.supersedes and event.event_id not in bad:
                by_target[event.supersedes].append(event)
        for target_id, corrections in by_target.items():
            corrections.sort(key=lambda e: (e.dataset_revision, e.event_id))
            first_rev = corrections[0].dataset_revision
            for event in corrections:
                if (
                    event.dataset_revision == first_rev
                    and len([c for c in corrections if c.dataset_revision == first_rev]) > 1
                ):
                    bad[event.event_id] = ("conflicting_supersession", "multiple corrections tie")
                elif event.dataset_revision > first_rev:
                    bad[event.event_id] = (
                        "invalid_supersession",
                        f"{target_id!r} is already corrected; supersede the latest correction",
                    )
        for event_id, (code, message) in bad.items():
            rejected.add(EventRejection(event_id, code, message))
            del accepted[event_id]
            changed = True


def _window(event: PerforationEvent) -> tuple[datetime, datetime]:
    """Ordering window. An instant baseline establishes the state at the START of its instant
    (zero-width window), so it precedes same-instant events (assumption D5, see spec)."""
    eff = event.effective
    if event.kind is EventKind.BASELINE and eff.precision is Precision.INSTANT:
        return eff.start, eff.start
    return eff.start, eff.end


def _components(events: list[PerforationEvent]) -> list[list[PerforationEvent]]:
    ordered = sorted(events, key=lambda e: (e.effective.start, _window(e)[1], e.event_id))
    comps: list[list[PerforationEvent]] = []
    horizon: datetime | None = None
    zero_start: datetime | None = None  # start of a zero-width baseline in the current component
    for event in ordered:
        start, end = _window(event)
        zero = start == end
        joins = bool(comps) and horizon is not None and (
            start < horizon or (zero and zero_start == start)
        )  # fmt: skip
        if joins:
            comps[-1].append(event)
            assert horizon is not None
            horizon = max(horizon, end)
        else:
            comps.append([event])
            horizon = end
            zero_start = None
        if zero:
            zero_start = start
    return comps


# An assignment is (variable, value, lo, hi); two events commute unless they assign different
# values to the same variable over overlapping MD ranges (wellbore status: always overlapping).
_WHOLE = (Decimal(0), Decimal(1))


def _assignment(e: PerforationEvent) -> tuple[str, str, Decimal, Decimal]:
    kind = e.kind
    if kind is EventKind.WELLBORE_STATUS:
        assert e.status is not None
        return ("W", e.status.value, *_WHOLE)
    assert e.depth is not None
    lo, hi = e.depth.from_md_m, e.depth.to_md_m
    if kind in (EventKind.PERFORATE, EventKind.REPERFORATE):
        return ("P", "true", lo, hi)
    if kind in (EventKind.OPEN, EventKind.REOPEN):
        return ("A", "open", lo, hi)
    if kind is EventKind.ISOLATE:
        return ("A", "isolated", lo, hi)
    assert e.status is not None
    return ("F", e.status.value, lo, hi)


def _conflict_edges(events: list[PerforationEvent]) -> list[tuple[int, int]]:
    """Pairs of events whose relative order changes the outcome (non-commuting)."""
    edges: list[tuple[int, int]] = []
    baselines = [i for i, e in enumerate(events) if e.kind is EventKind.BASELINE]
    for b in baselines:
        eb = events[b]
        payload = (eb.status, eb.baseline_intervals)
        for j, other in enumerate(events):
            if j == b or (j < b and j in baselines):
                continue
            if (
                other.kind is EventKind.BASELINE
                and (other.status, other.baseline_intervals) == payload
            ):
                continue  # identical baselines commute
            edges.append((b, j))
    by_var: dict[str, list[tuple[Decimal, Decimal, int, str]]] = defaultdict(list)
    for i, e in enumerate(events):
        if e.kind is not EventKind.BASELINE:
            var, val, lo, hi = _assignment(e)
            by_var[var].append((lo, hi, i, val))
    for items in by_var.values():
        items.sort()
        active: dict[str, list[tuple[Decimal, int]]] = defaultdict(list)  # value -> (hi, idx)
        for lo, hi, idx, val in items:
            for other_val, lst in active.items():
                lst[:] = [(h, k) for h, k in lst if h > lo]
                if other_val != val:
                    edges.extend((k, idx) for _, k in lst)
            active[val].append((hi, idx))
    return edges


def _groups(n: int, edges: list[tuple[int, int]]) -> list[list[int]]:
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        parent[find(a)] = find(b)
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values())


def _group_window(group: list[PerforationEvent]) -> tuple[Decimal, Decimal] | None:
    if any(e.kind is EventKind.BASELINE for e in group):
        return None  # a baseline resets everything: explore on the full state
    ranges = [_assignment(e)[2:] for e in group if e.kind is not EventKind.WELLBORE_STATUS]
    if not ranges:
        return (Decimal(0), Decimal(0))
    return (min(r[0] for r in ranges), max(r[1] for r in ranges))


def _explore(
    base: CoverageState, group: list[PerforationEvent], certain_mask: int
) -> list[CoverageState]:
    """Reachable states over included subsets/orders of ``group`` (DP over subsets)."""
    window = _group_window(group)
    local = base
    if window is not None:
        lo, hi = window
        local = (
            extract(base, lo, hi)
            if lo < hi
            else CoverageState((), base.baseline, base.wellbore_status)
        )
    n = len(group)
    # Strict time order between non-overlapping windows is respected (N2): only events whose
    # windows overlap are mutually unordered. before[k]/after[k] are bitmasks over the group.
    wins = [_window(e) for e in group]
    before = [0] * n
    after = [0] * n
    for j in range(n):
        for k in range(n):
            if j != k and wins[j][1] <= wins[k][0] and not wins[k][1] <= wins[j][0]:
                before[k] |= 1 << j
                after[j] |= 1 << k
    reach: list[set[CoverageState]] = [set() for _ in range(1 << n)]
    reach[0].add(local)
    for mask in range(1, 1 << n):
        acc = reach[mask]
        for k in range(n):
            bit = 1 << k
            if mask & bit:
                prev = mask ^ bit
                if (certain_mask & before[k]) & ~prev or prev & after[k]:
                    continue
                for state in reach[prev]:
                    acc.add(apply_event(state, group[k]))
    outcomes: set[CoverageState] = set()
    for mask in range(1 << n):
        if mask & certain_mask == certain_mask:
            outcomes |= reach[mask]
    if window is None:
        return list(outcomes)
    lo, hi = window
    if lo >= hi:
        return [CoverageState(base.segments, o.baseline, o.wellbore_status) for o in outcomes]
    return [splice(base, lo, hi, o) for o in outcomes]


def _bracket(cands: list[CoverageState]) -> list[CoverageState]:
    """Lowest- and highest-coverage candidate per wellbore status (bounded, never exhaustive)."""
    by_status: dict[str | None, list[CoverageState]] = {}
    for c in cands:
        by_status.setdefault(c.wellbore_status, []).append(c)
    reps: list[CoverageState] = []
    for group in by_status.values():
        reps.append(min(group, key=lambda c: measure(c.segments)))
        reps.append(max(group, key=lambda c: measure(c.segments)))
    return reps


def _apply_all(state: CoverageState, events: list[PerforationEvent]) -> CoverageState:
    for e in sorted(events, key=lambda x: x.event_id):
        state = apply_event(state, e)
    return state


def _resolve(
    events: list[PerforationEvent], asof: datetime
) -> tuple[
    list[CoverageState], list[tuple[str, list[PerforationEvent]]], list[list[PerforationEvent]]
]:
    cands: list[CoverageState] = [CoverageState()]
    ambiguities: list[tuple[str, list[PerforationEvent]]] = []
    forced: list[list[PerforationEvent]] = []
    degraded = False
    for comp in _components(events):
        certain_flags = [
            e.effective.precision is Precision.INSTANT or e.effective.end <= asof for e in comp
        ]
        if len(comp) == 1 and certain_flags[0]:
            cands = [apply_event(c, comp[0]) for c in cands]
            continue
        raw_groups = _groups(len(comp), _conflict_edges(comp))
        free: list[PerforationEvent] = []
        groups: list[list[int]] = []
        for g in raw_groups:
            if len(g) == 1 and certain_flags[g[0]]:
                free.append(comp[g[0]])
            else:
                groups.append(g)
        free.sort(key=lambda e: e.event_id)
        for e in free:
            cands = [apply_event(c, e) for c in cands]
        groups.sort(key=lambda g: min(comp[i].event_id for i in g))
        for g in groups:
            group = sorted((comp[i] for i in g), key=lambda e: e.event_id)
            mask = 0
            for k, e in enumerate(group):
                if e.effective.precision is Precision.INSTANT or e.effective.end <= asof:
                    mask |= 1 << k
            new: list[CoverageState] = []
            ambiguous = False
            too_big = degraded or len(group) > MAX_GROUP_EVENTS
            if not too_big:
                for base in cands:
                    outs = _explore(base, group, mask)
                    ambiguous = ambiguous or len(outs) > 1
                    new.extend(outs)
                if len(new) > MAX_CANDIDATES:  # hash full states only on overflow
                    new = list(dict.fromkeys(new))
                too_big = len(new) > MAX_CANDIDATES
            if too_big:
                # Budget exceeded for an interacting group: explicit unresolved result. From here
                # on only a bracket is kept: lowest-/highest-coverage candidate with the certain/
                # all events applied (perforation is monotone absent a baseline). Open bounds are
                # withheld; no order is presented as fact.
                forced.append(group)
                certain = [e for k, e in enumerate(group) if mask & (1 << k)]
                if not degraded:
                    degraded = True
                    cands = _bracket(cands)  # (low, high) pairs per wellbore status
                new = [_apply_all(c, group if k % 2 else certain) for k, c in enumerate(cands)]
            elif ambiguous:
                ambiguities.append((_ambiguity_reason(group), group))
            cands = list(new)
    return cands, ambiguities, forced


def _attrs_at(state: CoverageState, point: Decimal) -> tuple[bool, str, str]:
    segs = state.segments
    i = bisect_right(segs, point, key=lambda s: s.end)
    if i < len(segs) and segs[i].start <= point:
        return segs[i].attrs()
    return (False, "unknown", "unknown")


def _merge_intervals(
    cands: list[CoverageState],
    baseline_all: bool,
    events: list[PerforationEvent],
    out: Any,
) -> tuple[tuple[IntervalState, ...], dict[str, bool]]:
    rows: list[tuple[Decimal, Decimal, Any, str, str, tuple[str, ...]]] = []
    if len(cands) == 1:
        for seg in cands[0].segments:
            known = True if seg.perforated else (False if baseline_all else None)
            rows.append((seg.start, seg.end, known, seg.access, seg.flow, ()))
    else:
        bounds = sorted({p for c in cands for s in c.segments for p in (s.start, s.end)})
        for lo, hi in zip(bounds, bounds[1:], strict=False):
            attrs = [_attrs_at(c, lo) for c in cands]
            if all(a == (False, "unknown", "unknown") for a in attrs):
                continue
            axes: list[str] = []
            perf: Any
            if len({a[0] for a in attrs}) > 1:
                axes.append("perforation")
                perf = None
            else:
                perf = True if attrs[0][0] else (False if baseline_all else None)
            access = attrs[0][1]
            if len({a[1] for a in attrs}) > 1:
                axes.append("access")
                access = "unknown"
            flow = attrs[0][2]
            if len({a[2] for a in attrs}) > 1:
                axes.append("flow")
                flow = "unknown"
            row = (lo, hi, perf, access, flow, tuple(axes))
            if rows and rows[-1][1] == lo and rows[-1][2:] == row[2:]:
                rows[-1] = (rows[-1][0], hi, *row[2:])
            else:
                rows.append(row)
    evidence = _row_evidence(rows, events)
    intervals = tuple(
        IntervalState(out(lo), out(hi), perf, access, flow, axes, evidence[k])
        for k, (lo, hi, perf, access, flow, axes) in enumerate(rows)
    )
    differing = {"wellbore_status": len({c.wellbore_status for c in cands}) > 1}
    return intervals, differing


def _row_evidence(rows: list[Any], events: list[PerforationEvent]) -> list[tuple[str, ...]]:
    """Event ids overlapping each row, via binary search (rows are sorted and disjoint)."""
    found: list[set[str]] = [set() for _ in rows]
    for e in events:
        for lo, hi in _all_ranges(e):
            k = bisect_right(rows, lo, key=lambda r: r[1])
            while k < len(rows) and rows[k][0] < hi:
                found[k].add(e.event_id)
                k += 1
    return [tuple(sorted(f)) for f in found]


def _all_ranges(event: PerforationEvent) -> list[tuple[Decimal, Decimal]]:
    ranges = [(i.depth.from_md_m, i.depth.to_md_m) for i in event.baseline_intervals]
    if event.depth is not None:
        ranges.append((event.depth.from_md_m, event.depth.to_md_m))
    return ranges


def _event_ranges(events: list[PerforationEvent]) -> list[tuple[Decimal, Decimal]]:
    return [r for e in events for r in _all_ranges(e)]


def _overlaps_any(iv: IntervalState, ranges: list[tuple[Decimal, Decimal]], out: Any) -> bool:
    return any(out(a) < iv.to_md and iv.from_md < out(b) for a, b in ranges)


def _depth_range(depth: RecordedDepth, out: Any) -> tuple[float, float]:
    return (out(depth.from_md_m), out(depth.to_md_m))


def _entry(
    reason: str, axis: str, hits: list[tuple[float, float]], events: list[PerforationEvent]
) -> UnresolvedCoverage:
    merged: list[tuple[float, float]] = []
    for lo, hi in sorted(hits):
        if merged and merged[-1][1] >= lo:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return UnresolvedCoverage(
        reason=reason,
        axis=axis,
        md_intervals=tuple(merged),
        time_from=min(e.effective.start for e in events),
        time_to=max(e.effective.end for e in events),
        event_ids=tuple(sorted(e.event_id for e in events)),
    )


def _evidence(event: PerforationEvent, out: Any) -> RecordedDepthEvidence:
    assert event.depth is not None
    return _evidence_for(event, event.depth, out)


def _evidence_baseline(event: PerforationEvent, item: Any, out: Any) -> RecordedDepthEvidence:
    return _evidence_for(event, item.depth, out)


def _evidence_for(event: PerforationEvent, d: RecordedDepth, out: Any) -> RecordedDepthEvidence:
    return RecordedDepthEvidence(
        event_id=event.event_id,
        kind=event.kind.value,
        source_code=event.source_code,
        from_value=d.from_value,
        to_value=d.to_value,
        unit=d.unit,
        reference=d.reference,
        datum=d.datum,
        from_md=out(d.from_md_m),
        to_md=out(d.to_md_m),
        recorded_tvd=d.recorded_tvd,
        derived_tvd=None,
    )

"""Perforation history for charts: source records -> engine events -> dated length steps.

Reuses ``engineering.perforation`` (not edited): the union of unique MD intervals decides every
length, so overlapping/duplicate intervals are never double counted. Nothing is invented:

* only dated ``perforation_interval`` records become engine events; an interval record without a
  usable date, depth or unit is listed with the reason and stays out of the steps;
* date precision is kept (a day stays a day) and same-day events are never ordered here: the
  engine reports an unresolved step as ``length = None`` with its reason;
* before the first dated event the length is *unknown* (no step is emitted, never zero);
* interval status columns of the source (``current_status``) are carried as text only: no
  squeeze/plug transition is inferred from them, so the open length is only reported where the
  engine can resolve it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from fieldlens.contracts.charts import (
    ChartEmptyReason,
    ChartEmptyState,
    PerforatedLengthStep,
    PerforationEventKind,
)
from fieldlens.contracts.charts import PerforationEvent as PerforationEventDto
from fieldlens.contracts.charts import PerforationHistory as PerforationHistoryDto
from fieldlens.contracts.evidence import EvidenceLink, Locator
from fieldlens.engineering.perforation import PerforationHistory, derive_event_id

#: The source tables state no MD datum. Lengths are differences of MD values, which do not depend
#: on the datum, so one explicit placeholder is used for every record (never a guessed RKB/MSL).
MD_DATUM_UNSTATED = "unstated-in-source"
MAX_EVENTS = 2000
_UNITS = {"m": "m", "ft": "ft", "feet": "ft", "metre": "m", "meter": "m", "metres": "m"}


@dataclass(frozen=True)
class PerfRow:
    """One ``perforation_interval`` record, reduced to what the history needs."""

    record_id: UUID
    ordinal: int
    top: float | None
    base: float | None
    unit: str | None
    unit_defaulted: bool
    literal: str | None
    precision: str | None
    timezone_known: bool
    description: str | None = None
    validation_state: str | None = None
    evidence: EvidenceLink | None = None


@dataclass
class StepRow:
    key: str  # ISO date (day precision) or ISO instant
    x: str
    effective_date: date | None
    effective_at: datetime | None
    total: float | None
    open: float | None
    event_ids: list[UUID]
    reason: str | None


@dataclass
class PerfResult:
    history: PerforationHistoryDto
    steps: list[StepRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unit_assumed: bool = False
    dated_events: int = 0
    undated_events: int = 0
    evidence: list[EvidenceLink] = field(default_factory=list)


def _norm_unit(row: PerfRow) -> str | None:
    return None if row.unit is None else _UNITS.get(row.unit.strip().lower())


def _engine_record(row: PerfRow, wellbore_id: str) -> tuple[str, dict[str, Any] | None, str | None]:
    """(engine event id, engine record or None, reason the record is not usable)."""
    eid = derive_event_id(str(row.record_id), wellbore_id, "perforate")
    if row.top is None or row.base is None:
        return eid, None, "interval depth is missing in the source"
    unit = _norm_unit(row)
    if unit is None:
        return eid, None, "depth unit is not metres or feet"
    precision = row.precision
    if precision not in ("day", "instant") or row.literal is None:
        return eid, None, f"effective date unusable (precision {precision or 'unknown'})"
    if precision == "instant" and not row.timezone_known:
        return eid, None, "instant has no UTC offset"
    record: dict[str, Any] = {
        "event_id": eid,
        "wellbore_id": wellbore_id,
        "kind": "perforate",
        "dataset_revision": 1,
        "precision": precision,
        "effective_time": row.literal,
        "depth": {
            "from": row.top,
            "to": row.base,
            "unit": unit,
            "reference": "MD",
            "datum": MD_DATUM_UNSTATED,
        },
    }
    if precision == "day":
        record["timezone"] = "UTC"
    return eid, record, None


def _instant(literal: str) -> datetime:
    return datetime.fromisoformat(literal.replace(" ", "T")).astimezone(UTC)


def _day_end(day: date) -> datetime:
    return datetime.combine(day + timedelta(days=1), time.min, tzinfo=UTC) - timedelta(
        microseconds=1
    )


def _event_day(event: PerforationEventDto) -> date | None:
    if event.effective_date is not None:
        return event.effective_date
    return event.effective_at.date() if event.effective_at is not None else None


def _bounds_reason(state: Any) -> str:
    text = f"engine state {state.status}"
    lo, hi = state.total_length_lower_bound, state.total_length_upper_bound
    if lo is not None and hi is not None:
        text += f"; total between {lo:g} and {hi:g} {state.unit}"
    if state.limitations:
        text += f" ({'; '.join(state.limitations)})"
    return text


def build(
    wellbore_id: UUID, rows: list[PerfRow], as_of: date | None, *, label: str = "wellbore"
) -> PerfResult:
    wid = str(wellbore_id)
    ordered = sorted(rows, key=lambda r: (r.record_id.int, r.ordinal))
    prepared = {r.record_id: _engine_record(r, wid) for r in ordered}
    engine = PerforationHistory.build(
        [rec for _, rec, _ in prepared.values() if rec is not None],
        wellbore_id=wid,
        md_datum=MD_DATUM_UNSTATED,
    )
    rejected = {rej.event_id: rej for rej in engine.rejections if rej.event_id}
    notes: list[str] = []
    events: list[PerforationEventDto] = []
    usable: dict[UUID, PerfRow] = {}
    for row in ordered:
        eid, rec, reason = prepared[row.record_id]
        if rec is not None and eid in rejected:
            reason = f"{rejected[eid].code}: {rejected[eid].message}"
        elif rec is not None:
            usable[row.record_id] = row
        lit = row.literal or ""
        day = date.fromisoformat(lit[:10]) if rec and row.precision == "day" and lit else None
        at = _instant(lit) if rec and row.precision == "instant" and not reason and lit else None
        if rec is not None and eid in rejected:
            day, at = None, None
        unit = _norm_unit(row)
        events.append(
            PerforationEventDto(
                event_id=row.record_id,
                wellbore_id=wellbore_id,
                kind=PerforationEventKind.PERFORATE,
                effective_at=at,
                effective_date=day,
                effective_time_unknown_reason=reason,
                top_md=row.top,
                base_md=row.base,
                depth_unit=unit or row.unit,
                description=row.description,
                validation_state=row.validation_state,
                evidence=[row.evidence] if row.evidence else [],
            )
        )
    events.sort(
        key=lambda e: (
            e.effective_at.isoformat()
            if e.effective_at
            else (e.effective_date or date.max).isoformat(),
            e.top_md if e.top_md is not None else float("inf"),
            e.event_id.int,
        )
    )
    dated = len(usable)
    undated = len(rows) - dated
    if undated:
        notes.append(
            f"{undated} perforation interval record(s) are not on the timeline "
            "(no usable date, depth or unit); they are listed with the reason."
        )
    assumed = any(r.unit_defaulted for r in usable.values())
    if assumed:
        notes.append(
            "The source states no depth unit; metres are assumed (owner decision, flagged by the "
            "extraction profile)."
        )
    if any(r.precision == "day" for r in usable.values()):
        notes.append(
            "Day-precision dates are kept as dates; events of one day are not ordered, and a "
            "step the engine cannot resolve shows no value."
        )
    notes.append(
        "Length before the first dated event is unknown (not zero); source status columns are "
        "not interpreted as squeeze/plug events."
    )
    revision = hashlib.sha256(
        json.dumps(
            [[str(r.record_id), r.top, r.base, r.unit, r.literal, r.precision] for r in ordered],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    steps = _steps(engine, usable, as_of) if usable else []
    at_as_of: float | None = None
    if as_of is not None and usable:
        state = engine.state_at(_day_end(as_of), 1, "m")
        if steps and state.status == "resolved":  # steps exist only for dated events <= as_of
            at_as_of = state.total_length
    empty = None
    if not rows:
        empty = ChartEmptyState(
            reason=ChartEmptyReason.NO_RECORDS,
            message=f"No perforation interval records exist for this {label}.",
        )
    elif not steps and as_of is not None and usable:
        empty = ChartEmptyState(
            reason=ChartEmptyReason.AS_OF_BEFORE_DATA,
            message="Every dated perforation event is after the selected as-of date.",
        )
    elif not usable:
        empty = ChartEmptyState(
            reason=ChartEmptyReason.SOURCE_UNAVAILABLE,
            message="Perforation records exist but none has a usable date, depth and unit.",
        )
    shown = events[:MAX_EVENTS]
    if len(events) > MAX_EVENTS:
        notes.append(f"Only the first {MAX_EVENTS} of {len(events)} events are listed.")
    if as_of is not None:
        shown = [e for e in shown if _event_day(e) is None or _event_day(e) <= as_of]  # type: ignore[operator]
    dto = PerforationHistoryDto(
        wellbore_id=wellbore_id,
        as_of=as_of,
        events=shown,
        steps=[
            PerforatedLengthStep(
                effective_at=s.effective_at,
                effective_date=s.effective_date,
                length=s.total,
                unit="m" if s.total is not None else None,
                event_ids=s.event_ids,
                unknown_reason=s.reason,
            )
            for s in steps
        ],
        perforated_length_at_as_of=at_as_of,
        length_unit="m",
        empty=empty,
        revision=revision,
    )
    links = [e.evidence[0] for e in shown if e.evidence][:20]
    return PerfResult(
        history=dto,
        steps=steps,
        notes=notes,
        unit_assumed=assumed,
        dated_events=dated,
        undated_events=undated,
        evidence=links,
    )


def _steps(
    engine: PerforationHistory,
    usable: dict[UUID, PerfRow],
    as_of: date | None,
) -> list[StepRow]:
    groups: dict[tuple[str, str], list[UUID]] = {}
    when: dict[tuple[str, str], tuple[date | None, datetime | None, datetime]] = {}
    for rid, row in usable.items():
        assert row.literal is not None
        if row.precision == "day":
            day = date.fromisoformat(row.literal[:10])
            key = (day.isoformat(), "day")
            when[key] = (day, None, _day_end(day))
        else:
            moment = _instant(row.literal)
            key = (moment.isoformat(), "instant")
            when[key] = (None, moment, moment)
        groups.setdefault(key, []).append(rid)
    steps: list[StepRow] = []
    for key in sorted(groups, key=lambda k: (when[k][2], k)):
        day_v, moment_v, evaluate_at = when[key]
        if as_of is not None and evaluate_at > _day_end(as_of):
            continue
        state = engine.state_at(evaluate_at, 1, "m")
        resolved = state.status == "resolved"
        steps.append(
            StepRow(
                key=key[0],
                x=key[0],
                effective_date=day_v,
                effective_at=moment_v,
                total=state.total_length if resolved else None,
                open=state.open_length if resolved else None,
                event_ids=sorted(groups[key], key=lambda u: u.int),
                reason=None
                if resolved and state.total_length is not None
                else _bounds_reason(state),
            )
        )
    return steps


def locator_link(
    locator: dict[str, Any], document_id: UUID, revision_id: UUID, record_id: UUID | None
) -> EvidenceLink | None:
    try:
        loc = Locator.model_validate(
            {**locator, "document_id": document_id, "source_revision_id": revision_id}
        )
        return EvidenceLink(
            document_id=document_id,
            source_revision_id=revision_id,
            record_id=record_id,
            locator=loc,
        )
    except (ValidationError, ValueError, TypeError):
        return None

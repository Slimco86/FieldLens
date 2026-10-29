"""Strict per-record parsing: a malformed record yields an explicit rejection, never an exception
that could corrupt unrelated validated history."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import (
    CODE_TO_KIND,
    DEPTH_KINDS,
    FEET_TO_METRES,
    INSTANT_WIDTH,
    Access,
    BaselineInterval,
    EffectiveTime,
    EventKind,
    EventRejection,
    FlowStatus,
    PerforationEvent,
    Precision,
    RecordedDepth,
    TvdRecord,
)

# Documented plausibility bound for any MD value after conversion to metres (about 100 km).
MAX_MD_M = Decimal(100_000)
MAX_RAW_DEPTH = Decimal(1_000_000)  # raw-unit pre-check (ft/m) so conversion cannot overflow


class RecordError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, int | float | str | Decimal):
        raise RecordError("malformed_depth", f"{label} must be a number")
    try:
        result = Decimal(str(value).strip())
    except InvalidOperation:
        raise RecordError("malformed_depth", f"{label} is not numeric") from None
    if not result.is_finite():
        raise RecordError("nonfinite_depth", f"{label} must be finite")
    return result


def _parse_tvd(raw: Any) -> TvdRecord:
    if not isinstance(raw, Mapping):
        raise RecordError("malformed_depth", "recorded_tvd must be a mapping")
    for key in ("from", "to"):
        _decimal(raw.get(key), f"recorded_tvd.{key}")
    unit = raw.get("unit")
    if unit not in ("m", "ft"):
        raise RecordError("unsupported_unit", "recorded_tvd.unit must be 'm' or 'ft'")
    datum = raw.get("datum")
    return TvdRecord(
        str(raw["from"]), str(raw["to"]), unit, datum if isinstance(datum, str) else None
    )


def parse_depth(raw: Any, md_datum: str) -> RecordedDepth:
    if not isinstance(raw, Mapping):
        raise RecordError("missing_depth", "depth interval is required")
    unit = raw.get("unit")
    if unit not in ("m", "ft"):
        raise RecordError("unsupported_unit", "depth unit must be 'm' or 'ft'")
    reference = raw.get("reference")
    if reference != "MD":
        raise RecordError(
            "unsupported_depth_reference",
            f"only measured-depth (MD) intervals are accepted, got {reference!r}",
        )
    datum = raw.get("datum")
    if not isinstance(datum, str) or not datum:
        raise RecordError("missing_depth_datum", "MD datum/depth origin is required")
    if datum != md_datum:
        raise RecordError(
            "conflicting_depth_reference",
            f"MD datum {datum!r} conflicts with the wellbore MD datum {md_datum!r}",
        )
    start = _decimal(raw.get("from"), "from")
    end = _decimal(raw.get("to"), "to")
    if start < 0 or end < 0:
        raise RecordError("negative_depth", "MD bounds must be non-negative")
    if max(start, end) > MAX_RAW_DEPTH:  # checked before unit conversion: no overflow possible
        raise RecordError(
            "implausible_depth", f"MD magnitude exceeds the plausibility bound ({MAX_MD_M} m)"
        )
    if start >= end:
        raise RecordError("reversed_depth", "from_md must be strictly less than to_md")
    factor = FEET_TO_METRES if unit == "ft" else Decimal(1)
    if max(start, end) * factor > MAX_MD_M:
        raise RecordError("implausible_depth", f"MD exceeds the plausibility bound ({MAX_MD_M} m)")
    tvd = _parse_tvd(raw["tvd"]) if raw.get("tvd") is not None else None
    return RecordedDepth(
        str(raw["from"]), str(raw["to"]), unit, "MD", datum, start * factor, end * factor, tvd
    )


def _parse_effective(raw: Mapping[str, Any]) -> EffectiveTime:
    precision_raw = raw.get("precision")
    try:
        precision = Precision(str(precision_raw))
    except ValueError:
        raise RecordError("malformed_time", "precision must be 'instant' or 'day'") from None
    value = raw.get("effective_time")
    if precision is Precision.INSTANT:
        try:
            moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
        except ValueError:
            raise RecordError("malformed_time", "effective_time is not ISO-8601") from None
        if moment.tzinfo is None or moment.utcoffset() is None:
            raise RecordError("missing_timezone", "instant effective_time needs a UTC offset")
        start = moment.astimezone(UTC)
        return EffectiveTime(precision, start, start + INSTANT_WIDTH, str(value), None)
    tz_name = raw.get("timezone")
    if not isinstance(tz_name, str) or not tz_name:
        raise RecordError("missing_timezone", "day-precision events need an explicit timezone")
    try:
        zone = UTC if tz_name == "UTC" else ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise RecordError("malformed_time", f"unknown timezone {tz_name!r}") from None
    try:
        if isinstance(value, datetime):
            raise ValueError
        day = value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError:
        raise RecordError("malformed_time", "day effective_time must be YYYY-MM-DD") from None
    start = datetime.combine(day, time.min, tzinfo=zone).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone).astimezone(UTC)
    return EffectiveTime(precision, start, end, day.isoformat(), tz_name)


def _parse_status(raw: Any) -> FlowStatus:
    try:
        status = FlowStatus(raw)
    except ValueError:
        raise RecordError("malformed_status", f"unsupported status {raw!r}") from None
    if status is FlowStatus.UNKNOWN:
        raise RecordError("malformed_status", "'unknown' is not an assertable status")
    return status


def parse_event(
    raw: Mapping[str, Any], wellbore_id: str, md_datum: str
) -> PerforationEvent | EventRejection:
    """Validate one raw record. Never raises for bad data."""
    raw_id = raw.get("event_id") if isinstance(raw, Mapping) else None
    event_id = raw_id if isinstance(raw_id, str) and raw_id else None
    try:
        return _parse_event(raw, wellbore_id, md_datum)
    except RecordError as err:
        return EventRejection(event_id, err.code, err.message)
    except (
        TypeError,
        KeyError,
        AttributeError,
        ValueError,
        ArithmeticError,
        OverflowError,
    ) as err:  # defensive: any other malformed value is an explicit per-event rejection
        return EventRejection(event_id, "malformed_event", f"malformed record: {err!r}")


def _parse_event(raw: Mapping[str, Any], wellbore_id: str, md_datum: str) -> PerforationEvent:
    if not isinstance(raw, Mapping):
        raise RecordError("malformed_event", "record must be a mapping")
    event_id = raw.get("event_id")
    if not isinstance(event_id, str) or not event_id:
        raise RecordError("malformed_event", "event_id is required")
    if raw.get("wellbore_id") != wellbore_id:
        raise RecordError(
            "wrong_wellbore", f"record targets {raw.get('wellbore_id')!r}, not {wellbore_id!r}"
        )
    code = raw.get("kind")
    if not isinstance(code, str) or not code:
        raise RecordError("malformed_event", "event code (kind) is required")
    kind = CODE_TO_KIND.get(code, EventKind.UNMAPPED)
    revision = raw.get("dataset_revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise RecordError("malformed_event", "dataset_revision must be an integer >= 1")
    effective = _parse_effective(raw)
    supersedes = raw.get("supersedes")
    if supersedes is not None and (not isinstance(supersedes, str) or not supersedes):
        raise RecordError("malformed_event", "supersedes must be an event id")
    recorded_at = raw.get("recorded_at")
    if recorded_at is not None:
        try:
            recorded_at = (
                recorded_at
                if isinstance(recorded_at, datetime)
                else datetime.fromisoformat(str(recorded_at))
            )
        except ValueError:
            raise RecordError("malformed_time", "recorded_at is not ISO-8601") from None
        if recorded_at.tzinfo is None:
            raise RecordError("missing_timezone", "recorded_at needs a UTC offset")
    locator = raw.get("source_locator")
    common: dict[str, Any] = {
        "event_id": event_id,
        "wellbore_id": wellbore_id,
        "kind": kind,
        "source_code": code,
        "effective": effective,
        "dataset_revision": revision,
        "supersedes": supersedes,
        "recorded_at": recorded_at,
        "source_locator": locator if isinstance(locator, str) else None,
    }
    if kind in DEPTH_KINDS:
        common["depth"] = parse_depth(raw.get("depth"), md_datum)
        if kind is EventKind.INTERVAL_FLOW:
            common["status"] = _parse_status(raw.get("status"))
    elif kind is EventKind.WELLBORE_STATUS:
        if raw.get("depth") is not None:
            raise RecordError(
                "scope_conflict", "wellbore status cannot carry an interval; use interval_flow"
            )
        common["status"] = _parse_status(raw.get("status"))
    elif kind is EventKind.BASELINE:
        if raw.get("status") is not None:
            common["status"] = _parse_status(raw["status"])
        intervals: list[BaselineInterval] = []
        for item in raw.get("baseline_intervals") or ():
            if not isinstance(item, Mapping):
                raise RecordError("malformed_event", "baseline interval must be a mapping")
            access = item.get("access", "unknown")
            try:
                parsed_access = Access(access)
            except ValueError:
                raise RecordError("malformed_event", f"unsupported access {access!r}") from None
            intervals.append(BaselineInterval(parse_depth(item, md_datum), parsed_access))
        common["baseline_intervals"] = tuple(intervals)
    elif kind is EventKind.UNMAPPED:
        if raw.get("depth") is not None:
            try:
                common["depth"] = parse_depth(raw["depth"], md_datum)
            except RecordError:
                common["depth"] = None  # scope unknown: blocks the whole wellbore
    return PerforationEvent(**common)

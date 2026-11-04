"""Chart assembly: lines (full-resolution samples + labels) -> validated ``ChartSpec``.

Axis rule: one y axis per unit. Series that state the same unit may share an axis; a series whose
unit is missing or mixed never shares an axis with another measure (no unit is assumed equal), so
different units/meanings are never drawn against one scale."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from fieldlens.contracts.charts import (
    MAX_SERIES_PER_CHART,
    AxisKind,
    AxisPosition,
    ChartAxis,
    ChartEmptyReason,
    ChartEmptyState,
    ChartKey,
    ChartKind,
    ChartSeries,
    ChartSeriesScope,
    ChartSpec,
    ChartWindow,
    ExcludedSeries,
)
from fieldlens.contracts.evidence import EvidenceLink
from fieldlens.contracts.series import SeriesUnitStatus

from . import numeric

X_AXIS_ID = "x"


@dataclass
class Line:
    series_key: str
    name: str
    axis_label: str
    unit: str | None
    unit_status: SeriesUnitStatus
    axis_group: str
    scope: ChartSeriesScope
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    summable: bool = False
    source_series_id: UUID | None = None
    revision: str | None = None
    evidence: list[EvidenceLink] = field(default_factory=list)
    stack_group: str | None = None
    kind: ChartKind | None = None
    time_axis: bool = True


def axis_group(measure: str, unit: str | None, status: SeriesUnitStatus, owner: str) -> str:
    """Series sharing a group share a y axis; only a stated, identical unit is shared."""
    if status is SeriesUnitStatus.STATED and unit:
        return f"unit:{unit}"
    return f"{status.value}:{measure}:{owner}"


def make_window(start: date | None, end: date | None) -> ChartWindow | None:
    if start is None and end is None:
        return None
    return ChartWindow(
        from_=start.isoformat() if start else None, to=end.isoformat() if end else None
    )


def digest(*parts: object) -> str:
    return hashlib.sha256(
        json.dumps(parts, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def build_chart(
    key: ChartKey,
    chart_id: str,
    title: str,
    kind: ChartKind,
    scope: ChartSeriesScope,
    lines: list[Line],
    *,
    window: ChartWindow | None,
    as_of: date | None,
    seed: str,
    notes: list[str] | None = None,
    excluded: list[ExcludedSeries] | None = None,
    empty_reason: ChartEmptyReason = ChartEmptyReason.NO_RECORDS,
    empty_message: str = "No records exist for this chart.",
    x_name: str = "Reporting date",
    x_kind: AxisKind = AxisKind.TIME,
    x_unit: str | None = None,
    evidence: list[EvidenceLink] | None = None,
) -> ChartSpec:
    excluded = list(excluded or [])
    kept: list[Line] = []
    for line in lines:
        if not bool(np.any(~np.isnan(line.y))):
            excluded.append(
                ExcludedSeries(
                    name=line.name,
                    source_series_id=line.source_series_id,
                    reason="no valid samples in the selected window (all missing)",
                )
            )
        else:
            kept.append(line)
    if len(kept) > MAX_SERIES_PER_CHART:
        for line in kept[MAX_SERIES_PER_CHART:]:
            excluded.append(
                ExcludedSeries(
                    name=line.name,
                    source_series_id=line.source_series_id,
                    reason=f"chart series limit of {MAX_SERIES_PER_CHART} reached",
                )
            )
        kept = kept[:MAX_SERIES_PER_CHART]
    if any(line.time_axis != (x_kind is AxisKind.TIME) for line in kept):
        raise ValueError("every line must match the declared x axis kind (ISO dates vs numbers)")
    cache_key = digest(
        chart_id, seed, as_of, window.model_dump() if window else None, [ln.revision for ln in kept]
    )
    base = {
        "chart_id": chart_id,
        "key": key,
        "title": title,
        "kind": kind,
        "scope": scope,
        "excluded_series": excluded,
        "window": window,
        "as_of": as_of,
        "cache_key": cache_key,
        "notes": list(notes or []),
        "evidence": (evidence or [])[:50],
    }
    if not kept:
        if lines:  # records exist but nothing is drawable in this window / as-of
            empty_reason = (
                ChartEmptyReason.AS_OF_BEFORE_DATA
                if empty_reason is ChartEmptyReason.AS_OF_BEFORE_DATA
                else ChartEmptyReason.NO_DATA_IN_WINDOW
            )
            empty_message = "No valid samples fall inside the selected window / as-of date."
        return ChartSpec(**base, empty=ChartEmptyState(reason=empty_reason, message=empty_message))
    axes = [
        ChartAxis(
            axis_id=X_AXIS_ID,
            name=x_name,
            kind=x_kind,
            position=AxisPosition.X,
            unit=x_unit,
            unit_status=SeriesUnitStatus.STATED,
        )
    ]
    group_ids: dict[str, str] = {}
    labels: dict[str, list[str]] = {}
    first: dict[str, Line] = {}
    for line in kept:
        if line.axis_group not in group_ids:
            group_ids[line.axis_group] = f"y{len(group_ids)}"
            first[line.axis_group] = line
            labels[line.axis_group] = []
        if line.axis_label not in labels[line.axis_group]:
            labels[line.axis_group].append(line.axis_label)
    positions = [AxisPosition.Y_LEFT, AxisPosition.Y_RIGHT]
    for group, axis_id in group_ids.items():
        line = first[group]
        idx = int(axis_id[1:])
        text = " / ".join(labels[group])
        if line.unit_status is SeriesUnitStatus.STATED and line.unit:
            text = f"{text} [{line.unit}]"
        elif line.unit_status is SeriesUnitStatus.MIXED:
            text = f"{text} (mixed units)"
        else:
            text = f"{text} (unit not stated)"
        axes.append(
            ChartAxis(
                axis_id=axis_id,
                name=text[:128],
                kind=AxisKind.VALUE,
                position=positions[idx] if idx < 2 else AxisPosition.Y_EXTRA,
                unit=line.unit,
                unit_status=line.unit_status,
            )
        )
    series: list[ChartSeries] = []
    for line in kept:
        points, info, gaps = numeric.display(line.x, line.y, time_axis=line.time_axis)
        series.append(
            ChartSeries(
                series_key=line.series_key,
                name=line.name[:256],
                kind=line.kind,
                axis_id=group_ids[line.axis_group],
                x_axis_id=X_AXIS_ID,
                unit=line.unit,
                unit_status=line.unit_status,
                scope=line.scope,
                points=points,
                gap_count=gaps,
                downsample=info,
                aggregates=numeric.aggregates(
                    line.x,
                    line.y,
                    unit=line.unit,
                    summable=line.summable,
                    time_axis=line.time_axis,
                ),
                source_series_id=line.source_series_id,
                series_revision=line.revision,
                stack_group=line.stack_group,
                evidence=line.evidence[:20],
            )
        )
    return ChartSpec(**base, axes=axes, series=series)

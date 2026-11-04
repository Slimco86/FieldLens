"""Wellbore log tracks (XC-1) and field stratigraphic correlation (XC-3).

Both charts are depth based, not time based: the date window and as-of date do not apply to them
and say so in a note. Nothing is invented or converted:

* ``log_tracks``: stored LAS curves linked to *this* wellbore, plotted against the stated depth
  index. Only an index named like measured depth (DEPT/DEPTH/MD/MDEPTH) is drawn as MD; a TVD/TVDSS
  index, an index without a stated unit or an index in another unit than the chart's is listed as
  excluded, never equated with MD or converted. Formation tops are MD reference lines taken from
  the formation pick read model; a top in another unit is not drawn and is counted in a note.
* ``stratigraphic_correlation``: top depth per surface per wellbore from the formation layer set,
  MD and TVD on separate, explicitly named axes. TVDSS is drawn only for a pick that states its
  datum. TVD picks that the formation read model blocks (unknown/differing vertical references
  across wellbores, TVD that conflicts with the trajectory) are listed as excluded, never mixed.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import text
from sqlalchemy.orm import Session

from fieldlens.context.formations import formation_layer_set
from fieldlens.contracts.charts import (
    MAX_SERIES_PER_CHART,
    AxisKind,
    AxisPosition,
    ChartAxis,
    ChartEmptyReason,
    ChartEmptyState,
    ChartKey,
    ChartKind,
    ChartPoint,
    ChartReferenceLine,
    ChartSeries,
    ChartSeriesScope,
    ChartSpec,
    DownsampleInfo,
    ExcludedSeries,
    SeriesAggregates,
)
from fieldlens.contracts.context_layers import (
    DatumStatus,
    DepthValue,
    FormationBlockReason,
    FormationLayerSet,
    FormationPick,
)
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import EvidenceLink
from fieldlens.contracts.series import SeriesUnitStatus
from fieldlens.series import codec

from .assemble import X_AXIS_ID, Line, axis_group, build_chart, digest
from .perforation import locator_link

MD_INDEX_NAMES = frozenset({"DEPT", "DEPTH", "MD", "MDEPTH"})
_METRES = frozenset({"m", "meter", "metre", "meters", "metres"})
_FEET = frozenset({"ft", "f", "feet", "foot"})
DEPTH_NOTE = (
    "Depth charts are not time based: the date window and as-of date do not apply. Display "
    "points are decimated for drawing only; aggregates are exact full-resolution."
)

_LOGS = text(
    """
    SELECT c.series_id, c.document_id, c.measure, c.description, c.unit, c.unit_status,
           c.data_sha256, c.evidence AS curve_evidence, c.values_data, c.record_ordinal,
           a.index_data, a.index_name, a.index_unit, a.index_type, a.well_name, a.wellbore_label,
           ru.source_revision_id
      FROM series_curve c
      JOIN series_axis a ON a.project_id = c.project_id AND a.axis_id = c.axis_id
      JOIN extraction_run ru ON ru.project_id = a.project_id AND ru.run_id = a.run_id
      JOIN record_wellbore_link lk
        ON lk.project_id = c.project_id AND lk.run_id = c.run_id AND lk.ordinal = c.record_ordinal
     WHERE c.project_id = :p AND a.kind = 'log' AND a.index_encoding = 'numeric'
       AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
       AND lk.wellbore_id = :w
     ORDER BY a.document_id, a.ordinal, c.column_ordinal
    """
)


@dataclass
class LogCurve:
    """One stored log curve with its depth index, as read (units exactly as stated)."""

    series_id: UUID
    document_id: UUID
    measure: str
    description: str | None
    unit: str | None
    status: SeriesUnitStatus
    sha: str
    evidence: list[EvidenceLink]
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    index_name: str
    index_unit: str | None
    index_type: str


def load_log_curves(session: Session, project_id: UUID, wellbore_id: UUID) -> list[LogCurve]:
    """Log curves linked to exactly this wellbore (no well-level or other-bore fallback)."""
    out: list[LogCurve] = []
    for r in session.execute(_LOGS, {"p": project_id, "w": wellbore_id}).all():
        x = codec.decode_f8(bytes(r.index_data)).copy()
        y = codec.decode_f8(bytes(r.values_data)).copy()
        if x.size != y.size:
            raise ContractError(
                ErrorCode.INTERNAL_ERROR, "stored series is inconsistent with its index", 500
            )
        raw = (r.curve_evidence or {}).get("curve_locator")
        link = (
            locator_link(dict(raw), r.document_id, r.source_revision_id, None)
            if isinstance(raw, dict)
            else None
        )
        out.append(
            LogCurve(
                series_id=r.series_id,
                document_id=r.document_id,
                measure=r.measure,
                description=r.description,
                unit=r.unit,
                status=SeriesUnitStatus(r.unit_status),
                sha=r.data_sha256,
                evidence=[link] if link else [],
                x=x,
                y=y,
                index_name=r.index_name,
                index_unit=(r.index_unit or "").strip() or None,
                index_type=r.index_type,
            )
        )
    return out


def log_revision(curves: list[LogCurve]) -> str:
    return digest(sorted((str(c.series_id), c.sha) for c in curves))


def _family(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.strip().casefold()
    if u in _METRES:
        return "m"
    if u in _FEET:
        return "ft"
    return u or None


def _name(curve: LogCurve) -> str:
    desc = (curve.description or "").strip()
    return f"{curve.measure} — {desc}" if desc and desc != curve.measure else curve.measure


def _excluded(curve: LogCurve, reason: str) -> ExcludedSeries:
    return ExcludedSeries(name=curve.measure, source_series_id=curve.series_id, reason=reason)


def build_log_tracks(
    curves: list[LogCurve],
    tops: list[FormationPick],
    *,
    scope: ChartSeriesScope,
    seed: str,
    tops_unavailable: str | None = None,
) -> ChartSpec:
    """Log curves vs MD for one wellbore, plus formation tops as MD reference lines."""
    excluded: list[ExcludedSeries] = []
    usable: list[LogCurve] = []
    for c in curves:
        if c.index_type != "depth":
            excluded.append(_excluded(c, f"index {c.index_name!r} is not a depth index"))
        elif c.index_name.strip().upper() not in MD_INDEX_NAMES:
            excluded.append(
                _excluded(
                    c,
                    f"depth index {c.index_name!r} is not measured depth; it is not equated "
                    "with MD or converted",
                )
            )
        elif c.index_unit is None:
            excluded.append(_excluded(c, "depth index unit not stated; none is assumed"))
        else:
            usable.append(c)
    counts = Counter(c.index_unit for c in usable)
    x_unit = min(counts, key=lambda u: (-counts[u], str(u))) if counts else None
    lines: list[Line] = []
    for c in usable:
        if c.index_unit != x_unit:
            excluded.append(
                _excluded(
                    c,
                    f"depth index unit {c.index_unit!r} differs from the chart's {x_unit!r}; "
                    "not converted",
                )
            )
            continue
        finite = np.isfinite(c.x)
        lines.append(
            Line(
                series_key=f"log:{c.measure}:{c.series_id}",
                name=_name(c)[:256],
                axis_label=c.measure,
                unit=c.unit,
                unit_status=c.status,
                axis_group=axis_group(c.measure, c.unit, c.status, str(c.document_id)),
                scope=scope,
                x=c.x[finite],
                y=c.y[finite],
                source_series_id=c.series_id,
                revision=c.sha,
                evidence=c.evidence,
                time_axis=False,
            )
        )
    notes = [
        DEPTH_NOTE,
        "A depth index named DEPT/DEPTH/MD is read as measured depth (LAS convention); "
        "TVD/TVDSS-indexed logs are not drawn here and MD is never equated with TVD.",
        "Curve values keep their stated units; curves with different units use separate axes "
        "and nothing is converted. Missing samples stay gaps.",
    ]
    if curves and not lines:
        message = (
            f"{len(curves)} log curve(s) exist for this wellbore but none can be drawn against "
            "MD; see the excluded series for the reasons."
        )
        reason = ChartEmptyReason.SOURCE_UNAVAILABLE
    else:
        message = (
            "No parsed log curves are associated with this wellbore "
            "(nothing is borrowed from another wellbore)."
        )
        reason = ChartEmptyReason.NO_RECORDS
    chart = build_chart(
        ChartKey.LOG_TRACKS,
        ChartKey.LOG_TRACKS.value,
        "Log curves vs measured depth",
        ChartKind.LOG_TRACK,
        scope,
        lines,
        window=None,
        as_of=None,
        seed=seed,
        notes=notes,
        excluded=excluded,
        empty_reason=reason,
        empty_message=message,
        x_name="Measured depth (MD)",
        x_kind=AxisKind.VALUE,
        x_unit=x_unit,
        evidence=[e for ln in lines for e in ln.evidence][:50],
    )
    if not chart.series:
        return chart
    refs: list[ChartReferenceLine] = []
    skipped = 0
    for p in tops:
        md = p.md
        if md is None or md.value is None or md.unit is None:
            skipped += 1
        elif _family(md.unit) != _family(x_unit):
            skipped += 1
        elif len(refs) < 200:
            refs.append(
                ChartReferenceLine(
                    label=f"{p.surface_name} top (formation pick, MD)"[:256],
                    axis_id=X_AXIS_ID,
                    value=md.value,
                    unit=x_unit,
                    surface_key=p.surface_key,
                    pick_id=p.pick_id,
                    evidence=p.evidence[:20],
                )
            )
    extra = list(chart.notes)
    if refs:
        extra.append(
            "Reference lines are formation tops at their stated MD from the formation picks."
        )
    if skipped:
        extra.append(
            f"{skipped} formation top(s) not drawn: no MD or an MD unit other than the chart's "
            f"{x_unit!r} (not converted)."
        )
    if tops_unavailable:
        extra.append(f"Formation tops unavailable: {tops_unavailable}")
    update = {"reference_lines": refs, "notes": extra}
    return ChartSpec.model_validate({**chart.model_dump(by_alias=True), **update})


# --- stratigraphic correlation -------------------------------------------------------------------

_BASIS_ORDER = {"md": 0, "tvd": 1, "tvdss": 2}
_BASIS_KIND = {"md": AxisKind.DEPTH_MD, "tvd": AxisKind.DEPTH_TVD, "tvdss": AxisKind.DEPTH_TVDSS}


def _aggregate(xs: list[float], ys: list[float], unit: str | None) -> SeriesAggregates:
    n = len(ys)
    return SeriesAggregates(
        count=n,
        valid_count=n,
        null_count=0,
        minimum=min(ys),
        maximum=max(ys),
        mean=min(max(math.fsum(ys) / n, min(ys)), max(ys)),
        first_valid_x=xs[0],
        last_valid_x=xs[-1],
        last_value=ys[-1],
        unit=unit,
    )


def _blocked_ids(layers: FormationLayerSet) -> dict[UUID, str]:
    """Pick ids whose TVD/TVDSS the formation read model will not compare, with its reason."""
    out: dict[UUID, str] = {}
    for b in layers.blocked:
        if b.reason in {FormationBlockReason.UNKNOWN_DATUM, FormationBlockReason.DATUM_MISMATCH}:
            for pid in b.pick_ids:
                out.setdefault(pid, b.message)
    for c in layers.conflicts:
        if c.reason is FormationBlockReason.TVD_CONFLICT:
            out.setdefault(c.pick_id, c.message)
    for s in layers.surfaces:
        for b in s.blocked:
            if b.reason is FormationBlockReason.TVD_CONFLICT:
                for pid in b.pick_ids:
                    out.setdefault(pid, b.message)
    return out


def _depth_group(
    basis: str, value: DepthValue | None, layers: FormationLayerSet
) -> tuple[str, str, str | None] | None:
    if value is None or value.value is None or value.unit is None:
        return None
    datum: str | None = None
    if value.datum_status is DatumStatus.STATED and value.datum:
        datum = value.datum
    elif basis == "tvd" and layers.frame.vertical_reference:
        datum = layers.frame.vertical_reference  # shared reference stated by the trajectories
    return basis, value.unit, datum


def _axis_name(basis: str, unit: str, datum: str | None) -> str:
    if basis == "md":
        return f"Top depth, MD [{unit}] (along each wellbore; not comparable between wellbores)"
    label = basis.upper()
    ref = f"reference: {datum}" if datum else "reference not stated"
    return f"Top depth, {label} [{unit}] ({ref})"


def build_stratigraphic_correlation(
    layers: FormationLayerSet,
    names: dict[UUID, tuple[str, str | None]],
    *,
    scope: ChartSeriesScope,
    seed: str,
) -> ChartSpec:
    """Top depth per surface per wellbore; MD and TVD explicit, no silent datum mixing."""
    chart_id = ChartKey.STRATIGRAPHIC_CORRELATION.value
    base = {
        "chart_id": chart_id,
        "key": ChartKey.STRATIGRAPHIC_CORRELATION,
        "title": "Stratigraphic correlation (top depth per surface per wellbore)",
        "kind": ChartKind.CORRELATION,
        "scope": scope,
        "cache_key": digest(chart_id, seed, layers.generated_from_revision),
    }
    notes = [
        "Depth charts are not time based: the date window and as-of date do not apply.",
        "Each series is one surface; x is the wellbore position (see the position notes) and y "
        "the top depth. MD (along the wellbore) and TVD are separate axes and never equated.",
    ]
    picks = [(s, p) for s in layers.surfaces for p in s.picks]
    if not picks:
        if layers.unsupported:
            return ChartSpec(
                **base,
                notes=notes,
                empty=ChartEmptyState(
                    reason=ChartEmptyReason.SOURCE_UNAVAILABLE,
                    message=(
                        f"{len(layers.unsupported)} formation pick(s) exist but none can be "
                        "drawn (no usable depth, qualifier, or no trajectory)."
                    ),
                ),
            )
        return ChartSpec(
            **base,
            notes=notes,
            empty=ChartEmptyState(
                reason=ChartEmptyReason.NO_RECORDS,
                message=layers.empty_reason or "No formation picks exist in this project.",
            ),
        )
    bore_ids = sorted(
        {p.wellbore_id for _, p in picks},
        key=lambda w: ((names.get(w) or ("", None))[0].casefold(), str(w)),
    )
    position = {w: float(i + 1) for i, w in enumerate(bore_ids)}
    label = {w: (names.get(w) or (str(w), None))[0] for w in bore_ids}
    notes.append(
        "Wellbore positions: " + "; ".join(f"{int(position[w])} = {label[w]}" for w in bore_ids)
    )
    blocked = _blocked_ids(layers)
    excluded: list[ExcludedSeries] = []
    groups: dict[tuple[str, str, str, str | None], list[tuple[float, float, FormationPick]]] = (
        defaultdict(list)
    )
    surface_names: dict[str, str] = {}
    withheld_tvdss = 0
    for surface, p in picks:
        surface_names.setdefault(surface.surface_key, surface.name)
        x = position[p.wellbore_id]
        md = _depth_group("md", p.md, layers)
        if md is not None and p.md is not None and p.md.value is not None:
            groups[(surface.surface_key, *md)].append((x, p.md.value, p))
        for basis, value in (("tvd", p.tvd), ("tvdss", p.tvdss)):
            grp = _depth_group(basis, value, layers)
            if grp is None or value is None or value.value is None:
                continue
            if p.pick_id in blocked:
                excluded.append(
                    ExcludedSeries(
                        name=f"{surface.name} — {label[p.wellbore_id]} ({basis.upper()})",
                        reason=blocked[p.pick_id],
                    )
                )
            elif basis == "tvdss" and grp[2] is None:
                withheld_tvdss += 1  # TVDSS only with a stated datum
            else:
                groups[(surface.surface_key, *grp)].append((x, value.value, p))
    if withheld_tvdss:
        notes.append(
            f"{withheld_tvdss} TVDSS value(s) not drawn: the pick states no datum, so TVD with its "
            "stated reference is shown instead."
        )
    if any(g[1] == "tvd" for g in groups) and layers.frame.vertical_reference is None:
        notes.append(
            "TVD vertical reference is not stated for all wellbores; TVD values are drawn per "
            "wellbore only where the formation read model does not block them."
        )
    if layers.unsupported:
        notes.append(
            f"{len(layers.unsupported)} formation pick(s) not drawn (listed with a reason in the "
            "formation layer)."
        )
    axis_keys = sorted(
        {k[1:] for k in groups}, key=lambda k: (_BASIS_ORDER[k[0]], k[1].casefold(), k[2] or "")
    )
    positions = [AxisPosition.Y_LEFT, AxisPosition.Y_RIGHT]
    axes = [
        ChartAxis(
            axis_id=X_AXIS_ID,
            name="Wellbore (position index; see notes)",
            kind=AxisKind.CATEGORY,
            position=AxisPosition.X,
        )
    ]
    axis_id: dict[tuple[str, str, str | None], str] = {}
    for i, (basis, unit, datum) in enumerate(axis_keys):
        axis_id[(basis, unit, datum)] = f"y{i}"
        axes.append(
            ChartAxis(
                axis_id=f"y{i}",
                name=_axis_name(basis, unit, datum)[:128],
                kind=_BASIS_KIND[basis],
                position=positions[i] if i < 2 else AxisPosition.Y_EXTRA,
                unit=unit,
                datum=datum,
                inverted=True,
            )
        )
    series: list[ChartSeries] = []
    for key in sorted(
        groups, key=lambda k: (surface_names[k[0]].casefold(), _BASIS_ORDER[k[1]], k[2], k[3] or "")
    ):
        skey, basis, unit, datum = key
        rows = sorted(groups[key], key=lambda t: (t[0], t[1], str(t[2].pick_id)))
        if len(series) >= MAX_SERIES_PER_CHART:
            excluded.append(
                ExcludedSeries(
                    name=f"{surface_names[skey]} ({basis.upper()})",
                    reason=f"chart series limit of {MAX_SERIES_PER_CHART} reached",
                )
            )
            continue
        xs = [r[0] for r in rows]
        ys = [r[1] for r in rows]
        series.append(
            ChartSeries(
                series_key=f"strat:{skey}:{basis}:{unit}:{datum or ''}",
                name=f"{surface_names[skey]} top — {basis.upper()}"[:256],
                kind=ChartKind.CORRELATION,
                axis_id=axis_id[(basis, unit, datum)],
                x_axis_id=X_AXIS_ID,
                unit=unit,
                unit_status=SeriesUnitStatus.STATED,
                scope=scope,
                points=[ChartPoint(x=x, y=y) for x, y in zip(xs, ys, strict=True)],
                gap_count=0,
                downsample=DownsampleInfo(
                    applied=False, source_points=len(ys), returned_points=len(ys)
                ),
                aggregates=_aggregate(xs, ys, unit),
                evidence=[e for r in rows for e in r[2].evidence][:20],
            )
        )
    return ChartSpec(
        **base,
        axes=axes,
        series=series,
        excluded_series=excluded,
        notes=notes,
        evidence=[e for s in series for e in s.evidence][:50],
    )


def formation_tops(
    session: Session, project_id: UUID, wellbore_id: UUID
) -> tuple[FormationLayerSet | None, str | None]:
    """Placed formation picks of one wellbore, or the reason they are unavailable."""
    try:
        return formation_layer_set(session, project_id, wellbore_id), None
    except ContractError as exc:
        return None, exc.message


def field_layers(session: Session, project_id: UUID) -> tuple[FormationLayerSet | None, str | None]:
    try:
        return formation_layer_set(session, project_id, None), None
    except ContractError as exc:
        return None, exc.message


def unavailable_correlation(scope: ChartSeriesScope, seed: str, reason: str) -> ChartSpec:
    key = ChartKey.STRATIGRAPHIC_CORRELATION
    return ChartSpec(
        chart_id=key.value,
        key=key,
        title="Stratigraphic correlation (top depth per surface per wellbore)",
        kind=ChartKind.CORRELATION,
        scope=scope,
        cache_key=digest(key.value, seed, "unavailable"),
        empty=ChartEmptyState(
            reason=ChartEmptyReason.SOURCE_UNAVAILABLE,
            message=f"Formation picks could not be read: {reason}",
        ),
    )


__all__ = [
    "LogCurve",
    "build_log_tracks",
    "build_stratigraphic_correlation",
    "field_layers",
    "formation_tops",
    "load_log_curves",
    "log_revision",
    "unavailable_correlation",
]

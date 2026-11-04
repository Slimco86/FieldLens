"""Read-only chart service: wellbore chart set and field chart set (XC-1..4).

Everything is computed from the stored full-resolution samples of the project's *current*
extraction runs (superseded / failed runs expose nothing). Display points are decimated to at most
``MAX_DISPLAY_POINTS`` per series; aggregates are exact over the full-resolution window. Nothing is
cached or written; the response carries the as-of date and a cache key over inputs and revisions."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import ARRAY, Text, bindparam, text
from sqlalchemy.orm import Session

from fieldlens.contracts.charts import (
    ChartEmptyReason,
    ChartKey,
    ChartKind,
    ChartScope,
    ChartSeriesScope,
    ChartSpec,
    ExcludedSeries,
    FieldChartSet,
    WellboreChartSet,
)
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import EvidenceLink
from fieldlens.contracts.series import SeriesUnitStatus
from fieldlens.series import codec

from . import numeric
from .assemble import Line, axis_group, build_chart, digest, make_window
from .perforation import PerfResult, PerfRow, build, locator_link

ENDPOINT_NOTE = (
    "Display points are decimated for drawing only; aggregates are exact full-resolution."
)
UNIT_NOTE = (
    "Daily production sheets state no unit; none is assumed, so axes are labeled "
    "'unit not stated' and series are never merged across different measures."
)

RATE_MEASURES = (
    ("bore_oil_vol", "Oil volume", "oil"),
    ("bore_gas_vol", "Gas volume", "gas"),
    ("bore_wat_vol", "Water produced", "water"),
    ("bore_wi_vol", "Water injected", "water_injection"),
)
PRESSURE_MEASURES = (
    ("avg_downhole_pressure", "Downhole pressure"),
    ("avg_downhole_temperature", "Downhole temperature"),
)
TUBING_MEASURES = (
    ("avg_dp_tubing", "Differential pressure, tubing"),
    ("avg_annulus_press", "Annulus pressure"),
)
HOURS = ("on_stream_hrs", "On-stream hours")
LABELS: dict[str, str] = {
    **{m: label for m, label, _ in RATE_MEASURES},
    **dict(PRESSURE_MEASURES),
    **dict(TUBING_MEASURES),
    HOURS[0]: HOURS[1],
}
ALL_MEASURES = sorted(LABELS)

_SERIES = text(
    """
    SELECT c.series_id, c.document_id, c.measure, c.unit, c.unit_status, c.data_sha256,
           c.evidence AS curve_evidence, c.values_data, a.index_data, a.well_name,
           a.wellbore_label, ru.source_revision_id, lk.wellbore_id
      FROM series_curve c
      JOIN series_axis a ON a.project_id = c.project_id AND a.axis_id = c.axis_id
      JOIN extraction_run ru ON ru.project_id = a.project_id AND ru.run_id = a.run_id
      LEFT JOIN record_wellbore_link lk
        ON lk.project_id = c.project_id AND lk.run_id = c.run_id AND lk.ordinal = c.record_ordinal
     WHERE c.project_id = :p AND a.kind = 'production' AND a.index_encoding = 'epoch_days'
       AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
       AND c.measure = ANY(:measures)
       AND (CAST(:w AS uuid) IS NULL OR lk.wellbore_id = :w
            OR (lk.wellbore_id IS NULL AND CAST(:wk AS text) IS NOT NULL
                AND a.subject->>'well_key' = :wk))
     ORDER BY a.document_id, a.ordinal, c.column_ordinal
    """
).bindparams(bindparam("measures", type_=ARRAY(Text())))

_PERF = text(
    """
    SELECT er.record_id, er.document_id, er.ordinal, er.locator, er.effective_time,
           er.validation_state, er.attributes, ru.source_revision_id, lk.wellbore_id
      FROM record_wellbore_link lk
      JOIN extracted_record er ON er.run_id = lk.run_id AND er.ordinal = lk.ordinal
      JOIN extraction_run ru ON ru.run_id = er.run_id AND ru.project_id = lk.project_id
     WHERE lk.project_id = :p AND er.project_id = :p AND er.kind = 'perforation_interval'
       AND NOT ru.superseded AND ru.status IN ('succeeded', 'partial')
       AND (CAST(:w AS uuid) IS NULL OR lk.wellbore_id = :w)
     ORDER BY er.run_id, er.ordinal
    """
)


@dataclass
class Loaded:
    series_id: UUID
    document_id: UUID
    measure: str
    unit: str | None
    status: SeriesUnitStatus
    sha: str
    evidence: list[EvidenceLink]
    x: NDArray[np.float64]
    y: NDArray[np.float64]
    wellbore_id: UUID | None
    well_name: str | None
    wellbore_label: str | None


def _evidence(raw: dict[str, Any], document_id: UUID, revision_id: UUID) -> list[EvidenceLink]:
    if raw.get("kind") != "xlsx" or not raw.get("sheet") or not raw.get("cell_range"):
        return []
    link = locator_link(
        {"kind": "xlsx", "sheet": raw["sheet"], "cell_range": raw["cell_range"]},
        document_id,
        revision_id,
        None,
    )
    return [link] if link else []


def _load_series(
    session: Session, project_id: UUID, wellbore_id: UUID | None, well_key: str | None
) -> list[Loaded]:
    out: list[Loaded] = []
    rows = session.execute(
        _SERIES,
        {"p": project_id, "measures": ALL_MEASURES, "w": wellbore_id, "wk": well_key},
    ).all()
    for r in rows:
        x = codec.decode_f8(bytes(r.index_data)).copy()
        y = codec.decode_f8(bytes(r.values_data)).copy()
        if x.size != y.size:
            raise ContractError(
                ErrorCode.INTERNAL_ERROR, "stored series is inconsistent with its index", 500
            )
        out.append(
            Loaded(
                r.series_id,
                r.document_id,
                r.measure,
                r.unit,
                SeriesUnitStatus(r.unit_status),
                r.data_sha256,
                _evidence(r.curve_evidence or {}, r.document_id, r.source_revision_id),
                x,
                y,
                r.wellbore_id,
                r.well_name,
                r.wellbore_label,
            )
        )
    return out


def _perf_rows(
    session: Session, project_id: UUID, wellbore_id: UUID | None
) -> dict[UUID, list[PerfRow]]:
    out: dict[UUID, list[PerfRow]] = defaultdict(list)
    for r in session.execute(_PERF, {"p": project_id, "w": wellbore_id}).all():
        attrs = {a.get("key"): a for a in (r.attributes or []) if isinstance(a, dict)}

        def depth(key: str, attrs: dict[Any, Any] = attrs) -> tuple[float | None, str | None, bool]:
            a = attrs.get(f"perforation.{key}")
            if not a or a.get("number") is None:
                return None, None, False
            unit = a.get("unit")
            if unit:
                return float(a["number"]), str(unit), False
            if a.get("normalized_unit") == "m":
                return float(a["number"]), "m", True
            return float(a["number"]), None, False

        top, unit, defaulted = depth("top_md")
        base, base_unit, base_defaulted = depth("base_md")
        if unit != base_unit and top is not None and base is not None:
            top = None  # conflicting interval units: unusable, listed with a reason
        eff = r.effective_time or {}
        parts = []
        for key in ("formation", "perf_type", "current_status", "remark"):
            a = attrs.get(f"perforation.{key}")
            if a and (a.get("text") or a.get("original_text")):
                parts.append(f"{key}: {a.get('text') or a.get('original_text')}")
        out[r.wellbore_id].append(
            PerfRow(
                record_id=r.record_id,
                ordinal=r.ordinal,
                top=top,
                base=base,
                unit=unit,
                unit_defaulted=defaulted or base_defaulted,
                literal=eff.get("literal"),
                precision=eff.get("precision"),
                timezone_known=bool(eff.get("timezone_known") or eff.get("timezone")),
                description="; ".join(parts)[:500] or None,
                validation_state=r.validation_state,
                evidence=locator_link(
                    dict(r.locator or {}), r.document_id, r.source_revision_id, r.record_id
                ),
            )
        )
    return out


def _parse_day(raw: str | None, name: str) -> date | None:
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ContractError(
            ErrorCode.VALIDATION_ERROR, f"{name} must be an ISO date (YYYY-MM-DD)"
        ) from exc


@dataclass
class _Range:
    lo: date | None
    hi: date | None  # window end
    as_of: date | None

    @property
    def lo_x(self) -> float:
        return numeric.epoch_day(self.lo) if self.lo else -np.inf

    @property
    def hi_x(self) -> float:
        end = [d for d in (self.hi, self.as_of) if d is not None]
        return numeric.epoch_day(min(end)) if end else np.inf


def _range(from_: str | None, to: str | None, as_of: str | None) -> _Range:
    lo, hi, asof = _parse_day(from_, "from"), _parse_day(to, "to"), _parse_day(as_of, "as_of")
    if lo is not None and hi is not None and lo > hi:
        raise ContractError(ErrorCode.VALIDATION_ERROR, "from must not be after to")
    return _Range(lo, hi, asof)


def _prefix(row: Loaded, rng: _Range) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    keep = row.x <= rng.hi_x
    return row.x[keep], row.y[keep]


def _from_lo(
    x: NDArray[np.float64], y: NDArray[np.float64], rng: _Range
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    keep = x >= rng.lo_x
    return x[keep], y[keep]


def _scope_bore(wellbore_id: UUID, label: str, well: str | None) -> ChartSeriesScope:
    return ChartSeriesScope(
        scope=ChartScope.WELLBORE,
        scope_label="wellbore-level",
        wellbore_id=wellbore_id,
        wellbore_label=label,
        well_name=well,
    )


def _scope_well(well: str | None) -> ChartSeriesScope:
    return ChartSeriesScope(
        scope=ChartScope.WELL,
        scope_label="well-level (not attributed to a wellbore)",
        well_name=well,
    )


def _line(
    row: Loaded,
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    scope: ChartSeriesScope,
    *,
    name: str | None = None,
    summable: bool = False,
    suffix: str = "",
    key_prefix: str = "",
    stack: str | None = None,
    kind: ChartKind | None = None,
    derived: bool = False,
) -> Line:
    label = LABELS[row.measure]
    owner = str(row.document_id)
    bore = f" — {scope.wellbore_label}" if scope.wellbore_label else f" ({scope.scope_label})"
    return Line(
        series_key=f"{key_prefix}{row.measure}:{row.series_id}",
        name=name or f"{label}{suffix}{bore}",
        axis_label=label,
        unit=row.unit,
        unit_status=row.status,
        axis_group=axis_group(
            row.measure + (":cum" if derived else ""), row.unit, row.status, owner
        ),
        scope=scope,
        x=x,
        y=y,
        summable=summable,
        source_series_id=row.series_id,
        revision=row.sha,
        evidence=row.evidence,
        stack_group=stack,
        kind=kind,
    )


def _revision(rows: list[Loaded], perf: dict[UUID, PerfResult]) -> str:
    return digest(
        sorted((str(r.series_id), r.sha) for r in rows),
        sorted((str(k), v.history.revision) for k, v in perf.items()),
    )


# --- wellbore chart set -------------------------------------------------------------------------


class ChartService:
    def wellbore_charts(
        self,
        session: Session,
        project_id: UUID,
        wellbore_id: UUID,
        *,
        as_of: str | None = None,
        from_: str | None = None,
        to: str | None = None,
    ) -> WellboreChartSet:
        rng = _range(from_, to, as_of)
        bore = session.execute(
            text(
                "SELECT w.name AS bore, g.name AS well, g.well_key FROM wellbore w "
                "JOIN well g ON g.project_id = w.project_id AND g.well_id = w.well_id "
                "WHERE w.project_id = :p AND w.wellbore_id = :w"
            ),
            {"p": project_id, "w": wellbore_id},
        ).first()
        if bore is None:
            raise ContractError(ErrorCode.NOT_FOUND, "wellbore not found", 404)
        rows = _load_series(session, project_id, wellbore_id, bore.well_key)
        linked = [r for r in rows if r.wellbore_id == wellbore_id]
        unlinked = [r for r in rows if r.wellbore_id is None]
        well_level = [r for r in unlinked if not r.wellbore_label]
        ambiguous = [r for r in unlinked if r.wellbore_label]
        ambiguities = sorted(
            {
                f"Series labeled {r.wellbore_label!r} of well {bore.well} could not be associated "
                f"with a single wellbore; it is not shown on any wellbore chart."
                for r in ambiguous
            }
        )
        perf = build(
            wellbore_id,
            _perf_rows(session, project_id, wellbore_id).get(wellbore_id, []),
            rng.as_of,
        )
        window = make_window(rng.lo, rng.hi)
        revision = _revision(rows, {wellbore_id: perf})
        seed = digest("wellbore", project_id, wellbore_id, revision)
        scope = _scope_bore(wellbore_id, bore.bore, bore.well)
        charts = self._production_charts(linked, scope, ":bore", rng, window, seed, bore.bore)
        if well_level:
            wscope = _scope_well(bore.well)
            charts += [
                c
                for c in self._production_charts(
                    well_level, wscope, ":well", rng, window, seed, bore.bore
                )
                if c.series
            ]
        charts += self._perforation_charts(perf, scope, rng, window, seed)
        for key, title, message in (
            (ChartKey.PRESSURE_TESTS, "Pressure tests", "No pressure-test records exist"),
            (ChartKey.LAB_TESTS, "Lab tests", "No lab-test records exist"),
        ):
            charts.append(
                build_chart(
                    key,
                    key.value,
                    title,
                    ChartKind.TIMELINE,
                    scope,
                    [],
                    window=window,
                    as_of=rng.as_of,
                    seed=seed,
                    empty_reason=ChartEmptyReason.NO_RECORDS,
                    empty_message=f"{message}: no parser produces them yet (owner decision D2).",
                )
            )
        return WellboreChartSet(
            project_id=project_id,
            wellbore_id=wellbore_id,
            wellbore_label=bore.bore,
            well_name=bore.well,
            as_of=rng.as_of,
            window=window,
            charts=charts,
            perforation_history=perf.history,
            ambiguities=ambiguities,
            generated_from_revision=revision,
            cache_key=digest(seed, rng.as_of, window.model_dump() if window else None),
        )

    def _production_charts(
        self,
        rows: list[Loaded],
        scope: ChartSeriesScope,
        tag: str,
        rng: _Range,
        window: Any,
        seed: str,
        bore: str,
    ) -> list[ChartSpec]:
        level = "wellbore" if scope.scope is ChartScope.WELLBORE else "well"
        none_msg = (
            f"No daily production records are associated with this {level} "
            "(nothing is borrowed from another wellbore)."
        )
        before_data = bool(
            rng.as_of is not None and rows and all(bool(np.all(r.x > rng.hi_x)) for r in rows)
        )
        reason = ChartEmptyReason.AS_OF_BEFORE_DATA if before_data else ChartEmptyReason.NO_RECORDS
        suffix = "" if tag == ":bore" else tag
        notes = [UNIT_NOTE, ENDPOINT_NOTE]
        sub = f" — {level}-level"

        def by(measures: tuple[str, ...]) -> list[Loaded]:
            return [r for r in rows if r.measure in measures]

        def plain(measures: tuple[str, ...], summable: bool, **kw: Any) -> list[Line]:
            lines: list[Line] = []
            for row in by(measures):
                x, y = _from_lo(*_prefix(row, rng), rng)
                lines.append(_line(row, x, y, scope, summable=summable, **kw))
            return lines

        def make(
            key: ChartKey,
            title: str,
            kind: ChartKind,
            lines: list[Line],
            extra: list[str] | None = None,
            excluded: list[ExcludedSeries] | None = None,
        ) -> ChartSpec:
            return build_chart(
                key,
                key.value + suffix,
                title + (sub if suffix else ""),
                kind,
                scope,
                lines,
                window=window,
                as_of=rng.as_of,
                seed=seed,
                notes=notes + (extra or []),
                excluded=excluded,
                empty_reason=reason,
                empty_message=none_msg,
                evidence=[e for ln in lines for e in ln.evidence][:50],
            )

        rate_keys = tuple(m for m, _, _ in RATE_MEASURES)
        cum_lines: list[Line] = []
        cum_excluded: list[ExcludedSeries] = []
        for row in by(rate_keys):
            if numeric.has_repeated(row.x):
                cum_excluded.append(
                    ExcludedSeries(
                        name=f"{LABELS[row.measure]} — {bore}",
                        source_series_id=row.series_id,
                        reason="repeated reporting dates: a running total would double count",
                    )
                )
                continue
            px, py = _prefix(row, rng)
            x, y = _from_lo(px, numeric.cumulative(py), rng)
            cum_lines.append(
                _line(
                    row,
                    x,
                    y,
                    scope,
                    suffix=" (cumulative)",
                    key_prefix="cum:",
                    derived=True,
                )
            )
        return [
            make(
                ChartKey.PRODUCTION_RATES,
                "Daily production / injection volumes",
                ChartKind.LINE,
                plain(rate_keys, True),
            ),
            make(
                ChartKey.CUMULATIVE_VOLUMES,
                "Cumulative volumes",
                ChartKind.LINE,
                cum_lines,
                ["Running total of reported days from the first record; missing days stay gaps."],
                cum_excluded,
            ),
            make(
                ChartKey.DOWNHOLE_PRESSURE_TEMPERATURE,
                "Downhole pressure and temperature",
                ChartKind.LINE,
                plain(tuple(m for m, _ in PRESSURE_MEASURES), False),
            ),
            make(
                ChartKey.TUBING_ANNULUS_PRESSURE,
                "Tubing and annulus pressure",
                ChartKind.LINE,
                plain(tuple(m for m, _ in TUBING_MEASURES), False),
            ),
            make(ChartKey.ON_STREAM_HOURS, HOURS[1], ChartKind.BAR, plain((HOURS[0],), True)),
        ]

    def _perforation_charts(
        self, perf: PerfResult, scope: ChartSeriesScope, rng: _Range, window: Any, seed: str
    ) -> list[ChartSpec]:
        hist = perf.history
        notes = [*perf.notes, ENDPOINT_NOTE]
        unit_note = "m"
        status = SeriesUnitStatus.STATED
        dated = [e for e in hist.events if e.effective_time_unknown_reason is None]
        steps = perf.steps
        empty_reason = hist.empty.reason if hist.empty else ChartEmptyReason.NO_RECORDS
        empty_message = hist.empty.message if hist.empty else "No dated perforation events."
        ev_lines: list[Line] = []
        if dated:
            x = np.array(
                [
                    numeric.epoch_day(e.effective_date or e.effective_at.date())  # type: ignore[union-attr]
                    for e in dated
                ]
            )
            y = np.array([(e.base_md or np.nan) - (e.top_md or np.nan) for e in dated])
            ev_lines.append(
                Line(
                    series_key="perforation-events",
                    name="Perforated interval length per event (event date)",
                    axis_label="Interval length",
                    unit=unit_note,
                    unit_status=status,
                    axis_group=f"unit:{unit_note}",
                    scope=scope,
                    x=x,
                    y=y.astype(np.float64),
                    revision=hist.revision,
                    evidence=perf.evidence,
                    kind=ChartKind.TIMELINE,
                )
            )
        step_lines: list[Line] = []
        if steps:
            sx = np.array([numeric.epoch_day(date.fromisoformat(s.key[:10])) for s in steps])
            total = np.array([np.nan if s.total is None else s.total for s in steps])
            opened = np.array([np.nan if s.open is None else s.open for s in steps])
            for series_key, name, vals in (
                ("perforated-length-total", "Perforated length (union of MD intervals)", total),
                ("perforated-length-open", "Open perforated length", opened),
            ):
                if series_key.endswith("open") and not bool(np.any(~np.isnan(vals))):
                    notes.append(
                        "Open length is not shown: the source gives no open/isolated state."
                    )
                    continue
                step_lines.append(
                    Line(
                        series_key=series_key,
                        name=name,
                        axis_label="Perforated length",
                        unit=unit_note,
                        unit_status=status,
                        axis_group=f"unit:{unit_note}",
                        scope=scope,
                        x=sx,
                        y=vals.astype(np.float64),
                        revision=hist.revision,
                        evidence=perf.evidence,
                        kind=ChartKind.STEP,
                    )
                )
        common: dict[str, Any] = {
            "window": window,
            "as_of": rng.as_of,
            "seed": seed,
            "empty_reason": empty_reason,
            "empty_message": empty_message,
            "evidence": perf.evidence,
            "x_name": "Event date",
        }
        return [
            build_chart(
                ChartKey.PERFORATION_TIMELINE,
                ChartKey.PERFORATION_TIMELINE.value,
                "Perforation events",
                ChartKind.TIMELINE,
                scope,
                ev_lines,
                notes=notes,
                **common,
            ),
            build_chart(
                ChartKey.PERFORATED_LENGTH,
                ChartKey.PERFORATED_LENGTH.value,
                "Perforated length over time",
                ChartKind.STEP,
                scope,
                step_lines,
                notes=notes,
                **common,
            ),
        ]

    # --- field chart set ------------------------------------------------------------------------

    def field_charts(
        self,
        session: Session,
        project_id: UUID,
        *,
        as_of: str | None = None,
        from_: str | None = None,
        to: str | None = None,
    ) -> FieldChartSet:
        rng = _range(from_, to, as_of)
        if (
            session.execute(
                text("SELECT 1 FROM project WHERE project_id = :p"), {"p": project_id}
            ).first()
            is None
        ):
            raise ContractError(ErrorCode.NOT_FOUND, "project not found", 404)
        rows = _load_series(session, project_id, None, None)
        names = {
            r.wellbore_id: (r.name, r.well)
            for r in session.execute(
                text(
                    "SELECT w.wellbore_id, w.name, g.name AS well FROM wellbore w "
                    "JOIN well g ON g.project_id = w.project_id AND g.well_id = w.well_id "
                    "WHERE w.project_id = :p"
                ),
                {"p": project_id},
            ).all()
        }
        published = session.execute(
            text(
                "SELECT 1 FROM project p JOIN model_revision r ON r.project_id = p.project_id "
                "AND r.revision_id = p.active_model_revision_id "
                "WHERE p.project_id = :p AND r.status = 'published'"
            ),
            {"p": project_id},
        ).first()
        perf_by_bore = _perf_rows(session, project_id, None)
        perf = {
            wid: build(wid, prows, rng.as_of, label="wellbore")
            for wid, prows in sorted(perf_by_bore.items(), key=lambda kv: str(kv[0]))
        }
        window = make_window(rng.lo, rng.hi)
        revision = _revision(rows, perf)
        seed = digest("field", project_id, revision)
        field_scope = ChartSeriesScope(
            scope=ChartScope.FIELD, scope_label="field (all wellbores in project)"
        )
        excluded: list[ExcludedSeries] = []
        linked = [r for r in rows if r.wellbore_id is not None and r.wellbore_id in names]
        for r in rows:
            if r not in linked:
                excluded.append(
                    ExcludedSeries(
                        name=f"{LABELS[r.measure]} — {r.wellbore_label or r.well_name or 'unlabeled'}",
                        source_series_id=r.series_id,
                        reason="not associated with a known wellbore (unreconciled); not summed",
                    )
                )
        linked.sort(key=lambda r: (names[r.wellbore_id][0], str(r.series_id)))

        def scope_of(r: Loaded) -> ChartSeriesScope:
            assert r.wellbore_id is not None
            nm, well = names[r.wellbore_id]
            return _scope_bore(r.wellbore_id, nm, well)

        notes = [UNIT_NOTE, ENDPOINT_NOTE]

        def make(
            key: ChartKey,
            title: str,
            kind: ChartKind,
            lines: list[Line],
            extra: list[str] | None = None,
            ex: list[ExcludedSeries] | None = None,
            empty_message: str = "No daily production records exist in this project.",
        ) -> ChartSpec:
            chart = build_chart(
                key,
                key.value,
                title,
                kind,
                field_scope,
                lines,
                window=window,
                as_of=rng.as_of,
                seed=seed,
                notes=notes + (extra or []),
                excluded=ex,
                empty_message=empty_message,
                evidence=[e for ln in lines for e in ln.evidence][:50],
            )
            excluded.extend(chart.excluded_series)
            return chart

        def per_bore(
            measures: tuple[str, ...], *, cum: bool = False, stack: bool = False, **kw: Any
        ) -> tuple[list[Line], list[ExcludedSeries]]:
            lines: list[Line] = []
            ex: list[ExcludedSeries] = []
            for r in linked:
                if r.measure not in measures:
                    continue
                if cum and numeric.has_repeated(r.x):
                    ex.append(
                        ExcludedSeries(
                            name=f"{LABELS[r.measure]} — {scope_of(r).wellbore_label}",
                            source_series_id=r.series_id,
                            reason="repeated reporting dates: a running total would double count",
                        )
                    )
                    continue
                px, py = _prefix(r, rng)
                x, y = _from_lo(px, numeric.cumulative(py) if cum else py, rng)
                group = axis_group(
                    r.measure + (":cum" if cum else ""), r.unit, r.status, str(r.document_id)
                )
                lines.append(
                    _line(
                        r,
                        x,
                        y,
                        scope_of(r),
                        suffix=" (cumulative)" if cum else "",
                        key_prefix="cum:" if cum else "",
                        stack=group if stack else None,
                        derived=cum,
                        summable=bool(kw.get("summable", False)) and not cum,
                    )
                )
            return lines, ex

        rate_keys = tuple(m for m, _, _ in RATE_MEASURES)
        totals, total_ex = self._totals(linked, rate_keys, rng, field_scope)
        oil = ("bore_oil_vol",)
        by_rate, ex1 = per_bore(oil, stack=True, summable=True)
        by_cum, ex2 = per_bore(oil, cum=True)
        pressure, ex3 = per_bore(("avg_downhole_pressure",))
        uptime, ex4 = per_bore((HOURS[0],), summable=True)
        for ln in uptime:
            ln.kind = ChartKind.STRIP
        total_lines = [_clipped(t, rng) for t, _ in totals]
        cum_totals = [_derived_cumulative(t, rng) for t, _ in totals]
        charts = [
            make(
                ChartKey.FIELD_RATES_BY_WELLBORE,
                "Daily oil volume by wellbore (stacked)",
                ChartKind.STACKED_AREA,
                by_rate,
                ["Only oil is stacked here; other phases are in the totals chart."],
                ex1,
            ),
            make(
                ChartKey.FIELD_RATES_TOTAL,
                "Field daily volumes by phase (sum over wellbores)",
                ChartKind.LINE,
                total_lines,
                [
                    "Only series with the same stated unit (or the same unstated-unit workbook "
                    "column) are summed; a day with no value stays a gap.",
                    "A day total sums only the wellbores that reported a value that day.",
                ],
                total_ex,
            ),
            make(
                ChartKey.FIELD_CUMULATIVE_BY_WELLBORE,
                "Cumulative oil volume by wellbore",
                ChartKind.LINE,
                by_cum,
                None,
                ex2,
            ),
            make(
                ChartKey.PRODUCER_INJECTOR_VOLUMES,
                "Produced versus injected cumulative volumes (field)",
                ChartKind.LINE,
                cum_totals,
                [
                    "Produced and injected volumes are different meanings: they are shown as "
                    "separate series and never netted."
                ],
            ),
            make(
                ChartKey.PRESSURE_COMPARISON,
                "Downhole pressure by wellbore",
                ChartKind.LINE,
                pressure,
                None,
                ex3,
            ),
            make(
                ChartKey.UPTIME_STRIP,
                "On-stream hours by wellbore",
                ChartKind.STRIP,
                uptime,
                None,
                ex4,
            ),
            self._wellbores_on_stream(linked, rng, window, seed, field_scope, notes, excluded),
            self._perforated_by_wellbore(
                perf, names, rng, window, seed, field_scope, notes, excluded
            ),
        ]
        dedup: dict[tuple[str, str], ExcludedSeries] = {}
        for item in excluded:
            dedup[(item.name, item.reason)] = item
        return FieldChartSet(
            project_id=project_id,
            as_of=rng.as_of,
            window=window,
            wellbore_ids=sorted(
                {r.wellbore_id for r in linked if r.wellbore_id} | set(perf), key=str
            ),
            charts=charts,
            excluded_series=list(dedup.values()),
            reconciliation_note=None
            if published
            else (
                "Unreconciled until a published model associates series: wellbore association "
                "here uses the deterministic identity links of the extracted records."
            ),
            generated_from_revision=revision,
            cache_key=digest(seed, rng.as_of, window.model_dump() if window else None),
        )

    def _totals(
        self,
        linked: list[Loaded],
        measures: tuple[str, ...],
        rng: _Range,
        scope: ChartSeriesScope,
    ) -> tuple[list[tuple[Line, int]], list[ExcludedSeries]]:
        """Per-phase sums over wellbores with the same stated unit (or same unstated column)."""
        out: list[tuple[Line, int]] = []
        excluded: list[ExcludedSeries] = []
        for measure, label, _ in RATE_MEASURES:
            if measure not in measures:
                continue
            groups: dict[str, list[Loaded]] = defaultdict(list)
            for r in (r for r in linked if r.measure == measure):
                who = f"{label} — {r.wellbore_label or r.well_name or r.series_id}"
                if r.status is SeriesUnitStatus.MIXED:
                    excluded.append(
                        ExcludedSeries(
                            name=who,
                            source_series_id=r.series_id,
                            reason="mixed units across rows: not summed",
                        )
                    )
                elif numeric.has_repeated(r.x):
                    excluded.append(
                        ExcludedSeries(
                            name=who,
                            source_series_id=r.series_id,
                            reason="repeated reporting dates: not summed (would double count)",
                        )
                    )
                else:
                    groups[axis_group(measure, r.unit, r.status, str(r.document_id))].append(r)
            for gkey in sorted(groups):
                members = groups[gkey]
                days, total = numeric.sum_by_day([_prefix(r, rng) for r in members])
                first = members[0]
                multi = len(groups) > 1
                unit_txt = first.unit or "unit not stated"
                line = Line(
                    series_key=f"total:{measure}:{gkey}",
                    name=f"{label} — sum of {len(members)} wellbore series"
                    + (f" [{unit_txt}]" if multi else ""),
                    axis_label=label,
                    unit=first.unit,
                    unit_status=first.status,
                    axis_group=gkey,
                    scope=scope,
                    x=days,
                    y=total,
                    summable=True,
                    revision=digest(sorted(r.sha for r in members)),
                    evidence=[e for r in members for e in r.evidence][:20],
                )
                out.append((line, len(members)))
        return out, excluded

    def _wellbores_on_stream(
        self,
        linked: list[Loaded],
        rng: _Range,
        window: Any,
        seed: str,
        scope: ChartSeriesScope,
        notes: list[str],
        excluded: list[ExcludedSeries],
    ) -> ChartSpec:
        days: dict[float, set[UUID]] = defaultdict(set)
        seen: dict[float, bool] = {}
        shas: list[str] = []
        for r in linked:
            if r.measure != HOURS[0]:
                continue
            shas.append(r.sha)
            x, y = _from_lo(*_prefix(r, rng), rng)
            for d, v in zip(x.tolist(), y.tolist(), strict=True):
                seen.setdefault(d, True)
                if v == v and v > 0 and r.wellbore_id is not None:
                    days[d].add(r.wellbore_id)
        lines: list[Line] = []
        if seen:
            xs = np.array(sorted(seen), dtype=np.float64)
            ys = np.array([float(len(days.get(d, ()))) for d in xs.tolist()])
            lines.append(
                Line(
                    series_key="wellbores-on-stream",
                    name="Wellbores reporting on-stream hours above zero",
                    axis_label="Wellbores",
                    unit="wellbores",
                    unit_status=SeriesUnitStatus.STATED,
                    axis_group="unit:wellbores",
                    scope=scope,
                    x=xs,
                    y=ys,
                    revision=digest(sorted(shas)),
                    kind=ChartKind.BAR,
                )
            )
        chart = build_chart(
            ChartKey.CUSTOM,
            "wellbores_on_stream",
            "Wellbores with on-stream hours > 0 (count per reporting day)",
            ChartKind.BAR,
            scope,
            lines,
            window=window,
            as_of=rng.as_of,
            seed=seed,
            notes=[
                *notes,
                "Counts wellbores whose reported on-stream hours exceed zero that day; it is not "
                "a well-status or 'active well' claim, and a wellbore without a value is not counted.",
            ],
            empty_message="No on-stream hours records exist in this project.",
        )
        excluded.extend(chart.excluded_series)
        return chart

    def _perforated_by_wellbore(
        self,
        perf: dict[UUID, PerfResult],
        names: dict[UUID, tuple[str, str]],
        rng: _Range,
        window: Any,
        seed: str,
        scope: ChartSeriesScope,
        notes: list[str],
        excluded: list[ExcludedSeries],
    ) -> ChartSpec:
        if rng.as_of is None:
            return build_chart(
                ChartKey.PERFORATED_LENGTH_BY_WELLBORE,
                ChartKey.PERFORATED_LENGTH_BY_WELLBORE.value,
                "Perforated length by wellbore at the as-of date",
                ChartKind.BAR,
                scope,
                [],
                window=window,
                as_of=None,
                seed=seed,
                empty_reason=ChartEmptyReason.NOT_APPLICABLE,
                empty_message="Select an as-of date: no implicit 'today' is assumed.",
            )
        lines: list[Line] = []
        for wid, result in perf.items():
            label, well = names.get(wid, (str(wid), None))
            length = result.history.perforated_length_at_as_of
            if length is None:
                excluded.append(
                    ExcludedSeries(
                        name=f"Perforated length — {label}",
                        reason="length unknown at the as-of date (no dated event yet, or the "
                        "engine cannot resolve it); not shown as zero",
                    )
                )
                continue
            lines.append(
                Line(
                    series_key=f"perforated-length:{wid}",
                    name=f"Perforated length at as-of — {label}",
                    axis_label="Perforated length",
                    unit="m",
                    unit_status=SeriesUnitStatus.STATED,
                    axis_group="unit:m",
                    scope=_scope_bore(wid, label, well),
                    x=np.array([numeric.epoch_day(rng.as_of)]),
                    y=np.array([length]),
                    revision=result.history.revision,
                    evidence=result.evidence,
                    kind=ChartKind.BAR,
                )
            )
        lines.sort(key=lambda ln: ln.name)
        chart = build_chart(
            ChartKey.PERFORATED_LENGTH_BY_WELLBORE,
            ChartKey.PERFORATED_LENGTH_BY_WELLBORE.value,
            "Perforated length by wellbore at the as-of date",
            ChartKind.BAR,
            scope,
            lines,
            window=window,
            as_of=rng.as_of,
            seed=seed,
            notes=[*notes, "Union of MD intervals from dated perforation events (engine)."],
            empty_reason=ChartEmptyReason.NO_RECORDS,
            empty_message="No wellbore has a known perforated length at the as-of date.",
        )
        return chart


def _clipped(line: Line, rng: _Range) -> Line:
    x, y = _from_lo(line.x, line.y, rng)
    return Line(**{**line.__dict__, "x": x, "y": y})


def _derived_cumulative(line: Line, rng: _Range) -> Line:
    """Cumulative of a field total; the total holds the whole prefix, so only then clip to lo."""
    x, y = _from_lo(line.x, numeric.cumulative(line.y), rng)
    return Line(
        series_key=f"cum:{line.series_key}",
        name=line.name.replace(" — sum of", " — cumulative of sum of"),
        axis_label=line.axis_label,
        unit=line.unit,
        unit_status=line.unit_status,
        axis_group=line.axis_group + ":cum",
        scope=line.scope,
        x=x,
        y=y,
        revision=line.revision,
        evidence=line.evidence,
    )

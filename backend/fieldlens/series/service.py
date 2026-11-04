"""Read-only series service for charts and, later, the agent's ``get_series_window`` tool.

Series are visible only through the project's *current* extraction run of a document
(``superseded`` false and status ``succeeded``/``partial``): an interrupted, failed or superseded
run exposes nothing. Every call is project-scoped; an id from another project is a 404."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import and_, func, select
from sqlalchemy.engine import Row
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.series import (
    DEFAULT_SERIES_PAGE,
    DEFAULT_WINDOW_POINTS,
    DOWNSAMPLING_ALGORITHM,
    FULL_RESOLUTION_LIMIT,
    MAX_SERIES_PAGE,
    MAX_SERIES_WINDOW_POINTS,
    MIN_WINDOW_POINTS,
    IndexEncoding,
    IndexOrder,
    IndexType,
    SeriesEvidence,
    SeriesIndex,
    SeriesInfo,
    SeriesKind,
    SeriesList,
    SeriesUnitStatus,
    SeriesWindow,
    WindowResolution,
)
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from . import codec
from .downsample import select_positions
from .tables import series_axis, series_curve

_EPOCH = date(1970, 1, 1)
_NUMBER = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$", re.ASCII)
_VISIBLE_STATUS = ("succeeded", "partial")


@dataclass(frozen=True)
class _Bound:
    value: float | None
    text: str | None


class SeriesService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    # -- listing ---------------------------------------------------------------------------
    def list_series(
        self,
        project_id: UUID,
        *,
        wellbore_label: str | None = None,
        wellbore_label_token: str | None = None,
        kind: SeriesKind | None = None,
        mnemonic: str | None = None,
        document_id: UUID | None = None,
        limit: int = DEFAULT_SERIES_PAGE,
        offset: int = 0,
    ) -> SeriesList:
        if not 1 <= limit <= MAX_SERIES_PAGE or offset < 0:
            raise ContractError(ErrorCode.VALIDATION_ERROR, "limit or offset out of range")
        with session_scope(self._factory) as session:
            _require_project(session, project_id)
            where = _visible(project_id)
            if wellbore_label is not None:
                where.append(series_axis.c.wellbore_label == wellbore_label)
            if wellbore_label_token is not None:
                # "F-12" matches "NO 15/9-F-12 H" but not "F-120"; case-insensitive.
                pattern = r"(^|[^0-9A-Za-z])" + re.escape(wellbore_label_token) + r"([^0-9]|$)"
                where.append(series_axis.c.wellbore_label.op("~*")(pattern))
            if kind is not None:
                where.append(series_axis.c.kind == kind.value)
            if mnemonic is not None:
                where.append(func.lower(series_curve.c.measure) == mnemonic.lower())
            if document_id is not None:
                where.append(series_axis.c.document_id == document_id)
            base = _joined()
            total = session.execute(
                select(func.count()).select_from(base).where(and_(*where))
            ).scalar_one()
            rows = session.execute(
                select(*_info_columns())
                .select_from(base)
                .where(and_(*where))
                .order_by(
                    series_axis.c.document_id,
                    series_axis.c.ordinal,
                    series_curve.c.column_ordinal,
                )
                .limit(limit)
                .offset(offset)
            ).all()
            items = [_info(r) for r in rows]
        nxt = offset + len(items)
        return SeriesList(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            next_offset=nxt if nxt < total else None,
        )

    def get_series(self, project_id: UUID, series_id: UUID) -> SeriesInfo:
        with session_scope(self._factory) as session:
            return _info(_one(session, project_id, series_id))

    # -- windows ---------------------------------------------------------------------------
    def get_window(
        self,
        project_id: UUID,
        series_id: UUID,
        *,
        start: str | None = None,
        end: str | None = None,
        max_points: int = DEFAULT_WINDOW_POINTS,
        resolution: WindowResolution = WindowResolution.DOWNSAMPLED,
    ) -> SeriesWindow:
        if not MIN_WINDOW_POINTS <= max_points <= MAX_SERIES_WINDOW_POINTS:
            raise ContractError(
                ErrorCode.VALIDATION_ERROR,
                f"max_points must be between {MIN_WINDOW_POINTS} and {MAX_SERIES_WINDOW_POINTS}",
            )
        with session_scope(self._factory) as session:
            row = _one(session, project_id, series_id)
            info = _info(row)
            encoding = IndexEncoding(row.index_encoding)
            lo = _parse_bound(start, encoding, "from")
            hi = _parse_bound(end, encoding, "to")
            if lo.value is not None and hi.value is not None and lo.value > hi.value:
                raise ContractError(ErrorCode.VALIDATION_ERROR, "from must not be after to")
            index = codec.decode_f8(
                session.execute(
                    select(series_axis.c.index_data).where(series_axis.c.axis_id == row.axis_id)
                ).scalar_one()
            )
            if index.size != int(row.sample_count):
                raise _inconsistent()
            sel = _select(index, row.index_order, lo.value, hi.value)
            values = self._values(session, series_id, sel, int(row.sample_count))
        window_index = index[sel] if isinstance(sel, np.ndarray) else index[sel[0] : sel[1]]
        n = int(values.size)
        nulls = int(np.isnan(values).sum())
        if resolution is WindowResolution.FULL and n > FULL_RESOLUTION_LIMIT:
            raise ContractError(
                ErrorCode.VALIDATION_ERROR,
                f"window holds {n} samples; full resolution is limited to "
                f"{FULL_RESOLUTION_LIMIT} (narrow the window or use downsampled)",
                details={"samples_in_window": n, "limit": FULL_RESOLUTION_LIMIT},
            )
        omitted = 0
        downsampled = False
        if resolution is WindowResolution.DOWNSAMPLED and n > max_points:
            positions, omitted = select_positions(values, max_points)
            window_index, values = window_index[positions], values[positions]
            downsampled = True
        return SeriesWindow(
            series=info,
            requested_from=lo.text,
            requested_to=hi.text,
            resolution=resolution,
            max_points=max_points,
            downsampled=downsampled,
            algorithm=DOWNSAMPLING_ALGORITHM if downsampled else None,
            source_samples_in_window=n,
            null_samples_in_window=nulls,
            returned_points=int(values.size),
            gaps_omitted=omitted,
            index=window_index.tolist(),
            dates=[_iso(v) for v in window_index.tolist()]
            if encoding is IndexEncoding.EPOCH_DAYS
            else None,
            values=[None if v != v else v for v in values.tolist()],
            cache_key=_cache_key(info, lo.text, hi.text, max_points, resolution),
        )

    @staticmethod
    def _values(
        session: Session, series_id: UUID, sel: NDArray[np.int64] | tuple[int, int], total: int
    ) -> NDArray[np.float64]:
        if isinstance(sel, tuple):
            first, last = sel
            if last <= first:
                return np.zeros(0, dtype=np.float64)
            data = session.execute(
                select(
                    func.substring(series_curve.c.values_data, first * 8 + 1, (last - first) * 8)
                ).where(series_curve.c.series_id == series_id)
            ).scalar_one()
            out = codec.decode_f8(data).copy()
            if out.size != last - first or last > total:
                raise _inconsistent()
            return out
        if sel.size == 0:
            return np.zeros(0, dtype=np.float64)
        data = session.execute(
            select(series_curve.c.values_data).where(series_curve.c.series_id == series_id)
        ).scalar_one()
        full = codec.decode_f8(data)
        if full.size != total:
            raise _inconsistent()
        return full[sel].copy()


def _inconsistent() -> ContractError:
    return ContractError(
        ErrorCode.INTERNAL_ERROR, "stored series is inconsistent with its sample count", 500
    )


def _require_project(session: Session, project_id: UUID) -> None:
    found = session.execute(
        select(m.project.c.project_id).where(m.project.c.project_id == project_id)
    ).first()
    if found is None:
        raise ContractError(ErrorCode.NOT_FOUND, "project not found", 404)


def _joined() -> Any:
    run = m.extraction_run
    return series_curve.join(
        series_axis,
        and_(
            series_axis.c.project_id == series_curve.c.project_id,
            series_axis.c.axis_id == series_curve.c.axis_id,
        ),
    ).join(
        run,
        and_(run.c.project_id == series_axis.c.project_id, run.c.run_id == series_axis.c.run_id),
    )


def _visible(project_id: UUID) -> list[Any]:
    run = m.extraction_run
    return [
        series_curve.c.project_id == project_id,
        run.c.superseded.is_(False),
        run.c.status.in_(_VISIBLE_STATUS),
    ]


def _info_columns() -> list[Any]:
    a, c, run = series_axis.c, series_curve.c, m.extraction_run.c
    return [
        c.series_id,
        c.project_id,
        c.document_id,
        c.run_id,
        c.axis_id,
        c.column_ordinal,
        c.measure,
        c.description,
        c.unit,
        c.unit_status,
        c.sample_count,
        c.valid_count,
        c.null_count,
        c.first_valid_index,
        c.last_valid_index,
        c.min_value,
        c.max_value,
        c.null_sentinel,
        c.record_ordinal,
        c.evidence.label("curve_evidence"),
        c.data_sha256,
        c.created_at,
        a.kind,
        a.index_type,
        a.index_encoding,
        a.index_name,
        a.index_unit,
        a.index_unit_status,
        a.index_order,
        a.index_first,
        a.index_last,
        a.index_min,
        a.index_max,
        a.position_kind,
        a.well_name,
        a.wellbore_label,
        a.subject,
        a.evidence.label("axis_evidence"),
        run.profile_name,
        run.profile_version,
    ]


def _one(session: Session, project_id: UUID, series_id: UUID) -> Row[Any]:
    _require_project(session, project_id)
    row = session.execute(
        select(*_info_columns())
        .select_from(_joined())
        .where(*_visible(project_id), series_curve.c.series_id == series_id)
    ).first()
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "series not found", 404)
    return row


def _iso(epoch_day: float) -> str:
    return (_EPOCH + timedelta(days=int(epoch_day))).isoformat()


def _info(r: Row[Any]) -> SeriesInfo:
    encoding = IndexEncoding(r.index_encoding)
    dated = encoding is IndexEncoding.EPOCH_DAYS
    positions = _position_range(r)
    return SeriesInfo(
        series_id=r.series_id,
        project_id=r.project_id,
        document_id=r.document_id,
        run_id=r.run_id,
        kind=SeriesKind(r.kind),
        well_name=r.well_name,
        wellbore_label=r.wellbore_label,
        subject=r.subject,
        measure=r.measure,
        description=r.description,
        unit=r.unit,
        unit_status=SeriesUnitStatus(r.unit_status),
        index=SeriesIndex(
            type=IndexType(r.index_type),
            encoding=encoding,
            name=r.index_name,
            unit=r.index_unit,
            unit_status=SeriesUnitStatus(r.index_unit_status),
            order=IndexOrder(r.index_order),
            first=r.index_first,
            last=r.index_last,
            min=r.index_min,
            max=r.index_max,
            first_date=_iso(r.index_first) if dated else None,
            last_date=_iso(r.index_last) if dated else None,
        ),
        sample_count=r.sample_count,
        valid_count=r.valid_count,
        null_count=r.null_count,
        first_valid_index=r.first_valid_index,
        last_valid_index=r.last_valid_index,
        min_value=r.min_value,
        max_value=r.max_value,
        null_sentinel=r.null_sentinel,
        revision=r.data_sha256,
        evidence=SeriesEvidence(
            run_id=r.run_id,
            profile_name=r.profile_name,
            profile_version=r.profile_version,
            record_ordinal=r.record_ordinal,
            position_kind=r.position_kind,
            first_source_position=positions[0],
            last_source_position=positions[1],
            locator={**r.axis_evidence, **r.curve_evidence},
        ),
        created_at=r.created_at,
    )


def _position_range(r: Row[Any]) -> tuple[int, int]:
    ev = r.curve_evidence
    if "first_row" in ev:
        return int(ev["first_row"]), int(ev["last_row"])
    lines = r.axis_evidence.get("data_lines", {})
    return int(lines.get("first", 0)), int(lines.get("last", 0))


def _parse_bound(raw: str | None, encoding: IndexEncoding, name: str) -> _Bound:
    if raw is None:
        return _Bound(None, None)
    if encoding is IndexEncoding.EPOCH_DAYS:
        if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", raw, re.ASCII):
            raise ContractError(
                ErrorCode.VALIDATION_ERROR, f"{name} must be an ISO date (YYYY-MM-DD) here"
            )
        try:
            return _Bound(float((date.fromisoformat(raw) - _EPOCH).days), raw)
        except ValueError as exc:
            raise ContractError(ErrorCode.VALIDATION_ERROR, f"{name} is not a valid date") from exc
    if not _NUMBER.match(raw):
        raise ContractError(ErrorCode.VALIDATION_ERROR, f"{name} must be a plain number")
    value = float(raw)
    if not math.isfinite(value):
        raise ContractError(ErrorCode.VALIDATION_ERROR, f"{name} must be finite")
    return _Bound(value, raw)


def _select(
    index: NDArray[np.float64], order: str, lo: float | None, hi: float | None
) -> NDArray[np.int64] | tuple[int, int]:
    """Samples with ``lo <= index <= hi``: a contiguous range for ordered indexes (binary
    search), an explicit position list when the index goes backwards (source order kept)."""
    if order in ("increasing", "non_decreasing"):
        first = 0 if lo is None else int(np.searchsorted(index, lo, side="left"))
        last = index.size if hi is None else int(np.searchsorted(index, hi, side="right"))
        return first, max(first, last)
    mask = np.ones(index.size, dtype=bool)
    if lo is not None:
        mask &= index >= lo
    if hi is not None:
        mask &= index <= hi
    return np.flatnonzero(mask)


def _cache_key(
    info: SeriesInfo,
    start: str | None,
    end: str | None,
    max_points: int,
    resolution: WindowResolution,
) -> str:
    payload = json.dumps(
        [
            str(info.series_id),
            str(info.run_id),
            info.revision,
            start,
            end,
            max_points if resolution is WindowResolution.DOWNSAMPLED else None,
            resolution.value,
            DOWNSAMPLING_ALGORITHM,
        ],
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()

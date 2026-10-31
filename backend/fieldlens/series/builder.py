"""Persist the series a profile produced, inside the transaction that finalizes the run.

Called by the extraction runner after the fenced run update, so the rows exist only if the run
is finalized: an interrupted or fence-lost run leaves nothing. Statistics are recomputed here
from the stored arrays (independently of the profile's own per-curve summary records, which is
what the fidelity tests compare against)."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import UUID, uuid5

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from fieldlens.persistence import models as m
from fieldlens.profiles.types import AxisOut, CurveOut

from . import codec
from .tables import series_axis, series_curve

CURVE_BATCH = 8


def index_order(index: NDArray[np.float64]) -> str:
    if index.size < 2:
        return "increasing"
    d = np.diff(index)
    if bool((d > 0).all()):
        return "increasing"
    if bool((d >= 0).all()):
        return "non_decreasing"
    return "unordered"


def summarize(index: NDArray[np.float64], values: NDArray[np.float64]) -> dict[str, Any]:
    """Counts and range of a value array (NaN = missing), in storage order."""
    valid = ~np.isnan(values)
    good = np.flatnonzero(valid)
    out: dict[str, Any] = {
        "sample_count": int(values.size),
        "valid_count": int(good.size),
        "null_count": int(values.size - good.size),
        "first_valid_index": None,
        "last_valid_index": None,
        "min_value": None,
        "max_value": None,
    }
    if good.size:
        picked = values[good]
        out["first_valid_index"] = float(index[good[0]])
        out["last_valid_index"] = float(index[good[-1]])
        out["min_value"] = float(picked.min())
        out["max_value"] = float(picked.max())
    return out


def purge_superseded(session: Session, project_id: UUID, document_id: UUID) -> None:
    """Drop the series of this document's superseded runs (they are superseded with the run)."""
    er = m.extraction_run
    session.execute(
        delete(series_axis).where(
            series_axis.c.project_id == project_id,
            series_axis.c.document_id == document_id,
            series_axis.c.run_id.in_(
                select(er.c.run_id).where(
                    er.c.project_id == project_id,
                    er.c.document_id == document_id,
                    er.c.superseded.is_(True),
                )
            ),
        )
    )


def store_series(
    session: Session,
    project_id: UUID,
    run_id: UUID,
    document_id: UUID,
    axes: list[AxisOut],
) -> int:
    """Replace this run's series (idempotent for a retried finalization). Returns curve count."""
    session.execute(delete(series_axis).where(series_axis.c.run_id == run_id))
    stored = 0
    for ordinal, axis in enumerate(axes):
        n = int(axis.index.size)
        if n == 0 or any(c.values.size != n for c in axis.curves) or axis.positions.size != n:
            raise ValueError("series arrays must have one entry per sample")
        index_bytes = codec.encode_f8(axis.index)
        axis_id = uuid5(run_id, f"axis:{ordinal}")
        subject = axis.subject
        session.execute(
            insert(series_axis).values(
                axis_id=axis_id,
                project_id=project_id,
                run_id=run_id,
                document_id=document_id,
                ordinal=ordinal,
                kind=axis.kind,
                index_type=axis.index_type,
                index_encoding=axis.index_encoding,
                index_name=axis.index_name[:128],
                index_unit=axis.index_unit,
                index_unit_status="stated" if axis.index_unit else "missing",
                index_order=index_order(axis.index),
                sample_count=n,
                index_first=float(axis.index[0]),
                index_last=float(axis.index[-1]),
                index_min=float(axis.index.min()),
                index_max=float(axis.index.max()),
                position_kind=axis.position_kind,
                well_name=_text(subject.get("well_name")),
                wellbore_label=_text(subject.get("wellbore_label") or subject.get("wellbore_name")),
                subject=subject,
                evidence=axis.evidence,
                index_data=index_bytes,
                positions_data=codec.encode_i4(axis.positions),
            )
        )
        batch: list[dict[str, Any]] = []
        for curve in axis.curves:
            batch.append(
                _curve_row(project_id, run_id, document_id, axis_id, axis, curve, index_bytes)
            )
            if len(batch) >= CURVE_BATCH:
                session.execute(insert(series_curve), batch)
                batch = []
            stored += 1
        if batch:
            session.execute(insert(series_curve), batch)
    return stored


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _curve_row(
    project_id: UUID,
    run_id: UUID,
    document_id: UUID,
    axis_id: UUID,
    axis: AxisOut,
    curve: CurveOut,
    index_bytes: bytes,
) -> dict[str, Any]:
    values_bytes = codec.encode_f8(curve.values)
    digest = hashlib.sha256()
    digest.update(index_bytes)
    digest.update(values_bytes)
    return {
        "series_id": uuid5(run_id, f"curve:{axis_id}:{curve.column_ordinal}"),
        "project_id": project_id,
        "axis_id": axis_id,
        "run_id": run_id,
        "document_id": document_id,
        "column_ordinal": curve.column_ordinal,
        "measure": curve.measure[:128],
        "description": curve.description,
        "unit": curve.unit,
        "unit_status": curve.unit_status,
        "null_sentinel": curve.null_sentinel,
        "record_ordinal": curve.record_ordinal,
        "evidence": curve.evidence,
        "data_sha256": digest.hexdigest(),
        "values_data": values_bytes,
        **summarize(axis.index, curve.values),
    }

"""Time-series DTOs (TASK-047): stored log curves and production series, windowed reads.

Everything here is a *source observation* derived from an extraction run: samples keep the
unit and index convention the source stated (a missing unit is ``missing``, never assumed),
missing samples are explicit nulls (never zero), and no value is reconciled across wellbores.
``evidence`` points back at the extraction run and the source record/data range. A window never
contains more than ``MAX_SERIES_WINDOW_POINTS`` downsampled or ``FULL_RESOLUTION_LIMIT`` raw
samples."""

from __future__ import annotations

import unicodedata
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, field_validator

from .base import ContractModel, FiniteJsonValue

DEFAULT_WINDOW_POINTS = 2000
MIN_WINDOW_POINTS = 10
MAX_SERIES_WINDOW_POINTS = 10_000
FULL_RESOLUTION_LIMIT = 50_000
MAX_SERIES_PAGE = 500
DEFAULT_SERIES_PAGE = 100
DOWNSAMPLING_ALGORITHM = "minmax-gap-v1"


class SeriesKind(StrEnum):
    LOG = "log"
    PRODUCTION = "production"


class IndexType(StrEnum):
    DEPTH = "depth"
    TIME = "time"
    UNKNOWN = "unknown"
    """The source index is neither recognizably a depth nor a time."""


class IndexEncoding(StrEnum):
    NUMERIC = "numeric"
    """Index values are numbers in the stated index unit."""
    EPOCH_DAYS = "epoch_days"
    """Day-precision dates stored as whole days since 1970-01-01 (production series)."""


class IndexOrder(StrEnum):
    INCREASING = "increasing"
    NON_DECREASING = "non_decreasing"
    """Equal neighbouring index values exist (for example repeated production days)."""
    UNORDERED = "unordered"
    """The index goes backwards somewhere; source order is kept and nothing is re-sorted."""


class SeriesUnitStatus(StrEnum):
    STATED = "stated"
    MISSING = "missing"
    """The source gave no usable unit; none is assumed."""
    MIXED = "mixed"
    """Different rows state different units; no single unit is reported."""


class WindowResolution(StrEnum):
    DOWNSAMPLED = "downsampled"
    FULL = "full"


def _no_control(value: str | None) -> str | None:
    if value is not None and any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("must not contain NUL or other control characters")
    return value


class SeriesIndex(ContractModel):
    type: IndexType
    encoding: IndexEncoding
    name: str = Field(description="Index column name as written in the source.")
    unit: str | None = None
    unit_status: SeriesUnitStatus
    order: IndexOrder
    first: float = Field(description="Index value of the first stored sample.")
    last: float = Field(description="Index value of the last stored sample.")
    min: float
    max: float
    first_date: str | None = Field(
        default=None, description="ISO date when encoding is epoch_days."
    )
    last_date: str | None = None


class SeriesEvidence(ContractModel):
    run_id: UUID
    profile_name: str | None = None
    profile_version: str | None = None
    record_ordinal: int | None = Field(
        default=None, description="Ordinal of the extracted record this series is anchored to."
    )
    position_kind: Literal["line", "row"] = Field(
        description="Whether source positions are LAS data lines or workbook rows."
    )
    first_source_position: int
    last_source_position: int
    locator: dict[str, FiniteJsonValue] = Field(
        description="Source locators (curve record, data range, sheet/column) for this series."
    )


class SeriesInfo(ContractModel):
    series_id: UUID
    project_id: UUID
    document_id: UUID
    run_id: UUID
    kind: SeriesKind
    well_name: str | None = None
    wellbore_label: str | None = Field(
        default=None, description="Wellbore label exactly as written in the source records."
    )
    subject: dict[str, FiniteJsonValue]
    measure: str = Field(description="Curve mnemonic or production measure key.")
    description: str | None = None
    unit: str | None = None
    unit_status: SeriesUnitStatus
    index: SeriesIndex
    sample_count: int
    valid_count: int
    null_count: int
    first_valid_index: float | None = None
    last_valid_index: float | None = None
    min_value: float | None = None
    max_value: float | None = None
    null_sentinel: float | None = Field(
        default=None, description="Source NULL value that was converted to a real null."
    )
    revision: str = Field(description="SHA-256 of the stored index and sample bytes.")
    evidence: SeriesEvidence
    created_at: datetime


class SeriesListQuery(ContractModel):
    wellbore_label: str | None = Field(default=None, min_length=1, max_length=256)
    kind: SeriesKind | None = None
    mnemonic: str | None = Field(default=None, min_length=1, max_length=128)
    document_id: UUID | None = None
    limit: int = Field(default=DEFAULT_SERIES_PAGE, ge=1, le=MAX_SERIES_PAGE)
    offset: int = Field(default=0, ge=0, le=1_000_000)

    @field_validator("wellbore_label", "mnemonic")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return _no_control(value)


class SeriesList(ContractModel):
    items: list[SeriesInfo] = Field(max_length=MAX_SERIES_PAGE)
    total: int
    limit: int
    offset: int
    next_offset: int | None = None


class SeriesWindowQuery(ContractModel):
    """``from``/``to`` are inclusive: numbers for numeric indexes, ``YYYY-MM-DD`` for dates."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str | None = Field(default=None, alias="from", min_length=1, max_length=64)
    to: str | None = Field(default=None, min_length=1, max_length=64)
    max_points: int = Field(
        default=DEFAULT_WINDOW_POINTS, ge=MIN_WINDOW_POINTS, le=MAX_SERIES_WINDOW_POINTS
    )
    resolution: WindowResolution = WindowResolution.DOWNSAMPLED

    @field_validator("from_", "to")
    @classmethod
    def _text(cls, value: str | None) -> str | None:
        return _no_control(value)


class SeriesWindow(ContractModel):
    series: SeriesInfo
    requested_from: str | None = None
    requested_to: str | None = None
    resolution: WindowResolution
    max_points: int
    downsampled: bool
    algorithm: str | None = Field(
        default=None, description="Downsampling algorithm; null when every sample is returned."
    )
    source_samples_in_window: int
    null_samples_in_window: int
    returned_points: int
    gaps_omitted: int = Field(
        description="Null runs in the window that the downsampled output could not represent."
    )
    index: list[float] = Field(max_length=FULL_RESOLUTION_LIMIT)
    dates: list[str] | None = Field(
        default=None, max_length=FULL_RESOLUTION_LIMIT, description="ISO dates, epoch_days only."
    )
    values: list[float | None] = Field(
        max_length=FULL_RESOLUTION_LIMIT, description="Null marks a missing sample (a gap)."
    )
    cache_key: str = Field(description="Stable for the same series revision, window and mode.")

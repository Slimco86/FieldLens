"""Explore chart DTOs (TASK-094, FL-025; spec EXPLORE_ENRICHMENT sections 3 XC-*, 4.2).

DTO-only freeze. A chart is a declarative spec the UI renders; it never invents values:

* null ``y`` values are gaps and stay gaps (never zero-filled, never joined);
* every axis carries its own unit (different units never share an axis);
* display points are downsampled (<= ``MAX_DISPLAY_POINTS`` per series) but ``aggregates`` are exact
  server-side values over the full-resolution data, and the two are reported separately;
* every spec states its scope (well-level, wellbore-level, field-level) and an ambiguous association is
  surfaced rather than attributed to a "first bore";
* a chart without records is an explicit empty state with a reason, not an empty or zero chart.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from .base import MAX_WINDOW_POINTS, ContractModel, UtcDatetime
from .evidence import EvidenceLink
from .series import SeriesUnitStatus

MAX_DISPLAY_POINTS = MAX_WINDOW_POINTS
MAX_CHARTS = 40
MAX_SERIES_PER_CHART = 60
DOWNSAMPLING_ALGORITHM = "minmax-gap-v1"


class ChartKind(StrEnum):
    LINE = "line"
    STEP = "step"
    BAR = "bar"
    STACKED_BAR = "stacked_bar"
    STACKED_AREA = "stacked_area"
    SCATTER = "scatter"
    STRIP = "strip"
    """On-stream/uptime strip."""
    TIMELINE = "timeline"
    """Event timeline (perforation/completion events)."""
    LOG_TRACK = "log_track"
    """Value versus MD with reference lines."""
    CORRELATION = "correlation"
    """Stratigraphic correlation (top depth per surface per wellbore)."""


class ChartKey(StrEnum):
    """Stable identity of a chart in a set; also the target of chart links and chat chart requests."""

    PRODUCTION_RATES = "production_rates"
    CUMULATIVE_VOLUMES = "cumulative_volumes"
    DOWNHOLE_PRESSURE_TEMPERATURE = "downhole_pressure_temperature"
    TUBING_ANNULUS_PRESSURE = "tubing_annulus_pressure"
    ON_STREAM_HOURS = "on_stream_hours"
    PERFORATION_TIMELINE = "perforation_timeline"
    PERFORATED_LENGTH = "perforated_length"
    LOG_TRACKS = "log_tracks"
    PRESSURE_TESTS = "pressure_tests"
    LAB_TESTS = "lab_tests"
    FIELD_RATES_BY_WELLBORE = "field_rates_by_wellbore"
    FIELD_RATES_TOTAL = "field_rates_total"
    FIELD_CUMULATIVE_BY_WELLBORE = "field_cumulative_by_wellbore"
    PRODUCER_INJECTOR_VOLUMES = "producer_injector_volumes"
    PRESSURE_COMPARISON = "pressure_comparison"
    UPTIME_STRIP = "uptime_strip"
    PERFORATED_LENGTH_BY_WELLBORE = "perforated_length_by_wellbore"
    STRATIGRAPHIC_CORRELATION = "stratigraphic_correlation"
    CUSTOM = "custom"
    """Assistant-composed chart over tool-result series."""


class ChartScope(StrEnum):
    WELLBORE = "wellbore"
    WELL = "well"
    """Well-level series: labeled as such and not attributed to a wellbore (XC-2)."""
    FIELD = "field"
    PROJECT = "project"
    UNRECONCILED = "unreconciled"
    """Project-wide and not yet associated by a published model."""


class ChartEmptyReason(StrEnum):
    NO_RECORDS = "no_records"
    NO_DATA_IN_WINDOW = "no_data_in_window"
    SCOPE_AMBIGUOUS = "scope_ambiguous"
    UNIT_MISMATCH = "unit_mismatch"
    NOT_APPLICABLE = "not_applicable"
    SOURCE_UNAVAILABLE = "source_unavailable"
    AS_OF_BEFORE_DATA = "as_of_before_data"


class AxisKind(StrEnum):
    VALUE = "value"
    TIME = "time"
    DEPTH_MD = "depth_md"
    DEPTH_TVD = "depth_tvd"
    DEPTH_TVDSS = "depth_tvdss"
    CATEGORY = "category"


class AxisPosition(StrEnum):
    X = "x"
    Y_LEFT = "y_left"
    Y_RIGHT = "y_right"
    Y_EXTRA = "y_extra"


class ChartAxis(ContractModel):
    axis_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    kind: AxisKind
    position: AxisPosition
    unit: str | None = Field(default=None, max_length=32)
    unit_status: SeriesUnitStatus = SeriesUnitStatus.STATED
    datum: str | None = Field(
        default=None, description="Vertical reference for depth axes, as stated."
    )
    inverted: bool = Field(default=False, description="Depth increases downwards.")

    @model_validator(mode="after")
    def _unit(self) -> ChartAxis:
        if (
            self.unit_status is SeriesUnitStatus.STATED
            and self.unit is None
            and self.kind
            not in {
                AxisKind.CATEGORY,
                AxisKind.TIME,
            }
        ):
            raise ValueError("a stated-unit value axis needs its unit")
        return self


class ChartPoint(ContractModel):
    """One sample; ``y`` null is a gap and is rendered as a break."""

    x: float | str = Field(description="Number, or an ISO date/time string on time axes.")
    y: float | None = None


class DownsampleInfo(ContractModel):
    """Display-only decimation; distinct from the exact aggregates."""

    applied: bool
    algorithm: str | None = None
    max_points: int = Field(default=MAX_DISPLAY_POINTS, ge=10, le=MAX_DISPLAY_POINTS)
    source_points: int = Field(ge=0, description="Full-resolution samples in the window.")
    returned_points: int = Field(ge=0)
    gap_markers_preserved: bool = True
    gaps_omitted: int = Field(default=0, ge=0)
    extrema_preserved: bool = True


class SeriesAggregates(ContractModel):
    """Exact values over full-resolution data, never recomputed from display points (CH-6)."""

    basis: Literal["full_resolution"] = "full_resolution"
    count: int = Field(ge=0)
    valid_count: int = Field(ge=0)
    null_count: int = Field(ge=0)
    minimum: float | None = None
    maximum: float | None = None
    mean: float | None = None
    total: float | None = Field(default=None, description="Sum, only where summing is meaningful.")
    first_valid_x: float | str | None = None
    last_valid_x: float | str | None = None
    last_value: float | None = None
    unit: str | None = None

    @model_validator(mode="after")
    def _counts(self) -> SeriesAggregates:
        if self.valid_count + self.null_count > self.count:
            raise ValueError("valid plus null samples cannot exceed count")
        return self


class ChartSeriesScope(ContractModel):
    scope: ChartScope
    scope_label: str = Field(
        min_length=1, max_length=128, description="Shown on the chart, for example 'well-level'."
    )
    wellbore_id: UUID | None = None
    wellbore_label: str | None = None
    well_name: str | None = None
    ambiguity: str | None = Field(
        default=None, description="Why association is ambiguous; set instead of picking a wellbore."
    )

    @model_validator(mode="after")
    def _scope(self) -> ChartSeriesScope:
        if self.scope is ChartScope.WELLBORE and self.wellbore_id is None:
            raise ValueError("wellbore-scoped series need wellbore_id")
        if (
            self.scope in {ChartScope.WELL, ChartScope.UNRECONCILED}
            and self.wellbore_id is not None
        ):
            raise ValueError("well-level/unreconciled series are not attributed to a wellbore")
        return self


class ChartSeries(ContractModel):
    series_key: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=256)
    kind: ChartKind | None = Field(
        default=None, description="Overrides the chart kind for this series."
    )
    axis_id: str = Field(min_length=1, max_length=64)
    x_axis_id: str | None = None
    unit: str | None = None
    unit_status: SeriesUnitStatus = SeriesUnitStatus.STATED
    scope: ChartSeriesScope
    points: list[ChartPoint] = Field(default_factory=list, max_length=MAX_DISPLAY_POINTS)
    gap_count: int = Field(default=0, ge=0)
    downsample: DownsampleInfo
    aggregates: SeriesAggregates
    source_series_id: UUID | None = None
    series_revision: str | None = Field(default=None, description="Revision of the stored series.")
    stack_group: str | None = None
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def _display(self) -> ChartSeries:
        if self.downsample.returned_points != len(self.points):
            raise ValueError("downsample.returned_points must equal the number of points")
        if self.downsample.returned_points > self.downsample.source_points and (
            self.downsample.source_points
        ):
            raise ValueError("cannot return more points than the source has")
        return self


class ChartReferenceLine(ContractModel):
    """Reference line, for example a formation top on a log track."""

    label: str = Field(min_length=1, max_length=256)
    axis_id: str
    value: float
    unit: str | None = None
    surface_key: str | None = None
    pick_id: UUID | None = None
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=20)


class ChartEmptyState(ContractModel):
    reason: ChartEmptyReason
    message: str = Field(min_length=1)


class ExcludedSeries(ContractModel):
    """Series left out of an aggregate chart (different unit/meaning) and listed instead."""

    name: str
    source_series_id: UUID | None = None
    reason: str = Field(min_length=1)


class ChartWindow(ContractModel):
    """Inclusive window: ISO dates on time axes, numbers (as text) on depth axes."""

    model_config = ConfigDict(populate_by_name=True)

    from_: str | None = Field(default=None, alias="from", min_length=1, max_length=64)
    to: str | None = Field(default=None, min_length=1, max_length=64)


class ChartSpec(ContractModel):
    chart_id: str = Field(min_length=1, max_length=128)
    key: ChartKey
    title: str = Field(min_length=1, max_length=256)
    kind: ChartKind
    scope: ChartSeriesScope
    axes: list[ChartAxis] = Field(default_factory=list, max_length=12)
    series: list[ChartSeries] = Field(default_factory=list, max_length=MAX_SERIES_PER_CHART)
    reference_lines: list[ChartReferenceLine] = Field(default_factory=list, max_length=200)
    excluded_series: list[ExcludedSeries] = Field(default_factory=list)
    empty: ChartEmptyState | None = None
    window: ChartWindow | None = None
    as_of: date | None = Field(default=None, description="Selected as-of date the data reflects.")
    cache_key: str = Field(
        min_length=1, description="Stable for the same inputs, window and as-of."
    )
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=50)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> ChartSpec:
        if (self.empty is None) == (not self.series):
            raise ValueError("a chart has series or an empty state, exactly one of the two")
        axis_ids = {a.axis_id for a in self.axes}
        for item in self.series:
            if item.axis_id not in axis_ids:
                raise ValueError(f"series {item.series_key} references unknown axis {item.axis_id}")
            if item.x_axis_id is not None and item.x_axis_id not in axis_ids:
                raise ValueError(f"series {item.series_key} references unknown x axis")
        for line in self.reference_lines:
            if line.axis_id not in axis_ids:
                raise ValueError("reference line references an unknown axis")
        return self


# --- Perforation history ----------------------------------------------------------------


class PerforationEventKind(StrEnum):
    PERFORATE = "perforate"
    SQUEEZE = "squeeze"
    PLUG = "plug"
    ISOLATE = "isolate"
    REOPEN = "reopen"
    COMPLETION = "completion"
    OTHER = "other"


class PerforationEvent(ContractModel):
    """Effective time is when the event happened; reported time is when it was recorded/imported."""

    event_id: UUID
    wellbore_id: UUID
    kind: PerforationEventKind
    effective_at: UtcDatetime | None = None
    effective_date: date | None = None
    reported_at: UtcDatetime | None = None
    effective_time_unknown_reason: str | None = None
    top_md: float | None = None
    base_md: float | None = None
    depth_unit: str | None = None
    description: str | None = None
    validation_state: str | None = None
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=20)


class PerforatedLengthStep(ContractModel):
    """Perforated length that holds from ``effective_at`` until the next step."""

    effective_at: UtcDatetime | None = None
    effective_date: date | None = None
    length: float | None = Field(default=None, ge=0, description="Null when not computable.")
    unit: str | None = None
    event_ids: list[UUID] = Field(default_factory=list)
    unknown_reason: str | None = None


class PerforationHistory(ContractModel):
    wellbore_id: UUID
    as_of: date | None = None
    events: list[PerforationEvent] = Field(default_factory=list, max_length=2000)
    steps: list[PerforatedLengthStep] = Field(default_factory=list, max_length=2000)
    perforated_length_at_as_of: float | None = Field(default=None, ge=0)
    length_unit: str | None = None
    empty: ChartEmptyState | None = None
    revision: str | None = None


# --- Sets -------------------------------------------------------------------------------


class WellboreChartSet(ContractModel):
    """Charts for one wellbore only; well-level series are labeled and not attributed (XC-1/2)."""

    project_id: UUID
    wellbore_id: UUID
    wellbore_label: str | None = None
    well_name: str | None = None
    as_of: date | None = None
    window: ChartWindow | None = None
    charts: list[ChartSpec] = Field(default_factory=list, max_length=MAX_CHARTS)
    perforation_history: PerforationHistory | None = None
    ambiguities: list[str] = Field(
        default_factory=list, description="Surfaced association ambiguities (never 'first bore')."
    )
    generated_from_revision: str = Field(min_length=1)
    cache_key: str = Field(min_length=1, description="Covers wellbore, as-of, window and revision.")
    generated_at: UtcDatetime | None = None


class FieldChartSet(ContractModel):
    """Global charts, computed server-side on full-resolution data (XC-3)."""

    project_id: UUID
    as_of: date | None = None
    window: ChartWindow | None = None
    wellbore_ids: list[UUID] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list, max_length=MAX_CHARTS)
    excluded_series: list[ExcludedSeries] = Field(default_factory=list)
    reconciliation_note: str | None = Field(
        default=None,
        description="For example 'unreconciled until a published model associates series'.",
    )
    generated_from_revision: str = Field(min_length=1)
    cache_key: str = Field(min_length=1)
    generated_at: UtcDatetime | None = None

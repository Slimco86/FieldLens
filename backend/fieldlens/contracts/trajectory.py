"""Read-only wellbore trajectory for the 3D views (TASK-083, WELLBORE_ASSET_GENERATION section 16 F3).

The route derives local ENU offsets (metres, from the wellhead) from one validated survey set by
deterministic double-precision minimum curvature. The points are a *display* downsample only
(``displayed_count`` of ``source_count``); no calculation ever consumes them. References, units and
the CRS are returned exactly as stated by the source; an unstated CRS is ``null``, never assumed.
"""

from __future__ import annotations

from typing import Any, Final, Literal
from uuid import UUID

from pydantic import Field

from .base import ContractModel
from .exposure import SurveyStatus

TRAJECTORY_METHOD: Final = "minimum_curvature"
NorthReferenceName = Literal["true", "grid", "magnetic"]


class TrajectoryPoint(ContractModel):
    """One display point: depths in metres below the stated depth reference, offsets in metres."""

    md_m: float
    tvd_m: float = Field(description="True vertical depth below the wellhead, metres (derived).")
    east_m: float = Field(description="Local east offset from the wellhead, metres.")
    north_m: float = Field(description="Local north offset from the wellhead, metres.")


class TrajectoryReason(ContractModel):
    code: str
    message: str


class TrajectoryEvidence(ContractModel):
    """Source of a value: the document, the record and the locator inside the document."""

    document_id: UUID
    filename: str
    record_id: UUID
    kind: str
    ordinal: int
    locator: dict[str, Any]


class TrajectorySetRef(ContractModel):
    """One trajectory station set (one document run) and why it was or was not drawn."""

    document_id: UUID
    run_id: UUID
    filename: str
    page: int | None = Field(
        default=None,
        ge=1,
        description="First page of the set's stations when the source is a paged document (PDF).",
    )
    survey_status: SurveyStatus
    station_count: int = Field(ge=0)
    validated: bool
    used: bool
    reasons: list[TrajectoryReason] = Field(
        description="Why the set is not drawn (data quality or not selected); empty when used."
    )


class TrajectorySurfaceLocation(ContractModel):
    easting: float | None
    northing: float | None
    unit: str | None
    latitude: float | None
    longitude: float | None
    crs: str | None = Field(
        description="CRS / map zone text exactly as stated by the source; null when not stated."
    )
    geodetic_datum: str | None
    evidence: TrajectoryEvidence


class WellboreTrajectory(ContractModel):
    project_id: UUID
    wellbore_id: UUID
    method: Literal["minimum_curvature"] = TRAJECTORY_METHOD
    survey_set: TrajectorySetRef
    survey_status: SurveyStatus
    md_unit: str | None = Field(description="MD unit as stated in the source records.")
    depth_unit: Literal["m"] = "m"
    md_reference: str | None = Field(description="MD zero reference text as stated, else null.")
    tvd_reference: str | None
    azimuth_reference: str | None = Field(description="Azimuth reference text as stated.")
    north_reference: NorthReferenceName = Field(
        description="Normalized north the offsets are relative to; no grid/true conversion is done."
    )
    crs: str | None = Field(description="CRS of the validated surface location, else null.")
    geodetic_datum: str | None
    surface_location: TrajectorySurfaceLocation | None
    points: list[TrajectoryPoint]
    displayed_count: int = Field(ge=0)
    source_count: int = Field(ge=0)
    md_min_m: float
    md_max_m: float
    max_tvd_m: float
    source_tvd_max_abs_diff_m: float | None = Field(
        description="Largest |computed - stated| TVD over stations that state a valid TVD."
    )
    evidence: list[TrajectoryEvidence]
    other_sets: list[TrajectorySetRef]
    warnings: list[TrajectoryReason]

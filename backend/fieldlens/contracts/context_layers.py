"""Formation layer DTOs (TASK-094, FL-024; spec EXPLORE_ENRICHMENT section 4.1).

DTO-only freeze: no behavior lives here. A formation layer set is a read model over stored
``formation_pick`` records placed by the deterministic trajectory engine. The truth rules are
encoded structurally:

* depths keep the original value, unit and *explicit* vertical reference; an unknown datum is
  ``datum=None`` with ``datum_status=unknown`` and is never assumed (MD is not TVD);
* tiers are always labeled: T1 pick marker (observed), T2 level plane (illustrative, never an
  interpreted horizon), T3 interpolated surface (method shown), T4 source horizon grid (deferred, D5);
* conflicts, unsupported picks and blocked surfaces carry a reason instead of being drawn or hidden;
* surfaces are scoped per wellbore; project-wide planes require a shared vertical reference.
"""

from __future__ import annotations

from enum import StrEnum
from math import isfinite
from uuid import UUID

from pydantic import Field, model_validator

from .base import ContractModel
from .evidence import EvidenceLink, ValidationState

MAX_PICKS_PER_SURFACE = 500
MAX_SURFACES = 500
MAX_MESH_VERTICES = 200_001
MAX_MESH_TRIANGLES = 200_000
LEVEL_PLANE_LABEL = "level plane - illustrative"
LEVEL_PLANE_NOTE = "not an interpreted horizon"


class FormationTier(StrEnum):
    T1 = "T1"
    """Pick marker at the wellbore (observed)."""
    T2 = "T2"
    """Level plane at the pick's scene elevation (illustrative fallback)."""
    T3 = "T3"
    """Interpolated surface from >=3 non-collinear picks of one surface (no extrapolation)."""
    T4 = "T4"
    """Source horizon grid (stretch, deferred by D5; reserved)."""


class InterpretationStatus(StrEnum):
    OBSERVED = "observed"
    ILLUSTRATIVE = "illustrative"
    INTERPOLATED = "interpolated"
    SOURCE_GRID = "source_grid"
    """Reserved for T4."""


TIER_STATUS: dict[FormationTier, InterpretationStatus] = {
    FormationTier.T1: InterpretationStatus.OBSERVED,
    FormationTier.T2: InterpretationStatus.ILLUSTRATIVE,
    FormationTier.T3: InterpretationStatus.INTERPOLATED,
    FormationTier.T4: InterpretationStatus.SOURCE_GRID,
}


class FormationScope(StrEnum):
    WELLBORE = "wellbore"
    PROJECT = "project"
    """Spans several wellbores; requires a shared, known vertical reference."""


class DepthReference(StrEnum):
    MD = "md"
    TVD = "tvd"
    TVDSS = "tvdss"
    SCENE_ELEVATION = "scene_elevation"
    """Up-positive elevation in the scene frame, derived from the trajectory (not a source datum)."""


class DatumStatus(StrEnum):
    STATED = "stated"
    UNKNOWN = "unknown"
    """The source gave no usable datum; none is assumed."""
    NOT_APPLICABLE = "not_applicable"
    """MD along the bore or a trajectory-derived scene elevation."""


class DepthValue(ContractModel):
    """One depth with its original unit and explicit vertical reference."""

    reference: DepthReference
    value: float | None = None
    unit: str | None = Field(default=None, min_length=1, max_length=32)
    datum: str | None = Field(
        default=None,
        max_length=128,
        description="Datum name exactly as stated (for example KB, MSL).",
    )
    datum_status: DatumStatus
    original_text: str | None = None
    unknown_reason: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> DepthValue:
        if self.value is None:
            if not self.unknown_reason:
                raise ValueError("unknown depth (value null) requires unknown_reason")
        elif self.unit is None:
            raise ValueError("a known depth requires its original unit")
        if self.datum_status is DatumStatus.STATED and not self.datum:
            raise ValueError("datum_status stated requires a datum name")
        if self.datum_status is not DatumStatus.STATED and self.datum is not None:
            raise ValueError("a datum name requires datum_status stated")
        if self.reference in {DepthReference.TVD, DepthReference.TVDSS} and (
            self.datum_status is DatumStatus.NOT_APPLICABLE
        ):
            raise ValueError("TVD/TVDSS depths need a stated or explicitly unknown datum")
        if self.reference in {DepthReference.MD, DepthReference.SCENE_ELEVATION} and (
            self.datum is not None or self.datum_status is DatumStatus.STATED
        ):
            raise ValueError("MD and scene elevation do not carry a datum")
        return self


class FormationBlockReason(StrEnum):
    UNKNOWN_DATUM = "unknown_datum"
    UNKNOWN_UNIT = "unknown_unit"
    DATUM_MISMATCH = "datum_mismatch"
    """Wellbore vertical references differ; no cross-wellbore plane or surface."""
    TVD_CONFLICT = "tvd_conflict"
    """Pick TVD/TVDSS disagrees with the trajectory beyond tolerance."""
    NO_USABLE_DEPTH = "no_usable_depth"
    TWT_ONLY = "twt_only"
    UNSUPPORTED_QUALIFIER = "unsupported_qualifier"
    """Qualifier ER/FP/FO/NL/NR: listed, not drawn."""
    NO_TRAJECTORY = "no_trajectory"
    INSUFFICIENT_PICKS = "insufficient_picks"
    COLLINEAR_PICKS = "collinear_picks"
    OUTSIDE_SUPPORT = "outside_support"
    UNVALIDATED_PICK = "unvalidated_pick"


class FormationBlocked(ContractModel):
    reason: FormationBlockReason
    message: str = Field(min_length=1, description="On-screen explanation.")
    pick_ids: list[UUID] = Field(default_factory=list)


class FormationPick(ContractModel):
    """A source pick placed at its MD; every source value keeps its own unit and datum."""

    pick_id: UUID
    wellbore_id: UUID
    surface_key: str = Field(min_length=1, max_length=256)
    surface_name: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    md: DepthValue | None = None
    tvd: DepthValue | None = None
    tvdss: DepthValue | None = None
    twt: DepthValue | None = Field(
        default=None, description="Two-way time as stated; never converted to depth geometry."
    )
    scene_elevation: DepthValue | None = Field(
        default=None, description="Elevation from the trajectory at MD (up-positive scene frame)."
    )
    position_enu: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="East/north/up scene position [m] from the trajectory engine; null if unplaced.",
    )
    qualifier: str | None = Field(default=None, max_length=32)
    source_dip: DepthValue | None = Field(
        default=None, description="Unused attribute only; planes stay level."
    )
    source_azimuth: DepthValue | None = None
    validation_state: ValidationState
    tier: FormationTier = FormationTier.T1
    status: InterpretationStatus = InterpretationStatus.OBSERVED
    label: str = Field(default="pick - observed", max_length=128)
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=20)
    extraction_method: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _truthful_status(self) -> FormationPick:
        if self.status is not TIER_STATUS[self.tier]:
            raise ValueError("pick status must match its tier")
        if self.status.value not in self.label.lower():
            raise ValueError("pick label must state its interpretation status")
        return self


class FormationUnsupportedPick(ContractModel):
    """A pick listed with its qualifier but not drawn (FO-2)."""

    pick_id: UUID
    wellbore_id: UUID | None = None
    surface_name: str | None = None
    qualifier: str | None = None
    reason: FormationBlockReason
    message: str = Field(min_length=1)
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=20)


class FormationConflict(ContractModel):
    """Engine TVD versus source TVD/TVDSS beyond tolerance; never silently resolved (FO-1)."""

    pick_id: UUID
    wellbore_id: UUID
    reason: FormationBlockReason
    message: str = Field(min_length=1)
    source_depth: DepthValue | None = None
    trajectory_depth: DepthValue | None = None
    difference: float | None = None
    difference_unit: str | None = None
    tolerance: float | None = Field(default=None, ge=0)


class PlaneFootprint(ContractModel):
    """Scene-footprint rectangle [m] the plane is bounded to (bounds plus margin)."""

    min_east: float
    max_east: float
    min_north: float
    max_north: float
    margin_m: float = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> PlaneFootprint:
        if self.min_east >= self.max_east or self.min_north >= self.max_north:
            raise ValueError("footprint minimums must be below maximums")
        return self


class LevelPlane(ContractModel):
    """T2 level plane: illustrative, at a pick's scene elevation."""

    elevation: DepthValue
    footprint: PlaneFootprint
    label: str = LEVEL_PLANE_LABEL
    note: str = LEVEL_PLANE_NOTE
    status: InterpretationStatus = InterpretationStatus.ILLUSTRATIVE
    source_pick_id: UUID | None = None

    @model_validator(mode="after")
    def _scene_elevation(self) -> LevelPlane:
        if "illustrative" not in self.label.lower():
            raise ValueError("a level plane label must say 'illustrative'")
        if "not an interpreted horizon" not in self.note.lower():
            raise ValueError("a level plane note must say it is not an interpreted horizon")
        if self.elevation.reference is not DepthReference.SCENE_ELEVATION:
            raise ValueError("a level plane is placed at a scene elevation")
        if self.elevation.value is None:
            raise ValueError("a level plane requires a known elevation")
        if self.status is not InterpretationStatus.ILLUSTRATIVE:
            raise ValueError("a level plane is illustrative")
        return self


class SurfaceMesh(ContractModel):
    """T3 interpolated mesh (scene frame, metres), inside the picks' convex hull only."""

    positions: list[float] = Field(
        min_length=9,
        max_length=MAX_MESH_VERTICES * 3,
        description="Flat xyz triples [east, north, up].",
    )
    indices: list[int] = Field(
        min_length=3, max_length=MAX_MESH_TRIANGLES * 3, description="Flat vertex index triples."
    )
    method: str = Field(
        min_length=1, max_length=128, description="Interpolation method shown on screen."
    )
    method_version: str | None = None
    support_polygon: list[list[float]] = Field(
        min_length=3,
        max_length=1000,
        description="Convex-hull [east, north] vertices; no extrapolation.",
    )
    pick_ids: list[UUID] = Field(min_length=3, max_length=MAX_PICKS_PER_SURFACE)
    status: InterpretationStatus = InterpretationStatus.INTERPOLATED

    @model_validator(mode="after")
    def _shape(self) -> SurfaceMesh:
        if len(self.positions) % 3 or len(self.indices) % 3:
            raise ValueError("positions and indices must be multiples of three")
        vertex_count = len(self.positions) // 3
        if any(i < 0 or i >= vertex_count for i in self.indices):
            raise ValueError("mesh index out of range")
        if any(len(p) != 2 or not all(isfinite(c) for c in p) for p in self.support_polygon):
            raise ValueError("support polygon vertices are finite [east, north]")
        pos = self.positions
        for t in range(0, len(self.indices), 3):
            a, b, c = self.indices[t : t + 3]
            if a == b or b == c or a == c:
                raise ValueError("degenerate triangle: repeated vertex index")
            cross = (pos[3 * b] - pos[3 * a]) * (pos[3 * c + 1] - pos[3 * a + 1]) - (
                pos[3 * b + 1] - pos[3 * a + 1]
            ) * (pos[3 * c] - pos[3 * a])
            if abs(cross) < 1e-12:
                raise ValueError("degenerate triangle: zero horizontal area")
        if self.status is not InterpretationStatus.INTERPOLATED:
            raise ValueError("a T3 mesh is interpolated")
        return self


class FormationSurface(ContractModel):
    """One surface at its highest drawable tier; lower tiers are not drawn alongside it."""

    surface_key: str = Field(min_length=1, max_length=256)
    name: str = Field(min_length=1, max_length=256)
    tier: FormationTier
    tier_label: str = Field(
        min_length=1,
        max_length=128,
        description="Always shown, for example 'T2 level plane - illustrative'.",
    )
    status: InterpretationStatus
    scope: FormationScope
    wellbore_ids: list[UUID] = Field(min_length=1, max_length=200)
    picks: list[FormationPick] = Field(default_factory=list, max_length=MAX_PICKS_PER_SURFACE)
    plane: LevelPlane | None = None
    mesh: SurfaceMesh | None = None
    blocked: list[FormationBlocked] = Field(
        default_factory=list,
        description="Reasons the plane/mesh is not drawn; picks may still show.",
    )
    evidence: list[EvidenceLink] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def _tier_consistent(self) -> FormationSurface:
        if self.status is not TIER_STATUS[self.tier]:
            raise ValueError("interpretation status must match the tier")
        if self.tier is FormationTier.T2 and self.plane is None:
            raise ValueError("a T2 surface requires a level plane")
        if self.tier is FormationTier.T3 and self.mesh is None:
            raise ValueError("a T3 surface requires a mesh")
        if self.tier in {FormationTier.T1, FormationTier.T4} and (self.plane or self.mesh):
            raise ValueError("T1/T4 surfaces carry neither plane nor mesh here")
        if self.tier is FormationTier.T2 and self.mesh is not None:
            raise ValueError("only the highest tier is carried")
        if self.scope is FormationScope.WELLBORE and len(self.wellbore_ids) != 1:
            raise ValueError("a wellbore-scoped surface names exactly one wellbore")
        if self.tier is FormationTier.T2 and self.tier_label != LEVEL_PLANE_LABEL:
            raise ValueError(f"a T2 surface must be labeled {LEVEL_PLANE_LABEL!r}")
        if self.tier is not FormationTier.T2 and "illustrative" in self.tier_label.lower():
            raise ValueError("only T2 surfaces are labeled illustrative")
        allowed = set(self.wellbore_ids)
        if any(p.wellbore_id not in allowed for p in self.picks):
            raise ValueError("pick belongs to a wellbore not named by the surface")
        return self

    @property
    def spans_wellbores(self) -> bool:
        return self.scope is FormationScope.PROJECT or len(set(self.wellbore_ids)) > 1


class FormationFrame(ContractModel):
    """Scene frame the layer is expressed in; no datum is assumed."""

    origin_enu: list[float] | None = Field(default=None, min_length=3, max_length=3)
    horizontal_crs: str | None = None
    length_unit: str = Field(default="m", min_length=1)
    vertical_reference: str | None = Field(
        default=None, description="Shared vertical reference name; null when unknown or differing."
    )
    vertical_reference_status: DatumStatus = DatumStatus.UNKNOWN
    exaggeration_neutral: bool = Field(
        default=True,
        description="Geometry is unexaggerated; the viewer applies vertical exaggeration.",
    )
    tvd_tolerance_m: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _reference(self) -> FormationFrame:
        if self.vertical_reference_status is DatumStatus.STATED and not self.vertical_reference:
            raise ValueError("a stated shared vertical reference needs its name")
        if self.vertical_reference_status is not DatumStatus.STATED and self.vertical_reference:
            raise ValueError("a vertical reference name requires status stated")
        return self


class FormationLayerSet(ContractModel):
    project_id: UUID
    wellbore_id: UUID | None = Field(
        default=None, description="Selected wellbore, or null for the project-wide set."
    )
    frame: FormationFrame
    surfaces: list[FormationSurface] = Field(default_factory=list, max_length=MAX_SURFACES)
    conflicts: list[FormationConflict] = Field(default_factory=list)
    unsupported: list[FormationUnsupportedPick] = Field(default_factory=list)
    blocked: list[FormationBlocked] = Field(
        default_factory=list,
        description="Layer-level blocks, for example differing vertical references.",
    )
    empty_reason: str | None = Field(
        default=None,
        description="Set (for example 'no formation picks in this project') when nothing is drawn.",
    )
    generated_from_revision: str = Field(
        min_length=1, description="Cache/revision key of the inputs."
    )

    @model_validator(mode="after")
    def _shared_reference(self) -> FormationLayerSet:
        if (
            self.frame.vertical_reference_status is DatumStatus.STATED
            and self.frame.vertical_reference
        ):
            return self
        datum_reasons = {FormationBlockReason.UNKNOWN_DATUM, FormationBlockReason.DATUM_MISMATCH}
        for surface in self.surfaces:
            if not surface.spans_wellbores:
                continue
            if (
                surface.plane
                or surface.mesh
                or not any(b.reason in datum_reasons for b in surface.blocked)
            ):
                raise ValueError(
                    f"surface {surface.surface_key} spans several wellbores without a shared "
                    "stated vertical reference; it must carry a datum block and no geometry"
                )
        return self

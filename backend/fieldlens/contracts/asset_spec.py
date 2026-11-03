"""``VisualAssetSpec`` (TASK-077, WELLBORE_ASSET_GENERATION section 5): a declarative, visual-only
description of one wellbore's equipment that a deterministic renderer turns into geometry.

Nothing here is an engineering input: ``visual_only`` is the constant ``true``, generic components
carry no numbers, and unknown placement is the explicit ``unlocated`` state (never an invented
depth). Reference URLs are plain strings the application never fetches; a stored image is a bounded
file *reference* (content type and size limited), not bytes.
"""

from __future__ import annotations

import unicodedata
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from .base import ContractModel, UtcDatetime

MAX_COMPONENTS = 200
MAX_EVIDENCE = 8
MAX_FINDINGS = 200
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_CONTENT_TYPES = ("image/png", "image/jpeg", "image/webp")
_INVISIBLE = frozenset({"Cf", "Cc", "Zs", "Zl", "Zp"})
COMPONENT_ID_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,63}$"


class ComponentKind(StrEnum):
    """Closed enum of registered render primitives; unknown kinds are rejected."""

    CASING = "casing"
    LINER = "liner"
    TUBING = "tubing"
    PACKER = "packer"
    PUMP_ESP = "pump_esp"
    BEARING = "bearing"
    PLUG = "plug"
    NIPPLE = "nipple"
    VALVE = "valve"
    MANDREL = "mandrel"
    PERFORATION_INTERVAL = "perforation_interval"
    WELLHEAD = "wellhead"
    CHRISTMAS_TREE = "christmas_tree"
    GENERIC_BLOCK = "generic_block"
    SEPARATOR = "separator"
    CHOKE = "choke"
    MANIFOLD = "manifold"
    TANK = "tank"
    FLOWLINE = "flowline"
    PUMP_SURFACE = "pump_surface"


SURFACE_KINDS = frozenset(
    {
        ComponentKind.SEPARATOR,
        ComponentKind.CHOKE,
        ComponentKind.MANIFOLD,
        ComponentKind.TANK,
        ComponentKind.FLOWLINE,
        ComponentKind.PUMP_SURFACE,
    }
)
"""Facilities above ground: placement is ``surface`` or ``unlocated``, never an MD interval."""
SURFACE_OR_MD_KINDS = frozenset({ComponentKind.WELLHEAD, ComponentKind.CHRISTMAS_TREE})
"""May be located at MD (top of hole) or placed at the surface."""


class Representation(StrEnum):
    SOURCE_DIMENSIONED = "source_dimensioned"
    """Dimensions come from cited evidence (needs at least one evidence reference)."""
    CATALOG_REFERENCE = "catalog_reference"
    """Shape follows a documented manufacturer/model; not evidence of installation."""
    GENERIC_ILLUSTRATIVE = "generic_illustrative"
    """A labelled placeholder; carries no numbers."""


class SpecStatus(StrEnum):
    """No draft/accept gate: the latest valid generated spec is shown directly."""

    CURRENT = "current"
    SUPERSEDED = "superseded"


class SpecState(StrEnum):
    """Persistence state of one stored revision."""

    CURRENT = "current"
    """The latest valid generation for the wellbore (exactly one)."""
    SUPERSEDED = "superseded"
    """An earlier valid generation, kept as history."""
    INVALIDATED = "invalidated"
    """Dropped because the identity/merge basis changed (merge revert hook)."""


class LengthUnit(StrEnum):
    M = "m"
    FT = "ft"


class SizeUnit(StrEnum):
    MM = "mm"
    IN = "in"
    M = "m"
    FT = "ft"


class DepthReference(StrEnum):
    MD = "MD"
    """Only measured depth is renderable; other references are stored as ``unlocated``."""


class FindingCode(StrEnum):
    SPEC_TOO_LARGE = "spec_too_large"
    HEADER_INVALID = "header_invalid"
    TOO_MANY_COMPONENTS = "too_many_components"
    UNKNOWN_KIND = "unknown_kind"
    SCHEMA_INVALID = "schema_invalid"
    DUPLICATE_ID = "duplicate_id"
    PARAM_NOT_ALLOWED = "param_not_allowed"
    PARAM_OUT_OF_BOUNDS = "param_out_of_bounds"
    OUT_OF_MD_RANGE = "out_of_md_range"
    MISSING_EVIDENCE = "missing_evidence"
    GENERIC_DIMENSIONED = "generic_dimensioned"
    PLACEMENT_NOT_ALLOWED = "placement_not_allowed"
    LABEL_EMPTY = "label_empty"
    CONTROL_CHARACTER = "control_character"


class SizeQuantity(ContractModel):
    value: float = Field(gt=0, description="Positive finite number in ``unit``.")
    unit: SizeUnit


class ComponentParams(ContractModel):
    """Bounded numeric params. Which of them a kind accepts is checked by the validator."""

    od: SizeQuantity | None = Field(default=None, description="Outside diameter.")
    id: SizeQuantity | None = Field(default=None, description="Inside diameter (below ``od``).")
    length: SizeQuantity | None = Field(default=None, description="Body length (or height).")


class Located(ContractModel):
    state: Literal["located"] = "located"
    md_top: float = Field(ge=0, le=100_000)
    md_bottom: float = Field(ge=0, le=100_000)
    unit: LengthUnit
    depth_reference: DepthReference = DepthReference.MD

    @model_validator(mode="after")
    def _ordered(self) -> Located:
        if self.md_top >= self.md_bottom:
            raise ValueError("md_top must be above md_bottom")
        return self


class Unlocated(ContractModel):
    """Placement unknown: shown in a side preview, never at an invented depth."""

    state: Literal["unlocated"] = "unlocated"
    reason: str | None = Field(default=None, max_length=200)


class Surface(ContractModel):
    """Above ground, near the wellhead. The offset is an optional local layout hint in metres
    (east/north of the wellhead), never a surveyed position."""

    state: Literal["surface"] = "surface"
    offset_east_m: float | None = Field(default=None, ge=-1000, le=1000)
    offset_north_m: float | None = Field(default=None, ge=-1000, le=1000)


Placement = Annotated[Located | Unlocated | Surface, Field(discriminator="state")]


class EvidenceRef(ContractModel):
    """Where a component's facts come from: a document (page, quote) and/or a candidate."""

    document_id: UUID | None = None
    page: int | None = Field(default=None, ge=1, le=100_000)
    quote: str | None = Field(default=None, max_length=400)
    candidate_id: UUID | None = None
    # Readable fields, filled at read time from stored rows (never stored, never document I/O).
    filename: str | None = Field(default=None, max_length=512)
    locator: str | None = Field(
        default=None, max_length=200, description="e.g. 'page 3, table 2, row 5' or 'line 14'."
    )
    statement: str | None = Field(
        default=None, max_length=300, description="Short readable statement of the source record."
    )

    @model_validator(mode="after")
    def _anchored(self) -> EvidenceRef:
        if self.document_id is None and self.candidate_id is None:
            raise ValueError("evidence needs a document_id or a candidate_id")
        return self


class StoredImageRef(ContractModel):
    """A bounded image file kept outside the database (reference only; fetching is a later lane)."""

    storage_key: str = Field(min_length=1, max_length=256)
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    size_bytes: int = Field(gt=0, le=MAX_IMAGE_BYTES)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class VisualReference(ContractModel):
    """An external visual reference: untrusted data, "not evidence of installation"."""

    url: str | None = Field(default=None, max_length=2048, pattern=r"^https?://\S+$")
    title: str | None = Field(default=None, max_length=200)
    retrieved_at: UtcDatetime | None = None
    note: str | None = Field(default=None, max_length=600)
    image: StoredImageRef | None = None

    @model_validator(mode="after")
    def _has_target(self) -> VisualReference:
        if self.url is None and self.image is None:
            raise ValueError("a visual reference needs a url or a stored image")
        return self


class AssetComponent(ContractModel):
    id: str = Field(pattern=COMPONENT_ID_PATTERN)
    kind: ComponentKind
    label: str = Field(min_length=1, max_length=120, description="Visible name; never blank.")
    placement: Placement
    params: ComponentParams | None = None
    representation: Representation
    evidence: list[EvidenceRef] = Field(default_factory=list, max_length=MAX_EVIDENCE)
    visual_reference: VisualReference | None = None
    confidence_note: str | None = Field(
        default=None, max_length=300, description="Free text, never proof."
    )

    @model_validator(mode="after")
    def _honest(self) -> AssetComponent:
        if not any(unicodedata.category(ch) not in _INVISIBLE for ch in self.label):
            raise ValueError("label is blank")
        if self.kind in SURFACE_KINDS and isinstance(self.placement, Located):
            raise ValueError("placement not allowed: surface facilities have no MD")
        if (
            isinstance(self.placement, Surface)
            and self.kind not in SURFACE_KINDS
            and self.kind not in SURFACE_OR_MD_KINDS
        ):
            raise ValueError("placement not allowed: only surface items sit at the surface")
        rep = self.representation
        if rep == Representation.SOURCE_DIMENSIONED:
            if not self.evidence:
                raise ValueError("source_dimensioned needs evidence")
            if self.kind == ComponentKind.GENERIC_BLOCK:
                raise ValueError("a generic_block is never source_dimensioned")
        if rep == Representation.GENERIC_ILLUSTRATIVE and self.params is not None:
            raise ValueError("generic_illustrative carries no numbers")
        return self


class SpecGenerator(ContractModel):
    provider: str = Field(min_length=1, max_length=40)
    model: str = Field(min_length=1, max_length=80)
    run_id: str | None = Field(default=None, max_length=64)


class SpecFinding(ContractModel):
    """Why a component (or the whole document) was dropped; never a silent repair."""

    code: FindingCode
    component_id: str | None = Field(default=None, max_length=64)
    index: int | None = Field(default=None, ge=0, description="Position in the submitted list.")
    message: str = Field(max_length=240)


class VisualAssetSpec(ContractModel):
    project_id: UUID
    wellbore_id: UUID
    source_revision: str = Field(min_length=1, max_length=64)
    identity_revision: str | None = Field(
        default=None, max_length=64, description="Identity/merge basis the spec was built on."
    )
    spec_version: Literal["1"] = "1"
    generator: SpecGenerator
    generated_at: UtcDatetime
    status: SpecStatus
    visual_only: Literal[True] = True
    """Constant: nothing in a spec feeds calculations or published claims."""
    components: list[AssetComponent] = Field(default_factory=list, max_length=MAX_COMPONENTS)
    findings: list[SpecFinding] = Field(default_factory=list, max_length=MAX_FINDINGS)


class VisualAssetSpecRecord(ContractModel):
    """One stored revision of a wellbore's spec."""

    spec_id: UUID
    revision: int = Field(ge=1)
    state: SpecState
    created_at: UtcDatetime
    spec: VisualAssetSpec


class AssetSpecGenerateRequest(ContractModel):
    """Stub-designer input. The MD range (from the trajectory, when known) bounds located parts."""

    md_min: float | None = Field(default=None, ge=0, le=100_000)
    md_max: float | None = Field(default=None, ge=0, le=100_000)

    @model_validator(mode="after")
    def _ordered(self) -> AssetSpecGenerateRequest:
        if (self.md_min is None) != (self.md_max is None):
            raise ValueError("md_min and md_max go together")
        if self.md_min is not None and self.md_max is not None and self.md_min >= self.md_max:
            raise ValueError("md_min must be below md_max")
        return self


class AssetSpecHistory(ContractModel):
    """All stored revisions of a wellbore's spec, newest first (the current one is first when any)."""

    items: list[VisualAssetSpecRecord]

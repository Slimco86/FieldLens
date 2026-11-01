"""Evidence, locators, quantities, coverage and claims."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, Field, RootModel, field_validator, model_validator

from .base import ContractModel, UtcDatetime


class EvidenceClass(StrEnum):
    """Provenance class. No class implies validation."""

    SOURCE_RECORD = "source_record"
    CATALOG_DERIVED = "catalog_derived"
    DERIVED = "derived"
    INTERPOLATED = "interpolated"
    GENERIC = "generic"
    MODEL_PROPOSAL = "model_proposal"
    """Proposed by a model and checked by deterministic validators (AX-2); never source truth."""


class ValidationState(StrEnum):
    UNREVIEWED = "unreviewed"
    VALID = "valid"
    CONFLICTING = "conflicting"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"
    UNVERIFIED = "unverified"
    """Model-read from a page image with no text layer (AX-13): no quote could be checked."""


class CoverageStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class Coverage(ContractModel):
    status: CoverageStatus
    unit: Literal["page", "record", "cell", "line"] | None = None
    inspected: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    missing_ranges: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> Coverage:
        if self.inspected is not None and self.total is not None and self.inspected > self.total:
            raise ValueError("inspected count cannot exceed total")
        if self.status is CoverageStatus.COMPLETE and (
            self.total is None or self.inspected != self.total
        ):
            raise ValueError("complete coverage requires inspected == total (both known)")
        if (
            self.status is CoverageStatus.UNKNOWN
            and self.inspected is not None
            and not self.reasons
        ):
            raise ValueError("unknown coverage with an inspected count needs a reason")
        return self


# --- Locators ---------------------------------------------------------------------------


class _LocatorBase(ContractModel):
    document_id: UUID
    source_revision_id: UUID


def _normalized_rect(value: list[float]) -> list[float]:
    x0, y0, x1, y1 = value
    if not all(0.0 <= v <= 1.0 for v in value) or x0 >= x1 or y0 >= y1:
        raise ValueError("region must be normalized within [0,1] with x0<x1 and y0<y1")
    return value


NormalizedRect = Annotated[
    list[float], Field(min_length=4, max_length=4), AfterValidator(_normalized_rect)
]


class PdfLocator(_LocatorBase):
    kind: Literal["pdf"] = "pdf"
    page: int = Field(ge=1)
    table_id: str | None = None
    cell_id: str | None = None
    rect: NormalizedRect | None = Field(
        default=None, description="[x0,y0,x1,y1] normalized, top-left origin."
    )


class XlsxLocator(_LocatorBase):
    kind: Literal["xlsx"] = "xlsx"
    sheet: str = Field(min_length=1)
    cell_range: str = Field(min_length=1, description="A1 cell or range.")


class XmlLocator(_LocatorBase):
    kind: Literal["xml"] = "xml"
    namespace_uri: str | None = None
    element_path: str = Field(min_length=1, description="Descriptive path; never evaluated.")
    source_uids: list[str] = Field(default_factory=list)
    attribute_name: str | None = None


class TextLocator(_LocatorBase):
    kind: Literal["text"] = "text"
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)
    logical_record: int | None = Field(default=None, ge=1)
    column_name: str | None = None
    las_section: str | None = None
    las_mnemonic: str | None = None
    las_data_line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> TextLocator:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self


class ConvertedTextLocator(_LocatorBase):
    kind: Literal["converted_text"] = "converted_text"
    artifact_id: UUID
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_version: str = Field(min_length=1)
    line_start: int = Field(ge=1)
    line_end: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> ConvertedTextLocator:
        if self.line_end < self.line_start:
            raise ValueError("line_end must be >= line_start")
        return self


class EmbeddedImageLocator(_LocatorBase):
    kind: Literal["embedded_image"] = "embedded_image"
    container_item_index: int = Field(ge=0)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    region: NormalizedRect | None = None


class DerivationLocator(ContractModel):
    kind: Literal["derivation"] = "derivation"
    result_id: UUID
    input_claim_ids: list[UUID] = Field(min_length=1)


class Locator(
    RootModel[
        Annotated[
            PdfLocator
            | XlsxLocator
            | XmlLocator
            | TextLocator
            | ConvertedTextLocator
            | EmbeddedImageLocator
            | DerivationLocator,
            Field(discriminator="kind"),
        ]
    ]
):
    """Closed locator variants keyed by ``kind``."""


class EvidenceLink(ContractModel):
    """A typed link to the exact evidence location; no free-form paths or URLs."""

    document_id: UUID | None = None
    source_revision_id: UUID | None = None
    record_id: UUID | None = None
    locator: Locator

    @model_validator(mode="after")
    def _source_ids_agree(self) -> EvidenceLink:
        source = self.locator.root
        if isinstance(source, _LocatorBase) and (
            self.document_id != source.document_id
            or self.source_revision_id != source.source_revision_id
        ):
            raise ValueError("source evidence link IDs must match its nested locator")
        return self


# --- Quantities and claims --------------------------------------------------------------


class Quantity(ContractModel):
    """Original value/unit/reference; unknown values are null with a reason, never zero."""

    value: float | None = None
    unit: str | None = None
    reference: str | None = None
    original_text: str | None = None
    unknown_reason: str | None = None
    normalized_value: float | None = None
    normalized_unit: str | None = None
    conversion_validated: bool = False

    @field_validator("unit", "normalized_unit", "unknown_reason")
    @classmethod
    def _nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("quantity units and unknown reasons must not be blank")
        return value

    @model_validator(mode="after")
    def _unknown_or_known(self) -> Quantity:
        if self.value is None:
            if not self.unknown_reason:
                raise ValueError("unknown quantity (value null) requires unknown_reason")
            if self.normalized_value is not None or self.conversion_validated:
                raise ValueError("unknown quantity cannot carry a normalized value")
        elif self.unit is None:
            raise ValueError("known quantity requires its original unit")
        if self.normalized_value is not None and not (
            self.conversion_validated and self.normalized_unit
        ):
            raise ValueError("normalized value requires validated conversion and unit")
        return self


class QuantityValue(ContractModel):
    kind: Literal["quantity"] = "quantity"
    quantity: Quantity


class TextValue(ContractModel):
    kind: Literal["text"] = "text"
    text: str


class BooleanValue(ContractModel):
    kind: Literal["boolean"] = "boolean"
    value: bool


class ClaimValue(
    RootModel[Annotated[QuantityValue | TextValue | BooleanValue, Field(discriminator="kind")]]
):
    """Typed claim value variants; arbitrary JSON is never accepted as engineering truth."""


INSTALLED_PREFIX = "installed."
NON_INSTALLED_CLASSES = frozenset({EvidenceClass.GENERIC, EvidenceClass.CATALOG_DERIVED})


class SubjectType(StrEnum):
    FIELD = "field"
    WELL = "well"
    WELLBORE = "wellbore"
    COMPLETION = "completion"
    COMPONENT = "component"
    INTERVAL = "interval"


class Claim(ContractModel):
    claim_id: UUID
    project_id: UUID
    revision_id: UUID
    subject_id: UUID
    subject_type: SubjectType
    attribute_key: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    value: ClaimValue
    source_record_ids: list[UUID] = Field(default_factory=list)
    validation_state: ValidationState = ValidationState.UNREVIEWED
    evidence_class: EvidenceClass
    superseded_claim_id: UUID | None = None

    @model_validator(mode="after")
    def _authority(self) -> Claim:
        if self.attribute_key.startswith(INSTALLED_PREFIX):
            if self.evidence_class in NON_INSTALLED_CLASSES:
                raise ValueError(
                    "generic or catalog-derived evidence cannot be an authoritative installed "
                    "measurement; use a catalog.* or generic.* attribute key"
                )
            if self.evidence_class is EvidenceClass.SOURCE_RECORD and not self.source_record_ids:
                raise ValueError("source_record evidence requires source_record_ids")
        for evidence_class, prefix in (
            (EvidenceClass.GENERIC, "generic."),
            (EvidenceClass.CATALOG_DERIVED, "catalog."),
        ):
            if (self.evidence_class is evidence_class) != self.attribute_key.startswith(prefix):
                raise ValueError(
                    f"{evidence_class.value} evidence requires a matching {prefix} key"
                )
        return self


class DerivedResult(ContractModel):
    result_id: UUID
    algorithm: str
    algorithm_version: str
    input_claim_ids: list[UUID] = Field(min_length=1)
    input_revision_ids: list[UUID] = Field(min_length=1)
    parameters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    tolerance: Quantity | None = None
    output_artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_at: UtcDatetime

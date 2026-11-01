"""Model-proposed extraction candidates (TASK-036, AX-1..9, AX-12..15).

A candidate is a *proposal*: the model suggested it, deterministic validators decided its state.
``accepted`` needs every validator to pass and no parsed value to disagree; ``model_read``
candidates (page image without a text layer) are never accepted and stay ``unverified``. Original
text and units are kept as written; ``attributes`` is a typed payload with a ``kind``
discriminator so later categories (TASK-041) add a variant without a migration."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from .base import ContractModel, UtcDatetime
from .context import PageInfo, PageParams
from .evidence import EvidenceClass, EvidenceLink, ValidationState


class CandidateState(StrEnum):
    CANDIDATE = "candidate"
    """Proposed, not decided (always the state of a ``model_read`` candidate without a flag)."""
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FLAGGED = "flagged"


class ExtractionMethod(StrEnum):
    MODEL_PROPOSAL = "model_proposal"
    """Proposed from text-layer content; the quote is checked against the cited span."""
    MODEL_READ = "model_read"
    """Read from a page image with no text layer; unverified by construction."""


class ReasonCode(StrEnum):
    LOCATOR_NOT_FOUND = "locator_not_found"
    LOCATOR_UNSUPPORTED = "locator_unsupported"
    QUOTE_MISSING = "quote_missing"
    QUOTE_NOT_IN_SPAN = "quote_not_in_span"
    VALUE_NOT_IN_QUOTE = "value_not_in_quote"
    ATTRIBUTE_UNKNOWN = "attribute_unknown"
    UNIT_UNPARSEABLE = "unit_unparseable"
    UNIT_DIMENSION_MISMATCH = "unit_dimension_mismatch"
    UNIT_DEFAULTED_METERS = "unit_defaulted_meters"
    OUT_OF_RANGE = "out_of_range"
    MD_TVD_CONFUSION = "md_tvd_confusion"
    COMPOUND_DEPTH_PAIR = "compound_depth_pair"
    SUBJECT_UNRESOLVED = "subject_unresolved"
    SUBJECT_DOCUMENT_MISMATCH = "subject_document_mismatch"
    PARSED_CONFLICT = "parsed_conflict"
    CRS_NOT_STATED = "crs_not_stated"
    DATE_NOT_IN_SOURCE = "date_not_in_source"
    MODEL_READ_UNVERIFIED = "model_read_unverified"
    UNIT_CONFLICTS_WITH_QUOTE = "unit_conflicts_with_quote"
    UNIT_NOT_IN_SOURCE = "unit_not_in_source"
    NUMBER_UNPARSEABLE = "number_unparseable"
    FIELD_UNVERIFIED = "field_unverified"
    COORDINATE_FALLBACK_UNSUPPORTED = "coordinate_fallback_unsupported"
    UNIT_AWAY_FROM_VALUE = "unit_away_from_value"
    SIZE_AMBIGUOUS = "size_ambiguous"
    SUBJECT_PAGE_NAMES_OTHER_WELL = "subject_page_names_other_well"
    FIELD_NOT_ASSOCIATED = "field_not_associated"
    ID_EXCEEDS_OD = "id_exceeds_od"
    DEPTH_ORDER_INVALID = "depth_order_invalid"
    LABEL_NOT_IN_TEXT_LAYER = "label_not_in_text_layer"
    EQUIPMENT_NOT_ON_PAGE = "equipment_not_on_page"


class ValidatorName(StrEnum):
    LOCATOR = "locator"
    QUOTE = "quote"
    ATTRIBUTE = "attribute"
    UNIT = "unit"
    RANGE = "range"
    DEPTH_REFERENCE = "depth_reference"
    SUBJECT = "subject"
    PARSED_CONFLICT = "parsed_conflict"
    PROVENANCE = "provenance"


class ValidatorOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    FLAGGED = "flagged"
    SKIPPED = "skipped"


class ValidatorResult(ContractModel):
    validator: ValidatorName
    outcome: ValidatorOutcome
    reason: ReasonCode | None = None
    detail: str | None = Field(default=None, max_length=300)


class MeasurementAttributes(ContractModel):
    """Generic proof class: one measured/stated value with its unit exactly as written."""

    kind: Literal["measurement"] = "measurement"
    attribute_key: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$", max_length=80)
    value_text: str = Field(max_length=200, description="The value exactly as written.")
    number: float | None = None
    unit_as_written: str | None = Field(default=None, max_length=32)
    unit_defaulted: bool = Field(
        default=False, description="True when the unit was defaulted to meters (a warning)."
    )
    unit_source: Literal["quote", "context", "claimed", "default"] | None = Field(
        default=None,
        description="Where the unit comes from: the quote (as written), a unit the cited context states "
        "(a table header), the model's claim "
        "(only when the quote states none and the context does not contradict it) or the "
        "meters default.",
    )
    depth_reference: Literal["MD", "TVD", "TVDSS"] | None = None
    normalized_number: float | None = None
    normalized_unit: str | None = None
    crs_text: str | None = Field(default=None, max_length=120)
    effective_time_text: str | None = Field(
        default=None, max_length=80, description="Date text exactly as written; never normalized."
    )


class PageReadAttributes(ContractModel):
    """Superficial, visual-level reading of a page image (AX-13); no value is trustworthy."""

    kind: Literal["page_read"] = "page_read"
    item_type: str = Field(max_length=64)
    name: str | None = Field(default=None, max_length=120)
    sizes_text: list[str] = Field(default_factory=list, max_length=8)
    depth_text: str | None = Field(default=None, max_length=80)
    notes: str | None = Field(default=None, max_length=300)
    dropped_fields: list[str] = Field(
        default_factory=list,
        description="Fields the model proposed that the text layer does not support; removed.",
    )


class EquipmentCategory(StrEnum):
    """EQ-8 closed taxonomy (owner, visual level). Drilling/BHA equipment has no category."""

    CASING = "casing"
    LINER = "liner"
    TUBING = "tubing"
    PACKER = "packer"
    PUMP = "pump"
    BEARING = "bearing"
    PERFORATION_INTERVAL = "perforation_interval"
    ISOLATION = "isolation"
    """Plug, cement or bridge plug."""
    COMPLETION_ACCESSORY = "completion_accessory"
    """Nipple, valve, mandrel, sleeve, centralizer, wellhead/tree."""
    OTHER = "other"


class EquipmentQuantity(ContractModel):
    """A size, length or depth exactly as printed (original text and unit are never replaced).

    ``normalized_*`` is a display convenience for plausibility checks only; it is never a
    calculation input (the candidate stays model-read and unverified)."""

    value_text: str = Field(max_length=40, description="The value exactly as printed.")
    unit_as_written: str | None = Field(default=None, max_length=16)
    unit_defaulted: bool = Field(
        default=False, description="True when a depth had no unit and meters were assumed."
    )
    depth_reference_text: str | None = Field(
        default=None, max_length=24, description="Depth reference as printed, e.g. 'MD RKB'."
    )
    depth_reference: Literal["MD", "TVD", "TVDSS"] | None = None
    number: float | None = None
    normalized_number: float | None = None
    normalized_unit: str | None = None
    issue: str | None = Field(default=None, max_length=120, description="Why it was flagged.")


class EquipmentAttributes(ContractModel):
    """Visual-level production/completion equipment read from a page (EQ-8). Every field except
    ``category`` is optional; unknown stays absent, never zero or guessed. The page locator is the
    candidate's evidence link; ``region`` (normalized x0, y0, x1, y1) is optional."""

    kind: Literal["equipment"] = "equipment"
    category: EquipmentCategory
    material: str | None = Field(default=None, max_length=60)
    od: EquipmentQuantity | None = None
    id: EquipmentQuantity | None = None
    length: EquipmentQuantity | None = None
    top_depth: EquipmentQuantity | None = None
    bottom_depth: EquipmentQuantity | None = None
    label_text: str | None = Field(default=None, max_length=120, description="Printed label.")
    description: str | None = Field(default=None, max_length=200)
    region: list[float] | None = Field(default=None, max_length=4)
    label_in_text_layer: bool | None = Field(
        default=None, description="Whether the printed label is in the page text layer, if any."
    )
    dropped_fields: list[str] = Field(default_factory=list)


CandidateAttributes = Annotated[
    MeasurementAttributes | PageReadAttributes | EquipmentAttributes,
    Field(discriminator="kind"),
]


class ExtractionCandidate(ContractModel):
    candidate_id: UUID
    project_id: UUID
    unit_id: UUID
    source_revision_id: UUID
    document_id: UUID
    wellbore_id: UUID | None = Field(
        default=None, description="Project wellbore identity; null stays unattached with a finding."
    )
    subject: dict[str, str | None]
    method: ExtractionMethod
    evidence_class: EvidenceClass
    validation_state: ValidationState
    state: CandidateState
    label: str = Field(description="Human label, e.g. 'model-read, unverified'.")
    reason_codes: list[ReasonCode]
    validator_results: list[ValidatorResult]
    attributes: CandidateAttributes
    quote: str | None = Field(default=None, max_length=400)
    evidence: EvidenceLink
    conflicts_with_record_id: UUID | None = Field(
        default=None, description="The parsed record that disagrees; it stays authoritative."
    )
    model_id: str
    prompt_version: str
    harness_version: str
    created_at: UtcDatetime


class ExtractionCandidatePage(ContractModel):
    items: list[ExtractionCandidate]
    page: PageInfo


class CandidateQuery(PageParams):
    """Listing filters; the project comes from the path."""

    document_id: UUID | None = None
    state: CandidateState | None = None
    method: ExtractionMethod | None = None
    wellbore_id: UUID | None = None
    category: EquipmentCategory | None = Field(
        default=None, description="Equipment candidates of this EQ-8 category only."
    )

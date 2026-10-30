"""Parser output types shared by every native profile (pure data, no I/O, no database).

A parser never decides validity beyond what the source proves: it preserves the original text,
unit and reference of every attribute, attaches the exact locator of that attribute, and reports
conflicts/gaps as ``Finding`` objects. Unknown values are ``None`` with a reason - never zero.
Locators are stored without document/revision ids (added when an ``EvidenceLink`` is built)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import UUID

ProfileStatus = Literal["succeeded", "partial", "failed"]
Locator = dict[str, Any]

# Hard resource ceilings shared by the profiles (untrusted input).
MAX_XML_BYTES = 64 * 1024 * 1024
MAX_XML_DEPTH = 64
MAX_XML_NODES = 2_000_000
MAX_XLSX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_TEXT_LINES = 2_000_000
MAX_RECORDS = 400_000


class ProfileError(Exception):
    """Unparseable or unsafe source. ``code`` becomes the persisted failure code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ParseContext:
    document_id: UUID
    source_revision_id: UUID
    sha256: str
    filename: str


@dataclass
class Attr:
    """One attribute with its own locator. ``original_text`` is the source text verbatim."""

    key: str
    locator: Locator
    original_text: str | None = None
    number: float | None = None
    unit: str | None = None
    unit_status: Literal["stated", "not_applicable", "missing"] = "not_applicable"
    reference: str | None = None
    text: str | None = None
    unknown_reason: str | None = None
    normalized_number: float | None = None
    normalized_unit: str | None = None
    validation_state: Literal["unreviewed", "conflicting", "invalid", "unsupported"] = "unreviewed"

    def to_json(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "locator": self.locator,
            "original_text": self.original_text,
            "number": self.number,
            "unit": self.unit,
            "unit_status": self.unit_status,
            "reference": self.reference,
            "text": self.text,
            "unknown_reason": self.unknown_reason,
            "normalized_number": self.normalized_number,
            "normalized_unit": self.normalized_unit,
            "validation_state": self.validation_state,
        }


@dataclass
class EventTime:
    """Effective (event) time as written in the source; precision is never widened."""

    literal: str
    precision: Literal["instant", "day", "month", "year", "unknown"]
    timezone_known: bool = False
    field: str | None = None  # source field name, e.g. dTimStart / DATEPRD
    timezone: str | None = None  # "UTC" for a Z designator, "UTC+02:00" for an offset; else unknown


@dataclass
class Rec:
    kind: str
    subject: dict[str, Any]
    locator: Locator
    attrs: list[Attr] = field(default_factory=list)
    effective_time: EventTime | None = None
    report_time: EventTime | None = None  # report/creation time, kept apart from effective time
    validation_state: Literal["unreviewed", "conflicting", "invalid", "unsupported"] = "unreviewed"
    ordinal: int = 0

    def attr(self, key: str) -> Attr | None:
        for a in self.attrs:
            if a.key == key:
                return a
        return None


@dataclass
class Finding:
    """A data-quality finding. ``record_ordinals`` index into the output ``records``."""

    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    key: str  # deterministic idempotency key within the run
    attribute_keys: list[str] = field(default_factory=list)
    record_ordinals: list[int] = field(default_factory=list)
    locators: list[Locator] = field(default_factory=list)
    blocked: list[str] = field(default_factory=list)


@dataclass
class CoverageOut:
    unit: Literal["page", "record", "cell", "line"]
    inspected: int
    total: int | None
    missing_ranges: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.total is not None and self.inspected == self.total and not self.reasons


@dataclass
class ProfileOutput:
    records: list[Rec]
    findings: list[Finding]
    coverage: CoverageOut
    status: ProfileStatus = "succeeded"
    detail: dict[str, Any] = field(default_factory=dict)


class Profile(Protocol):
    name: str
    version: str
    method: str
    families: tuple[str, ...]

    def detect(self, path: Path, format_family: str, filename: str) -> bool: ...

    def parse(self, path: Path, ctx: ParseContext) -> ProfileOutput: ...


# Registered shared issue codes used by profiles (see contracts/quality.py IssueCode).
MISSING_REFERENCE = "MISSING_REFERENCE"
MISSING_UNIT = "MISSING_UNIT"
SUSPICIOUS_VALUE = "SUSPICIOUS_VALUE"
UNKNOWN_CODE = "UNKNOWN_CODE"
ASSEMBLY_TYPE_MISMATCH = "ASSEMBLY_TYPE_MISMATCH"
REFERENCE_CONFLICT = "REFERENCE_CONFLICT"
INTERVAL_CONFLICT = "INTERVAL_CONFLICT"
IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
TEMPORAL_AMBIGUITY = "TEMPORAL_AMBIGUITY"
HISTORY_INCOMPLETE = "HISTORY_INCOMPLETE"
EXTRACTION_PARTIAL = "EXTRACTION_PARTIAL"
UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
EXTRACTION_FAILED = "EXTRACTION_FAILED"
DIMENSION_CONFLICT = "DIMENSION_CONFLICT"

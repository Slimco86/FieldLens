"""Upload, source list, classification and persistent-job DTOs (FL-005-A).

Storage verification is not extraction: no DTO here reports parsed content, pages or entities.
Categories, tags and filenames are user hints and never engineering evidence.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import AfterValidator, BeforeValidator, Field, model_validator

from .base import ContractModel, UtcDatetime
from .context import PageInfo
from .identity import SourceDocument, SourceRevision

MAX_TAGS = 20
MAX_TAG_LENGTH = 64
MAX_IMPORT_FILES = 200
IDEMPOTENCY_KEY_PATTERN = r"^[A-Za-z0-9._:~-]{1,128}$"


class DocumentCategory(StrEnum):
    """Hybrid-label keys confirmed October 28. Labels are hints, not entity identity."""

    TRAJECTORY = "trajectory"
    COMPLETION_EQUIPMENT = "completion_equipment"
    PERFORATION_HISTORY = "perforation_history"
    PRODUCTION_INJECTION = "production_injection"
    WELL_LOGS = "well_logs"
    GEOLOGY_RESERVOIR = "geology_reservoir"
    TERRAIN_BATHYMETRY = "terrain_bathymetry"
    GENERAL_REPORT = "general_report"


class StorageState(StrEnum):
    PENDING_VERIFICATION = "pending_verification"
    STORED = "stored"
    QUARANTINED = "quarantined"


class ExtractionState(StrEnum):
    """No reader exists in this slice: a file is pending extraction or explicitly unsupported."""

    PENDING_EXTRACTION = "pending_extraction"
    UNSUPPORTED = "unsupported"


class CategoriesOrigin(StrEnum):
    NONE = "none"
    UPLOAD_HINT = "upload_hint"
    USER_OVERRIDE = "user_override"


class JobKind(StrEnum):
    STORAGE_VERIFICATION = "storage_verification"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class AttemptStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    CANCELLED = "cancelled"


def _storable(value: Any) -> Any:
    if isinstance(value, str) and any(ch == "\x00" or "\ud800" <= ch <= "\udfff" for ch in value):
        raise ValueError("text must not contain NUL or unpaired surrogate characters")
    return value


def _trim(value: Any) -> Any:
    return _storable(value).strip() if isinstance(value, str) else value


Tag = Annotated[str, BeforeValidator(_trim), Field(min_length=1, max_length=MAX_TAG_LENGTH)]


def _unique(values: list[Any]) -> list[Any]:
    return list(dict.fromkeys(values))


Tags = Annotated[list[Tag], AfterValidator(_unique), Field(max_length=MAX_TAGS)]
Categories = Annotated[
    list[DocumentCategory], AfterValidator(_unique), Field(max_length=len(DocumentCategory))
]


class ImportFileMetadata(ContractModel):
    """Per-file hints for the *n*-th ``files`` part. Replacement is explicit, never by name."""

    categories: Categories = Field(default_factory=list)
    tags: Tags = Field(default_factory=list)
    replaces_document_id: UUID | None = None


class ImportMetadata(ContractModel):
    """The first multipart part (``metadata``, JSON). ``expected_parent_source_revision_id``
    must be sent (null for a first import); a stale parent returns 409."""

    expected_parent_source_revision_id: UUID | None
    idempotency_key: Annotated[str, Field(pattern=IDEMPOTENCY_KEY_PATTERN)] | None = None
    files: list[ImportFileMetadata] = Field(min_length=1, max_length=MAX_IMPORT_FILES)

    @model_validator(mode="after")
    def _distinct_replacements(self) -> ImportMetadata:
        targets = [f.replaces_document_id for f in self.files if f.replaces_document_id]
        if len(targets) != len(set(targets)):
            raise ValueError("a document can be replaced by at most one file per import")
        return self


class ImportAccepted(ContractModel):
    """HTTP 202 for a new import; 200 when the request was a replay or all-duplicate no-op."""

    source_revision_id: UUID
    job_id: UUID | None
    status: Literal["staging", "ready", "ready_with_issues", "failed"]
    deduplicated: bool
    """True when every file already belonged to the current source revision (no new records)."""
    replayed: bool
    """True when the idempotency key matched an earlier identical request."""
    document_ids: list[UUID]
    """Document IDs in request file order (duplicates map to their existing document)."""
    created_document_ids: list[UUID]


class DocumentClassification(ContractModel):
    """Suggested labels and user labels keep distinct origins; neither is engineering evidence."""

    user_categories: list[DocumentCategory]
    suggested_categories: list[DocumentCategory]
    tags: list[str]
    categories_origin: CategoriesOrigin
    classification_method: str
    classification_version: str
    metadata_version: int = Field(ge=1)
    updated_at: UtcDatetime


class ClassificationUpdate(ContractModel):
    """User override; ``expected_metadata_version`` guards against stale edits (409)."""

    categories: Categories
    tags: Tags
    expected_metadata_version: int = Field(ge=1)


class SourceDocumentItem(SourceDocument):
    """A project document as shown in the source list."""

    storage_state: StorageState
    extraction_state: ExtractionState
    processing_detail: str | None = None
    classification: DocumentClassification
    replaces_document_id: UUID | None = None
    source_revision_id: UUID
    """The revision whose membership this row was read from."""


class DocumentPage(ContractModel):
    items: list[SourceDocumentItem]
    page: PageInfo


class SourceRevisionSummary(SourceRevision):
    """Revision plus honest storage/extraction counts; ``quarantined_count`` is surfaced."""

    is_latest: bool
    member_count: int = Field(ge=0)
    stored_count: int = Field(ge=0)
    quarantined_count: int = Field(ge=0)
    pending_extraction_count: int = Field(ge=0)
    unsupported_count: int = Field(ge=0)
    job_id: UUID | None = None
    job_status: JobStatus | None = None


class SourceRevisionPage(ContractModel):
    items: list[SourceRevisionSummary]
    page: PageInfo


class JobProgress(ContractModel):
    """Processed/total when known; never a fake percentage."""

    processed: int | None = Field(default=None, ge=0)
    total: int | None = Field(default=None, ge=0)
    unit: str | None = None


class JobAttempt(ContractModel):
    attempt_no: int = Field(ge=1)
    status: AttemptStatus
    stage: str | None = None
    fencing_token: int = Field(ge=1)
    started_at: UtcDatetime
    heartbeat_at: UtcDatetime
    ended_at: UtcDatetime | None = None
    error_code: str | None = None


class JobResult(ContractModel):
    """Result of storage verification only. ``extraction_performed`` is always false here."""

    result_kind: Literal["storage_verification"]
    documents: int = Field(ge=0)
    stored: int = Field(ge=0)
    quarantined: int = Field(ge=0)
    pending_extraction: int = Field(ge=0)
    unsupported: int = Field(ge=0)
    extraction_performed: Literal[False]


class JobError(ContractModel):
    code: str
    message: str


class Job(ContractModel):
    job_id: UUID
    project_id: UUID
    kind: JobKind
    source_revision_id: UUID
    status: JobStatus
    stage: str | None = None
    progress: JobProgress
    cancel_requested: bool
    attempts: list[JobAttempt]
    result: JobResult | None = None
    error: JobError | None = None
    created_at: UtcDatetime
    updated_at: UtcDatetime
    finished_at: UtcDatetime | None = None

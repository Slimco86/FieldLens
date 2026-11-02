"""Project, revision, document and well/wellbore identity contracts."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .base import ContractModel, FiniteJsonValue, UtcDatetime
from .evidence import Coverage

SHA256_PATTERN = r"^[0-9a-f]{64}$"


class SourceRevisionStatus(StrEnum):
    STAGING = "staging"
    READY = "ready"
    READY_WITH_ISSUES = "ready_with_issues"
    FAILED = "failed"


class ModelRevisionStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PUBLISHED = "published"
    REJECTED = "rejected"


class ProjectDeletionState(StrEnum):
    """``none`` (normal), ``deleting`` (cancel/purge in progress) or ``failed`` (retryable)."""

    NONE = "none"
    DELETING = "deleting"
    FAILED = "failed"


class Project(ContractModel):
    """A project is a scope, not a field on other records."""

    project_id: UUID
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    created_at: UtcDatetime
    updated_at: UtcDatetime
    latest_source_revision_id: UUID | None = None
    active_model_revision_id: UUID | None = None
    deletion_state: ProjectDeletionState = ProjectDeletionState.NONE
    deletion_requested_at: UtcDatetime | None = None
    deletion_error: str | None = None

    @field_validator("name")
    @classmethod
    def _trimmed(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("name must be trimmed")
        return value


class SourceRevision(ContractModel):
    source_revision_id: UUID
    project_id: UUID
    parent_source_revision_id: UUID | None = None
    manifest_hash: str = Field(pattern=SHA256_PATTERN)
    created_at: UtcDatetime
    status: SourceRevisionStatus
    coverage: Coverage | None = None

    @model_validator(mode="after")
    def _not_self_parent(self) -> SourceRevision:
        if self.parent_source_revision_id == self.source_revision_id:
            raise ValueError("a revision cannot be its own parent")
        return self


class ModelRevision(ContractModel):
    revision_id: UUID
    project_id: UUID
    pinned_source_revision_id: UUID
    base_revision_id: UUID | None = None
    status: ModelRevisionStatus
    created_at: UtcDatetime
    coverage: Coverage | None = None

    @model_validator(mode="after")
    def _not_self_base(self) -> ModelRevision:
        if self.base_revision_id == self.revision_id:
            raise ValueError("a revision cannot be its own base")
        return self


class SourceDocument(ContractModel):
    """Original bytes live outside the database. The server-owned storage key is persisted
    but is never part of this client-facing contract."""

    document_id: UUID
    project_id: UUID
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    original_filename: str = Field(min_length=1, max_length=512)
    detected_media_type: str | None = None
    format_family: str = Field(default="unknown", max_length=32)
    """Detected container/format family from the file signature; never an engineering claim."""
    origin_metadata: dict[str, FiniteJsonValue] = Field(default_factory=dict)
    created_at: UtcDatetime


class Well(ContractModel):
    well_id: UUID
    project_id: UUID
    name: str = Field(min_length=1)


class Wellbore(ContractModel):
    """Distinct from Well; ``parent_wellbore_id`` links sidetracks (no cycles)."""

    wellbore_id: UUID
    project_id: UUID
    well_id: UUID
    parent_wellbore_id: UUID | None = None
    name: str = Field(min_length=1)

    @model_validator(mode="after")
    def _not_self_parent(self) -> Wellbore:
        if self.parent_wellbore_id == self.wellbore_id:
            raise ValueError("a wellbore cannot be its own parent")
        return self

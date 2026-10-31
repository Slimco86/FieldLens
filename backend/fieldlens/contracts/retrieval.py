"""Retrieval DTOs (TASK-011): bounded evidence search and source coverage in source mode.

Everything returned here is a *source observation*: a chunk of text rendered from extracted
records, carrying the extraction quality of those records. ``resolved_entity_id`` and
``claim_ids`` are explicit nulls/empty until a reconstruction publishes resolved claims, and a
hit is never an accepted engineering fact. ``evidence`` locators are the authority; the chunk
text is only a retrieval index entry."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from .base import ContractModel
from .context import ReadLimit
from .evidence import Coverage, EvidenceLink

MAX_EVIDENCE_CHUNKS = 10
MAX_CONTEXT_TOKENS = 12_000
MAX_QUERY_CHARS = 500


class EvidenceSearchQuery(ContractModel):
    """Typed arguments of the ``search_evidence`` tool and of the read endpoint."""

    q: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    source_revision_id: UUID | None = Field(
        default=None, description="Defaults to the project's latest source revision."
    )
    document_id: list[UUID] = Field(default_factory=list, max_length=20)
    limit: ReadLimit = Field(default=MAX_EVIDENCE_CHUNKS, ge=1, le=MAX_EVIDENCE_CHUNKS)


class SearchStatus(StrEnum):
    OK = "ok"
    NO_RESULTS = "no_results"
    AMBIGUOUS = "ambiguous"
    UNAVAILABLE = "unavailable"


class RetrievalMode(StrEnum):
    HYBRID = "hybrid"
    DEGRADED = "degraded"


class DegradedReason(StrEnum):
    EMBEDDER_DISABLED = "embedder_disabled"
    MODEL_MISSING = "model_missing"
    MODEL_LOAD_FAILED = "model_load_failed"
    EMBEDDER_BUSY = "embedder_busy"
    EMBEDDING_FAILED = "embedding_failed"
    VECTOR_INDEX_INCOMPLETE = "vector_index_incomplete"
    VECTOR_INDEX_PARTIAL = "vector_index_partial"
    NO_INDEXED_DOCUMENTS = "no_indexed_documents"


class IndexedState(StrEnum):
    NOT_INDEXABLE = "not_indexable"
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


class ExtractionQuality(ContractModel):
    run_status: str
    coverage_status: str = Field(description="complete, partial or unknown extraction coverage.")
    validation_states: dict[str, int] = Field(
        default_factory=dict, description="Record validation states in this chunk (unreviewed...)."
    )
    profile_name: str | None = None
    profile_version: str | None = None


class HitSignals(ContractModel):
    exact: bool
    lexical_rank: int | None = Field(default=None, ge=1)
    vector_rank: int | None = Field(default=None, ge=1)
    vector_similarity: float | None = None


class EvidenceHit(ContractModel):
    chunk_id: UUID
    rank: int = Field(ge=1)
    rrf_score: float
    signals: HitSignals
    label: Literal["source_observation"] = "source_observation"
    text: str
    token_count: int = Field(ge=1)
    kind: str
    document_id: UUID
    source_revision_id: UUID = Field(description="Revision the extraction run was made for.")
    record_ids: list[UUID]
    first_record_ordinal: int = Field(ge=0)
    last_record_ordinal: int = Field(ge=0)
    evidence: list[EvidenceLink] = Field(description="Locators of the records, first five.")
    extraction_quality: ExtractionQuality
    resolved_entity_id: UUID | None = None
    claim_ids: list[UUID] = Field(default_factory=list)


class ExactMatch(ContractModel):
    identifier: str
    canonical: str
    kinds: list[str]
    chunk_count: int = Field(ge=0)


class AmbiguityCandidate(ContractModel):
    canonical: str
    kinds: list[str]
    chunk_count: int = Field(ge=0)
    document_ids: list[UUID]


class IdentifierAmbiguity(ContractModel):
    identifier: str
    candidates: list[AmbiguityCandidate]


class IndexState(ContractModel):
    eligible_documents: int = Field(ge=0)
    text_indexed_documents: int = Field(ge=0)
    vector_indexed_documents: int = Field(ge=0)
    pending_documents: int = Field(ge=0)
    index_epoch: str = Field(description="Changes whenever indexed content in scope changes.")
    embedding_fingerprint: str | None = None


class EvidenceSearchResult(ContractModel):
    project_id: UUID
    source_revision_id: UUID | None
    query: str
    status: SearchStatus
    mode: RetrievalMode
    degraded_reasons: list[DegradedReason] = Field(default_factory=list)
    hits: list[EvidenceHit]
    returned_tokens: int = Field(ge=0)
    max_chunks: int = MAX_EVIDENCE_CHUNKS
    max_tokens: int = MAX_CONTEXT_TOKENS
    exact_matches: list[ExactMatch] = Field(default_factory=list)
    ambiguities: list[IdentifierAmbiguity] = Field(default_factory=list)
    unmatched_identifiers: list[str] = Field(
        default_factory=list, description="Identifier-shaped query tokens found in no source."
    )
    index: IndexState
    cache_key: str
    notes: list[str] = Field(default_factory=list)


class EmbeddingState(ContractModel):
    state: Literal["ready", "unavailable", "disabled"]
    code: str | None = None
    message: str | None = None
    fingerprint: str | None = None
    model_id: str | None = None
    model_revision: str | None = None
    dimension: int | None = None


class DocumentCoverage(ContractModel):
    document_id: UUID
    filename: str
    format_family: str
    extraction_status: str
    text_index: IndexedState
    vector_index: IndexedState
    chunk_count: int = Field(ge=0)
    embedded_count: int = Field(ge=0)
    extraction_coverage: Coverage | None = None
    not_indexed: list[str] = Field(
        default_factory=list, description="What is not searchable and why."
    )
    coverage_notes: list[str] = Field(
        default_factory=list, description="Explicit extraction gaps for this document."
    )


class SourceCoverage(ContractModel):
    project_id: UUID
    source_revision_id: UUID | None
    chunker_version: str
    embedding: EmbeddingState
    documents: list[DocumentCoverage]
    index: IndexState
    notes: list[str] = Field(default_factory=list)

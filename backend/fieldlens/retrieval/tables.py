"""Retrieval tables (migration 0007 is authoritative): derived, rebuildable index data.

Chunks, identifiers and embeddings are *derived* from ``extracted_record`` rows. The original
record stays the evidence authority; nothing here is an accepted engineering fact. Every row
carries ``project_id`` and uses composite foreign keys, so search can never cross projects.
Embeddings are keyed by chunk fingerprint + embedding fingerprint, so a changed model, dimension
or preprocessing creates a new index instead of reusing old vectors.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Column,
    Computed,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.types import UserDefinedType

from fieldlens.persistence.models import metadata


class Vector(UserDefinedType[Any]):
    """pgvector ``vector`` (unconstrained; the per-row ``dimension`` column is checked)."""

    cache_ok = True

    def get_col_spec(self, **kw: Any) -> str:
        return "vector"


# Reflection of ``vector`` columns (migration comparison) resolves to this type.
postgresql.base.ischema_names["vector"] = Vector

INDEX_KINDS = ("chunks", "embeddings")
INDEX_STATUSES = ("queued", "running", "complete", "failed", "interrupted")
MAX_CHUNK_TOKENS = 800


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


retrieval_index = Table(
    "retrieval_index",
    metadata,
    Column(
        "index_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("chunker_version", String(32), nullable=False),
    Column("embedding_fingerprint", String(64), nullable=True),
    Column("embedding_spec", JSONB, nullable=True),
    Column("status", String(16), nullable=False, server_default=text("'queued'")),
    Column("attempt_no", Integer, nullable=False, server_default=text("0")),
    Column("lease_owner", String(128), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("chunk_count", Integer, nullable=False, server_default=text("0")),
    Column("embedded_count", Integer, nullable=False, server_default=text("0")),
    Column("truncated", Boolean, nullable=False, server_default=text("false")),
    Column("detail", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("error", JSONB, nullable=True),
    Column("queued_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["extraction_run.project_id", "extraction_run.run_id"],
        name="fk_retrieval_index_run_scope",
        ondelete="CASCADE",
    ),
    UniqueConstraint("project_id", "index_id", name="uq_retrieval_index_project_scope"),
    CheckConstraint(_in("kind", INDEX_KINDS), name="kind_known"),
    CheckConstraint(_in("status", INDEX_STATUSES), name="status_known"),
    CheckConstraint(
        "(kind = 'embeddings') = (embedding_fingerprint IS NOT NULL)", name="fingerprint_iff_vector"
    ),
    CheckConstraint(
        "embedding_fingerprint IS NULL OR embedding_fingerprint ~ '^[0-9a-f]{64}$'",
        name="fingerprint_sha256",
    ),
    CheckConstraint("chunk_count >= 0 AND embedded_count >= 0", name="counts_nonnegative"),
    CheckConstraint(
        "status <> 'complete' OR (finished_at IS NOT NULL AND lease_owner IS NULL)",
        name="complete_is_finished",
    ),
    Index(
        "uq_retrieval_index_chunks",
        "run_id",
        "chunker_version",
        unique=True,
        postgresql_where=text("kind = 'chunks'"),
    ),
    Index(
        "uq_retrieval_index_embeddings",
        "run_id",
        "chunker_version",
        "embedding_fingerprint",
        unique=True,
        postgresql_where=text("kind = 'embeddings'"),
    ),
    Index("ix_retrieval_index_status_queued_at", "status", "queued_at"),
    Index("ix_retrieval_index_project_document", "project_id", "document_id"),
)

evidence_chunk = Table(
    "evidence_chunk",
    metadata,
    Column("chunk_id", UUID(as_uuid=True), primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("index_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("chunker_version", String(32), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("kind", String(48), nullable=False),
    Column("chunk_fingerprint", String(64), nullable=False),
    Column("text", Text, nullable=False),
    Column("search_text", Text, nullable=False),
    Column("tsv", TSVECTOR, Computed("to_tsvector('simple', search_text)", persisted=True)),
    Column("token_count", Integer, nullable=False),
    Column("record_ids", ARRAY(UUID(as_uuid=True)), nullable=False),
    Column("first_record_ordinal", Integer, nullable=False),
    Column("last_record_ordinal", Integer, nullable=False),
    Column("locators", JSONB, nullable=False),
    Column("temporal_coverage", JSONB, nullable=True),
    Column("extraction_quality", JSONB, nullable=False),
    Column("resolved_entity_id", UUID(as_uuid=True), nullable=True),
    Column("claim_ids", ARRAY(UUID(as_uuid=True)), nullable=False, server_default=text("'{}'")),
    Column("invalidated_at", DateTime(timezone=True), nullable=True),
    Column("invalidated_reason", String(64), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "index_id"],
        ["retrieval_index.project_id", "retrieval_index.index_id"],
        name="fk_evidence_chunk_index_scope",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_evidence_chunk_document_scope",
        ondelete="CASCADE",
    ),
    UniqueConstraint("project_id", "chunk_id", name="uq_evidence_chunk_project_scope"),
    UniqueConstraint("index_id", "ordinal", name="uq_evidence_chunk_index_ordinal"),
    CheckConstraint(f"token_count BETWEEN 1 AND {MAX_CHUNK_TOKENS}", name="tokens_bounded"),
    CheckConstraint("chunk_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint_sha256"),
    CheckConstraint(
        "first_record_ordinal >= 0 AND last_record_ordinal >= first_record_ordinal",
        name="ordinals_ordered",
    ),
    CheckConstraint(
        "(invalidated_at IS NULL) = (invalidated_reason IS NULL)", name="invalidation_paired"
    ),
    Index("ix_evidence_chunk_tsv", "tsv", postgresql_using="gin"),
    Index("ix_evidence_chunk_document_revision", "project_id", "document_id", "source_revision_id"),
)

chunk_identifier = Table(
    "chunk_identifier",
    metadata,
    Column("chunk_id", UUID(as_uuid=True), primary_key=True),
    Column("identifier", Text, primary_key=True),
    Column("id_kind", String(24), primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("canonical", Text, nullable=False),
    ForeignKeyConstraint(
        ["project_id", "chunk_id"],
        ["evidence_chunk.project_id", "evidence_chunk.chunk_id"],
        name="fk_chunk_identifier_chunk_scope",
        ondelete="CASCADE",
    ),
    CheckConstraint(
        "identifier = lower(identifier) AND canonical = lower(canonical)", name="lower"
    ),
    Index("ix_chunk_identifier_lookup", "project_id", "identifier"),
    Index("ix_chunk_identifier_canonical", "project_id", "canonical"),
)

chunk_embedding = Table(
    "chunk_embedding",
    metadata,
    Column("chunk_id", UUID(as_uuid=True), primary_key=True),
    Column("embedding_fingerprint", String(64), primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("chunk_fingerprint", String(64), nullable=False),
    Column("dimension", Integer, nullable=False),
    Column("embedding", Vector, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "chunk_id"],
        ["evidence_chunk.project_id", "evidence_chunk.chunk_id"],
        name="fk_chunk_embedding_chunk_scope",
        ondelete="CASCADE",
    ),
    CheckConstraint("embedding_fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint_sha256"),
    CheckConstraint("dimension BETWEEN 1 AND 4096", name="dimension_bounded"),
    CheckConstraint("vector_dims(embedding) = dimension", name="dimension_matches"),
    Index("ix_chunk_embedding_fingerprint", "project_id", "embedding_fingerprint"),
)

__all__ = [
    "INDEX_KINDS",
    "INDEX_STATUSES",
    "MAX_CHUNK_TOKENS",
    "Vector",
    "chunk_embedding",
    "chunk_identifier",
    "evidence_chunk",
    "retrieval_index",
]

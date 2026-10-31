"""Source retrieval: derived evidence chunks, exact identifiers, embeddings and index jobs.

Revision ID: 0007_source_retrieval
Revises: 0006_agent_activity_log

Everything here is derived, rebuildable data over ``extracted_record`` (TASK-011). Project
scoping is structural (composite foreign keys). Embeddings are keyed by chunk fingerprint and
embedding fingerprint; the ``vector`` column is unconstrained with a per-row dimension check so
a different embedding dimension never needs a table rewrite. No ANN index: search is exact
cosine, filtered before ranking. Chunks cascade away with their index job, their document or
the extraction run, so removing a source cannot leave searchable text behind.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_source_retrieval"
down_revision: str | None = "0006_agent_activity_log"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")


class _Vector(sa.types.UserDefinedType):  # pgvector column; no extra Python dependency
    cache_ok = True

    def get_col_spec(self, **kw: object) -> str:
        return "vector"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "retrieval_index",
        sa.Column("index_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("chunker_version", sa.String(32), nullable=False),
        sa.Column("embedding_fingerprint", sa.String(64), nullable=True),
        sa.Column("embedding_spec", postgresql.JSONB, nullable=True),
        sa.Column("status", sa.String(16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column("attempt_no", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chunk_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("embedded_count", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("truncated", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column(
            "detail", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("error", postgresql.JSONB, nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("index_id", name=F("pk_retrieval_index")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_retrieval_index_project_id")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["extraction_run.project_id", "extraction_run.run_id"],
            name=F("fk_retrieval_index_run_scope"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("project_id", "index_id", name=F("uq_retrieval_index_project_scope")),
        sa.CheckConstraint(
            "kind IN ('chunks', 'embeddings')", name=F("ck_retrieval_index_kind_known")
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'complete', 'failed', 'interrupted')",
            name=F("ck_retrieval_index_status_known"),
        ),
        sa.CheckConstraint(
            "(kind = 'embeddings') = (embedding_fingerprint IS NOT NULL)",
            name=F("ck_retrieval_index_fingerprint_iff_vector"),
        ),
        sa.CheckConstraint(
            "embedding_fingerprint IS NULL OR embedding_fingerprint ~ '^[0-9a-f]{64}$'",
            name=F("ck_retrieval_index_fingerprint_sha256"),
        ),
        sa.CheckConstraint(
            "chunk_count >= 0 AND embedded_count >= 0",
            name=F("ck_retrieval_index_counts_nonnegative"),
        ),
        sa.CheckConstraint(
            "status <> 'complete' OR (finished_at IS NOT NULL AND lease_owner IS NULL)",
            name=F("ck_retrieval_index_complete_is_finished"),
        ),
    )
    op.create_index(
        "uq_retrieval_index_chunks",
        "retrieval_index",
        ["run_id", "chunker_version"],
        unique=True,
        postgresql_where=sa.text("kind = 'chunks'"),
    )
    op.create_index(
        "uq_retrieval_index_embeddings",
        "retrieval_index",
        ["run_id", "chunker_version", "embedding_fingerprint"],
        unique=True,
        postgresql_where=sa.text("kind = 'embeddings'"),
    )
    op.create_index(
        F("ix_retrieval_index_status_queued_at"), "retrieval_index", ["status", "queued_at"]
    )
    op.create_index(
        F("ix_retrieval_index_project_document"), "retrieval_index", ["project_id", "document_id"]
    )

    op.create_table(
        "evidence_chunk",
        sa.Column("chunk_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("index_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("chunker_version", sa.String(32), nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("chunk_fingerprint", sa.String(64), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("search_text", sa.Text, nullable=False),
        sa.Column(
            "tsv",
            postgresql.TSVECTOR,
            sa.Computed("to_tsvector('simple', search_text)", persisted=True),
        ),
        sa.Column("token_count", sa.Integer, nullable=False),
        sa.Column("record_ids", postgresql.ARRAY(UUID), nullable=False),
        sa.Column("first_record_ordinal", sa.Integer, nullable=False),
        sa.Column("last_record_ordinal", sa.Integer, nullable=False),
        sa.Column("locators", postgresql.JSONB, nullable=False),
        sa.Column("temporal_coverage", postgresql.JSONB, nullable=True),
        sa.Column("extraction_quality", postgresql.JSONB, nullable=False),
        sa.Column("resolved_entity_id", UUID, nullable=True),
        sa.Column(
            "claim_ids", postgresql.ARRAY(UUID), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_reason", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("chunk_id", name=F("pk_evidence_chunk")),
        sa.ForeignKeyConstraint(
            ["project_id", "index_id"],
            ["retrieval_index.project_id", "retrieval_index.index_id"],
            name=F("fk_evidence_chunk_index_scope"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_evidence_chunk_document_scope"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("project_id", "chunk_id", name=F("uq_evidence_chunk_project_scope")),
        sa.UniqueConstraint("index_id", "ordinal", name=F("uq_evidence_chunk_index_ordinal")),
        sa.CheckConstraint(
            "token_count BETWEEN 1 AND 800", name=F("ck_evidence_chunk_tokens_bounded")
        ),
        sa.CheckConstraint(
            "chunk_fingerprint ~ '^[0-9a-f]{64}$'", name=F("ck_evidence_chunk_fingerprint_sha256")
        ),
        sa.CheckConstraint(
            "first_record_ordinal >= 0 AND last_record_ordinal >= first_record_ordinal",
            name=F("ck_evidence_chunk_ordinals_ordered"),
        ),
        sa.CheckConstraint(
            "(invalidated_at IS NULL) = (invalidated_reason IS NULL)",
            name=F("ck_evidence_chunk_invalidation_paired"),
        ),
    )
    op.create_index(F("ix_evidence_chunk_tsv"), "evidence_chunk", ["tsv"], postgresql_using="gin")
    op.create_index(
        F("ix_evidence_chunk_document_revision"),
        "evidence_chunk",
        ["project_id", "document_id", "source_revision_id"],
    )

    op.create_table(
        "chunk_identifier",
        sa.Column("chunk_id", UUID, nullable=False),
        sa.Column("identifier", sa.Text, nullable=False),
        sa.Column("id_kind", sa.String(24), nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("canonical", sa.Text, nullable=False),
        sa.PrimaryKeyConstraint("chunk_id", "identifier", "id_kind", name=F("pk_chunk_identifier")),
        sa.ForeignKeyConstraint(
            ["project_id", "chunk_id"],
            ["evidence_chunk.project_id", "evidence_chunk.chunk_id"],
            name=F("fk_chunk_identifier_chunk_scope"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "identifier = lower(identifier) AND canonical = lower(canonical)",
            name=F("ck_chunk_identifier_lower"),
        ),
    )
    op.create_index(
        F("ix_chunk_identifier_lookup"), "chunk_identifier", ["project_id", "identifier"]
    )
    op.create_index(
        F("ix_chunk_identifier_canonical"), "chunk_identifier", ["project_id", "canonical"]
    )

    op.create_table(
        "chunk_embedding",
        sa.Column("chunk_id", UUID, nullable=False),
        sa.Column("embedding_fingerprint", sa.String(64), nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("chunk_fingerprint", sa.String(64), nullable=False),
        sa.Column("dimension", sa.Integer, nullable=False),
        sa.Column("embedding", _Vector(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("chunk_id", "embedding_fingerprint", name=F("pk_chunk_embedding")),
        sa.ForeignKeyConstraint(
            ["project_id", "chunk_id"],
            ["evidence_chunk.project_id", "evidence_chunk.chunk_id"],
            name=F("fk_chunk_embedding_chunk_scope"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "embedding_fingerprint ~ '^[0-9a-f]{64}$'",
            name=F("ck_chunk_embedding_fingerprint_sha256"),
        ),
        sa.CheckConstraint(
            "dimension BETWEEN 1 AND 4096", name=F("ck_chunk_embedding_dimension_bounded")
        ),
        sa.CheckConstraint(
            "vector_dims(embedding) = dimension", name=F("ck_chunk_embedding_dimension_matches")
        ),
    )
    op.create_index(
        F("ix_chunk_embedding_fingerprint"),
        "chunk_embedding",
        ["project_id", "embedding_fingerprint"],
    )


def downgrade() -> None:
    op.drop_index(F("ix_chunk_embedding_fingerprint"), table_name="chunk_embedding")
    op.drop_table("chunk_embedding")
    op.drop_index(F("ix_chunk_identifier_canonical"), table_name="chunk_identifier")
    op.drop_index(F("ix_chunk_identifier_lookup"), table_name="chunk_identifier")
    op.drop_table("chunk_identifier")
    op.drop_index(F("ix_evidence_chunk_document_revision"), table_name="evidence_chunk")
    op.drop_index(F("ix_evidence_chunk_tsv"), table_name="evidence_chunk")
    op.drop_table("evidence_chunk")
    op.drop_index(F("ix_retrieval_index_project_document"), table_name="retrieval_index")
    op.drop_index(F("ix_retrieval_index_status_queued_at"), table_name="retrieval_index")
    op.drop_index("uq_retrieval_index_embeddings", table_name="retrieval_index")
    op.drop_index("uq_retrieval_index_chunks", table_name="retrieval_index")
    op.drop_table("retrieval_index")

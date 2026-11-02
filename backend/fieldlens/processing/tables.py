"""Processing-run tables (migration 0011 is authoritative).

``processing_run`` is the persistent, project-scoped run created by an estimate and started by a
separate confirm. ``processing_run_document`` holds the per-document state, page range and cost.
A partial unique index lets a document sit in at most one pending/running run, so two runs can
never process (and spend on) the same document at once.
"""

from __future__ import annotations

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from fieldlens.persistence.models import DOCUMENT_CATEGORIES, metadata

USD = Numeric(14, 6)
RUN_STATUSES = (
    "estimated",
    "queued",
    "running",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
    "interrupted",
)
DOCUMENT_STATES = (
    "estimated",
    "pending",
    "running",
    "processed",
    "failed",
    "cancelled",
    "interrupted",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


processing_run = Table(
    "processing_run",
    metadata,
    Column(
        "run_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(16), nullable=False),
    Column("step", String(32), nullable=False),
    Column("provider", String(16), nullable=False),
    Column("route", String(16), nullable=False),
    Column("idempotency_key", String(80), nullable=True),
    Column("request_fingerprint", String(64), nullable=False),
    Column("retry_of_run_id", UUID(as_uuid=True), nullable=True),
    Column("estimated_pages", Integer, nullable=False),
    Column("estimated_input_tokens", BigInteger, nullable=False),
    Column("estimated_output_tokens", BigInteger, nullable=False),
    Column("estimated_usd", USD, nullable=False),
    Column("pricing_source", String(40), nullable=False),
    Column("total_cap_usd", USD, nullable=False),
    Column("remaining_budget_usd", USD, nullable=False),
    Column("confirmed_usd", USD, nullable=True),
    Column("actual_usd", USD, nullable=False, server_default=text("0")),
    Column("cancel_requested", Boolean, nullable=False, server_default=text("false")),
    Column("attempt_no", Integer, nullable=False, server_default=text("0")),
    Column("lease_owner", String(128), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("error_code", String(40), nullable=True),
    Column("error_message", String(400), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("confirmed_at", DateTime(timezone=True), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(["project_id"], ["project.project_id"], name="fk_processing_run_project"),
    ForeignKeyConstraint(
        ["project_id", "retry_of_run_id"],
        ["processing_run.project_id", "processing_run.run_id"],
        name="fk_processing_run_retry_scope",
    ),
    UniqueConstraint("project_id", "run_id", name="uq_processing_run_project_scope"),
    CheckConstraint(_in("status", RUN_STATUSES), name="status_known"),
    CheckConstraint("route = 'model'", name="route_model_only"),
    CheckConstraint("provider IN ('stub', 'meta')", name="provider_known"),
    CheckConstraint(
        "estimated_pages >= 0 AND estimated_usd >= 0 AND actual_usd >= 0 "
        "AND remaining_budget_usd >= 0 AND estimated_input_tokens >= 0 "
        "AND estimated_output_tokens >= 0",
        name="amounts_nonnegative",
    ),
    CheckConstraint(
        "status NOT IN ('queued', 'running', 'succeeded', 'partial') OR confirmed_usd IS NOT NULL",
        name="started_requires_confirmation",
    ),
    CheckConstraint(
        "status NOT IN ('succeeded', 'partial', 'failed', 'cancelled') OR finished_at IS NOT NULL",
        name="terminal_has_finish_time",
    ),
    Index(
        "uq_processing_run_idempotency",
        "project_id",
        "idempotency_key",
        unique=True,
        postgresql_where=text("idempotency_key IS NOT NULL"),
    ),
    Index(
        "ix_processing_run_project_recent",
        "project_id",
        text("created_at DESC"),
        text("run_id DESC"),
    ),
    Index(
        "ix_processing_run_active",
        "status",
        "created_at",
        postgresql_where=text("status IN ('queued', 'running')"),
    ),
)

processing_run_document = Table(
    "processing_run_document",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("document_id", UUID(as_uuid=True), primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("state", String(16), nullable=False),
    Column("page_count", Integer, nullable=False),
    Column("page_start", Integer, nullable=False),
    Column("page_end", Integer, nullable=False),
    Column("pages_done", Integer, nullable=False, server_default=text("0")),
    Column("label_hints", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("estimated_usd", USD, nullable=False),
    Column("actual_usd", USD, nullable=False, server_default=text("0")),
    Column("failure_code", String(40), nullable=True),
    Column("failure_message", String(400), nullable=True),
    Column("retryable", Boolean, nullable=False, server_default=text("false")),
    Column("cache_hit", Boolean, nullable=False, server_default=text("false")),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["processing_run.project_id", "processing_run.run_id"],
        name="fk_processing_run_document_run_scope",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_processing_run_document_document_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_processing_run_document_revision_scope",
    ),
    CheckConstraint(_in("state", DOCUMENT_STATES), name="state_known"),
    CheckConstraint(
        "page_start >= 1 AND page_end >= page_start AND page_end <= page_count "
        "AND page_end - page_start + 1 <= 500",
        name="page_range_bounded",
    ),
    CheckConstraint(
        "pages_done >= 0 AND pages_done <= page_end - page_start + 1", name="pages_done_bounded"
    ),
    CheckConstraint("estimated_usd >= 0 AND actual_usd >= 0", name="amounts_nonnegative"),
    CheckConstraint(
        "state <> 'processed' OR pages_done = page_end - page_start + 1",
        name="processed_read_all_pages",
    ),
    CheckConstraint(
        "state <> 'failed' OR failure_code IS NOT NULL", name="failed_has_failure_code"
    ),
    Index(
        "uq_processing_run_document_active",
        "project_id",
        "document_id",
        unique=True,
        postgresql_where=text("state IN ('pending', 'running')"),
    ),
    Index("ix_processing_run_document_document", "project_id", "document_id"),
)

# -- model classification and wellbore identity (TASK-055, migration 0016) ------------------------
IDENTITY_SUBJECT_KINDS = ("well", "wellbore")
_CATEGORY_SQL = ", ".join(f"'{c}'" for c in DOCUMENT_CATEGORIES)

document_model_result = Table(
    "document_model_result",
    metadata,
    Column(
        "result_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("page_start", Integer, nullable=False),
    Column("page_end", Integer, nullable=False),
    Column("pages_read", Integer, nullable=False),
    Column("prompt_version", String(48), nullable=False),
    Column("schema_version", String(16), nullable=False),
    Column("extraction_method", String(32), nullable=False),
    Column("provider", String(16), nullable=False),
    Column("model_revision", String(64), nullable=False),
    Column("category", String(32), nullable=False),
    Column("unclassified", Boolean, nullable=False),
    Column("tags", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("warnings", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("input_tokens", BigInteger, nullable=True),
    Column("output_tokens", BigInteger, nullable=True),
    Column("cost_usd", USD, nullable=False, server_default=text("0")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_document_model_result_document_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_document_model_result_revision_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["processing_run.project_id", "processing_run.run_id"],
        name="fk_document_model_result_run_scope",
    ),
    UniqueConstraint("project_id", "result_id", name="uq_document_model_result_project_scope"),
    UniqueConstraint(
        "project_id",
        "document_id",
        "page_start",
        "page_end",
        "prompt_version",
        "schema_version",
        name="uq_document_model_result_cache_key",
    ),
    CheckConstraint(f"category IN ({_CATEGORY_SQL})", name="category_known"),
    CheckConstraint("extraction_method = 'model_classification'", name="method_known"),
    CheckConstraint(
        "page_start >= 1 AND page_end >= page_start AND pages_read >= 0 "
        "AND pages_read <= page_end - page_start + 1 AND cardinality(tags) <= 5",
        name="pages_and_tags_bounded",
    ),
    Index(
        "ix_document_model_result_document", "project_id", "document_id", text("created_at DESC")
    ),
)

document_identity_proposal = Table(
    "document_identity_proposal",
    metadata,
    Column(
        "proposal_id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("result_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("subject_kind", String(16), nullable=False),
    Column("name_as_written", Text, nullable=False),
    Column("normalized_key", Text, nullable=True),
    Column("page", Integer, nullable=False),
    Column("quote", Text, nullable=False),
    Column("status", String(24), nullable=False, server_default=text("'model_proposal'")),
    Column("extraction_method", String(32), nullable=False),
    Column("provider", String(16), nullable=False),
    Column("model_revision", String(64), nullable=False),
    Column("prompt_version", String(48), nullable=False),
    Column("schema_version", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "result_id"],
        ["document_model_result.project_id", "document_model_result.result_id"],
        name="fk_document_identity_proposal_result_scope",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_document_identity_proposal_document_scope",
    ),
    UniqueConstraint("result_id", "ordinal", name="uq_document_identity_proposal_ordinal"),
    CheckConstraint(_in("subject_kind", IDENTITY_SUBJECT_KINDS), name="subject_kind_known"),
    CheckConstraint("status = 'model_proposal'", name="status_unverified"),
    CheckConstraint("extraction_method = 'model_classification'", name="method_known"),
    CheckConstraint(
        "page >= 1 AND char_length(quote) >= 1 AND char_length(name_as_written) >= 1",
        name="evidence_present",
    ),
    Index("ix_document_identity_proposal_document", "project_id", "document_id"),
)

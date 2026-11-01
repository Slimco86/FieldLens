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
from sqlalchemy.dialects.postgresql import UUID

from fieldlens.persistence.models import metadata

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
    CheckConstraint("provider = 'stub'", name="provider_known"),
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

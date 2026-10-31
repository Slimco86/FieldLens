"""Core relational schema (SQLAlchemy Core metadata; the Alembic migration is authoritative).

Every child row carries ``project_id`` and uses composite ``(project_id, id)`` foreign keys, so
project/revision/subject joins cannot cross project scopes. No engineering, provider or job
tables live here; later packets add their own through their own migrations.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING)

# Provider budget tables (TASK-004) register themselves on this metadata.
from fieldlens.assistant import tables as _assistant_tables  # noqa: E402,F401


def _uuid_pk(name: str) -> Column[Any]:
    return Column(
        name, UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Column[Any]:
    return Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


project = Table(
    "project",
    metadata,
    _uuid_pk("project_id"),
    Column("name", String(120), nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    _created_at(),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("latest_source_revision_id", UUID(as_uuid=True), nullable=True),
    Column("active_model_revision_id", UUID(as_uuid=True), nullable=True),
    CheckConstraint("char_length(name) >= 1 AND name = btrim(name)", name="name_trimmed"),
    CheckConstraint("char_length(description) <= 4000", name="description_max_length"),
    Index(
        "ix_project_created_at_project_id",
        text("created_at DESC"),
        text("project_id DESC"),
    ),
)

source_revision = Table(
    "source_revision",
    metadata,
    _uuid_pk("source_revision_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("parent_source_revision_id", UUID(as_uuid=True), nullable=True),
    Column("manifest_hash", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    _created_at(),
    Column("coverage", JSONB, nullable=True),
    UniqueConstraint("project_id", "source_revision_id", name="uq_source_revision_project_scope"),
    ForeignKeyConstraint(
        ["project_id", "parent_source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_source_revision_parent_scope",
    ),
    CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="manifest_hash_sha256"),
    CheckConstraint(
        "status IN ('staging','ready','ready_with_issues','failed')", name="status_known"
    ),
    CheckConstraint(
        "parent_source_revision_id IS DISTINCT FROM source_revision_id", name="not_own_parent"
    ),
    # One import may stage at a time per project (a concurrent second import gets 409).
    Index(
        "uq_source_revision_one_staging_per_project",
        "project_id",
        unique=True,
        postgresql_where=text("status = 'staging'"),
    ),
)

model_revision = Table(
    "model_revision",
    metadata,
    _uuid_pk("revision_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("pinned_source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("base_revision_id", UUID(as_uuid=True), nullable=True),
    Column("status", String(32), nullable=False),
    _created_at(),
    Column("coverage", JSONB, nullable=True),
    UniqueConstraint("project_id", "revision_id", name="uq_model_revision_project_scope"),
    ForeignKeyConstraint(
        ["project_id", "pinned_source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_model_revision_source_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "base_revision_id"],
        ["model_revision.project_id", "model_revision.revision_id"],
        name="fk_model_revision_base_scope",
    ),
    CheckConstraint("status IN ('draft','validated','published','rejected')", name="status_known"),
    CheckConstraint("base_revision_id IS DISTINCT FROM revision_id", name="not_own_base"),
)

# Project pointers are project-qualified too (deferred: a project precedes its revisions).
project.append_constraint(
    ForeignKeyConstraint(
        ["project_id", "latest_source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_project_latest_source_scope",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    )
)
project.append_constraint(
    ForeignKeyConstraint(
        ["project_id", "active_model_revision_id"],
        ["model_revision.project_id", "model_revision.revision_id"],
        name="fk_project_active_model_scope",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    )
)

source_document = Table(
    "source_document",
    metadata,
    _uuid_pk("document_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("original_filename", String(512), nullable=False),
    Column("detected_media_type", String(255), nullable=True),
    Column("origin_metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("storage_key", Text, nullable=False),
    _created_at(),
    Column("format_family", String(32), nullable=False, server_default=text("'unknown'")),
    UniqueConstraint("project_id", "document_id", name="uq_source_document_project_scope"),
    # Same bytes in one project are one document; the hash never crosses projects.
    UniqueConstraint("project_id", "sha256", name="uq_source_document_project_sha256"),
    CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
    CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
)

source_revision_document = Table(
    "source_revision_document",
    metadata,
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), primary_key=True),
    Column("document_id", UUID(as_uuid=True), primary_key=True),
    Column("replaces_document_id", UUID(as_uuid=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_srd_revision_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "replaces_document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_srd_replaces_scope",
    ),
    CheckConstraint(
        "replaces_document_id IS DISTINCT FROM document_id", name="srd_not_self_replace"
    ),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_srd_document_scope",
    ),
)

well = Table(
    "well",
    metadata,
    _uuid_pk("well_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("name", Text, nullable=False),
    UniqueConstraint("project_id", "well_id", name="uq_well_project_scope"),
    CheckConstraint("char_length(name) >= 1", name="name_nonempty"),
)

wellbore = Table(
    "wellbore",
    metadata,
    _uuid_pk("wellbore_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("well_id", UUID(as_uuid=True), nullable=False),
    Column("parent_wellbore_id", UUID(as_uuid=True), nullable=True),
    Column("name", Text, nullable=False),
    UniqueConstraint("project_id", "wellbore_id", name="uq_wellbore_project_scope"),
    ForeignKeyConstraint(
        ["project_id", "well_id"],
        ["well.project_id", "well.well_id"],
        name="fk_wellbore_well_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "parent_wellbore_id"],
        ["wellbore.project_id", "wellbore.wellbore_id"],
        name="fk_wellbore_parent_scope",
    ),
    CheckConstraint("char_length(name) >= 1", name="name_nonempty"),
    CheckConstraint("parent_wellbore_id IS DISTINCT FROM wellbore_id", name="not_own_parent"),
)


# --- Upload, classification and persistent jobs (migration 0003_upload_jobs) -------------------

DOCUMENT_CATEGORIES = (
    "trajectory",
    "completion_equipment",
    "perforation_history",
    "production_injection",
    "well_logs",
    "geology_reservoir",
    "terrain_bathymetry",
    "general_report",
)
_CATEGORY_SQL = ", ".join(f"'{c}'" for c in DOCUMENT_CATEGORIES)

document_processing = Table(
    "document_processing",
    metadata,
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), primary_key=True),
    Column("storage_state", String(32), nullable=False),
    Column("extraction_state", String(32), nullable=False),
    Column("detail", Text, nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_document_processing_document_scope",
    ),
    CheckConstraint(
        "storage_state IN ('pending_verification','stored','quarantined')",
        name="storage_state_known",
    ),
    CheckConstraint(
        "extraction_state IN ('pending_extraction','unsupported','extracted',"
        "'extracted_with_issues','extraction_failed')",
        name="extraction_state_known",
    ),
)

document_classification = Table(
    "document_classification",
    metadata,
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), primary_key=True),
    Column("user_categories", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("suggested_categories", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("tags", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("categories_origin", String(32), nullable=False),
    Column("classification_method", String(64), nullable=False),
    Column("classification_version", String(32), nullable=False),
    Column("metadata_version", Integer, nullable=False, server_default=text("1")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_document_classification_document_scope",
    ),
    CheckConstraint(
        f"user_categories <@ ARRAY[{_CATEGORY_SQL}]::text[] "
        f"AND suggested_categories <@ ARRAY[{_CATEGORY_SQL}]::text[]",
        name="categories_known",
    ),
    CheckConstraint("cardinality(tags) <= 20", name="tags_max"),
    CheckConstraint(
        "categories_origin IN ('none','upload_hint','user_override')", name="origin_known"
    ),
    CheckConstraint("metadata_version >= 1", name="version_positive"),
)

document_classification_event = Table(
    "document_classification_event",
    metadata,
    Column("event_id", BigInteger, primary_key=True, autoincrement=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("metadata_version", Integer, nullable=False),
    Column("origin", String(32), nullable=False),
    Column("categories", ARRAY(Text), nullable=False),
    Column("tags", ARRAY(Text), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_document_classification_event_document_scope",
    ),
    UniqueConstraint(
        "document_id", "metadata_version", name="uq_document_classification_event_version"
    ),
    CheckConstraint("origin IN ('upload_hint','user_override','none')", name="origin_known"),
)

JOB_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "partial",
    "failed",
    "cancelled",
    "interrupted",
)
_JOB_STATUS_SQL = ", ".join(f"'{c}'" for c in JOB_STATUSES)

ingest_job = Table(
    "ingest_job",
    metadata,
    _uuid_pk("job_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(16), nullable=False, server_default=text("'queued'")),
    Column("cancel_requested", Boolean, nullable=False, server_default=text("false")),
    Column("stage", String(32), nullable=True),
    Column("progress_processed", Integer, nullable=True),
    Column("progress_total", Integer, nullable=True),
    Column("progress_unit", String(16), nullable=True),
    Column("result", JSONB, nullable=True),
    Column("error", JSONB, nullable=True),
    Column("fence_counter", BigInteger, nullable=False, server_default=text("0")),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("max_attempts", Integer, nullable=False, server_default=text("2")),
    _created_at(),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    UniqueConstraint("project_id", "job_id", name="uq_ingest_job_project_scope"),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_ingest_job_revision_scope",
    ),
    CheckConstraint("kind IN ('storage_verification')", name="kind_known"),
    CheckConstraint(f"status IN ({_JOB_STATUS_SQL})", name="status_known"),
    CheckConstraint("attempt_count <= max_attempts", name="attempts_bounded"),
    Index("ix_ingest_job_status_created_at", "status", "created_at"),
)

ingest_job_attempt = Table(
    "ingest_job_attempt",
    metadata,
    _uuid_pk("attempt_id"),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("job_id", UUID(as_uuid=True), nullable=False),
    Column("attempt_no", Integer, nullable=False),
    Column("status", String(16), nullable=False, server_default=text("'running'")),
    Column("stage", String(32), nullable=True),
    Column("fencing_token", BigInteger, nullable=False),
    Column("lease_owner", Text, nullable=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=False),
    Column("heartbeat_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("ended_at", DateTime(timezone=True), nullable=True),
    Column("error", JSONB, nullable=True),
    ForeignKeyConstraint(
        ["project_id", "job_id"],
        ["ingest_job.project_id", "ingest_job.job_id"],
        name="fk_ingest_job_attempt_job_scope",
    ),
    UniqueConstraint("job_id", "attempt_no", name="uq_ingest_job_attempt_no"),
    UniqueConstraint("job_id", "fencing_token", name="uq_ingest_job_attempt_fence"),
    CheckConstraint(
        "status IN ('running','succeeded','failed','interrupted','cancelled')",
        name="status_known",
    ),
    # Only one heavy attempt may run at a time across all workers.
    Index(
        "uq_ingest_job_attempt_single_running",
        text("(true)"),
        unique=True,
        postgresql_where=text("status = 'running'"),
    ),
)

import_batch = Table(
    "import_batch",
    metadata,
    _uuid_pk("batch_id"),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("idempotency_key", String(128), nullable=True),
    Column("fingerprint", String(64), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("job_id", UUID(as_uuid=True), nullable=True),
    Column("deduplicated", Boolean, nullable=False, server_default=text("false")),
    Column("document_ids", ARRAY(UUID(as_uuid=True)), nullable=False),
    _created_at(),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_import_batch_revision_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "job_id"],
        ["ingest_job.project_id", "ingest_job.job_id"],
        name="fk_import_batch_job_scope",
    ),
    CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name="fingerprint_sha256"),
    Index(
        "uq_import_batch_project_idempotency_key",
        "project_id",
        "idempotency_key",
        unique=True,
        postgresql_where=text("idempotency_key IS NOT NULL"),
    ),
)


RUN_STATUSES = ("queued", "running", "succeeded", "partial", "failed", "interrupted", "unsupported")

extraction_run = Table(
    "extraction_run",
    metadata,
    _uuid_pk("run_id"),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("profile_name", String(64), nullable=True),
    Column("profile_version", String(32), nullable=True),
    Column("method", String(64), nullable=True),
    Column("content_sha256", String(64), nullable=False),
    Column("status", String(16), nullable=False),
    Column("attempt_no", Integer, nullable=False, server_default=text("0")),
    Column("lease_owner", String(128), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("coverage", JSONB, nullable=True),
    Column("summary", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("error", JSONB, nullable=True),
    Column("superseded", Boolean, nullable=False, server_default=text("false")),
    Column("queued_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_extraction_run_document_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_extraction_run_revision_scope",
    ),
    CheckConstraint(
        "status IN (" + ", ".join(f"'{c}'" for c in RUN_STATUSES) + ")", name="status_known"
    ),
    CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    UniqueConstraint("project_id", "run_id", name="uq_extraction_run_project_run"),
    Index(
        "uq_extraction_run_one_current_per_document",
        "document_id",
        unique=True,
        postgresql_where=text("NOT superseded"),
    ),
    Index(
        "ix_extraction_run_current_status_profile",
        "status",
        "profile_name",
        "profile_version",
        postgresql_where=text("NOT superseded"),
    ),
)

extracted_record = Table(
    "extracted_record",
    metadata,
    _uuid_pk("record_id"),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("kind", String(48), nullable=False),
    Column("subject", JSONB, nullable=False),
    Column("locator", JSONB, nullable=False),
    Column("effective_time", JSONB, nullable=True),
    Column("report_time", JSONB, nullable=True),
    Column("validation_state", String(16), nullable=False),
    Column("attributes", JSONB, nullable=False),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["extraction_run.project_id", "extraction_run.run_id"],
        name="fk_extracted_record_run_scope",
        ondelete="CASCADE",
    ),
    UniqueConstraint("run_id", "ordinal", name="uq_extracted_record_run_ordinal"),
    Index("ix_extracted_record_run_kind", "run_id", "kind", "ordinal"),
)

extraction_issue = Table(
    "extraction_issue",
    metadata,
    Column("issue_id", UUID(as_uuid=True), primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("producer_key", String(256), nullable=False),
    Column("code", String(48), nullable=False),
    Column("severity", String(16), nullable=False),
    Column("message", Text, nullable=False),
    Column("attribute_keys", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("record_ordinals", ARRAY(Integer), nullable=False, server_default=text("'{}'")),
    Column("locators", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("blocked_operations", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("coverage", JSONB, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["extraction_run.project_id", "extraction_run.run_id"],
        name="fk_extraction_issue_run_scope",
        ondelete="CASCADE",
    ),
    UniqueConstraint("run_id", "producer_key", name="uq_extraction_issue_run_key"),
)

# --- Agent activity log (migration 0006_agent_activity_log; AX-10, display/audit only) ----------

AGENT_UNIT_STATES = ("running", "succeeded", "failed", "interrupted", "cancelled")
AGENT_STEP_KINDS = ("tool_call", "candidate", "validator", "model_turn", "lifecycle", "note")
AGENT_STEP_OUTCOMES = ("ok", "refused", "error", "passed", "failed", "flagged")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


agent_work_unit = Table(
    "agent_work_unit",
    metadata,
    _uuid_pk("unit_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("unit_key", String(200), nullable=False),
    Column("question", Text, nullable=False),
    Column("state", String(16), nullable=False, server_default=text("'running'")),
    Column("stop_reason", String(64), nullable=True),
    Column("stop_detail", String(600), nullable=True),
    Column("fence_counter", Integer, nullable=False, server_default=text("1")),
    Column("attempt_count", Integer, nullable=False, server_default=text("1")),
    Column("step_count", Integer, nullable=False, server_default=text("0")),
    Column("tool_call_count", Integer, nullable=False, server_default=text("0")),
    Column("candidate_count", Integer, nullable=False, server_default=text("0")),
    Column("input_tokens", BigInteger, nullable=False, server_default=text("0")),
    Column("cached_input_tokens", BigInteger, nullable=False, server_default=text("0")),
    Column("output_tokens", BigInteger, nullable=False, server_default=text("0")),
    Column("cost_usd", Numeric(14, 6), nullable=False, server_default=text("0")),
    _created_at(),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_agent_work_unit_revision_scope",
    ),
    UniqueConstraint("project_id", "unit_id", name="uq_agent_work_unit_project_scope"),
    UniqueConstraint("project_id", "unit_key", name="uq_agent_work_unit_key"),
    CheckConstraint(_in("state", AGENT_UNIT_STATES), name="state_known"),
    CheckConstraint(
        "(state = 'running' AND stop_reason IS NULL AND finished_at IS NULL) "
        "OR (state <> 'running' AND stop_reason IS NOT NULL AND finished_at IS NOT NULL)",
        name="terminal_has_stop_reason",
    ),
    CheckConstraint("char_length(question) BETWEEN 1 AND 2200", name="question_bounded"),
    CheckConstraint(
        "fence_counter >= 1 AND attempt_count >= 1 AND step_count BETWEEN 0 AND 200 "
        "AND tool_call_count >= 0 AND candidate_count >= 0 AND input_tokens >= 0 "
        "AND cached_input_tokens >= 0 AND output_tokens >= 0 AND cost_usd >= 0",
        name="counters_bounded",
    ),
    Index(
        "ix_agent_work_unit_project_recent",
        "project_id",
        text("created_at DESC"),
        text("unit_id DESC"),
    ),
    Index("ix_agent_work_unit_project_revision_state", "project_id", "source_revision_id", "state"),
)

agent_step = Table(
    "agent_step",
    metadata,
    _uuid_pk("step_id"),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("unit_id", UUID(as_uuid=True), nullable=False),
    Column("step_no", Integer, nullable=False),
    Column("step_key", String(120), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("outcome", String(16), nullable=True),
    Column("tool_name", String(64), nullable=True),
    Column("summary", Text, nullable=False),
    Column("detail", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("evidence", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("truncated", Boolean, nullable=False, server_default=text("false")),
    _created_at(),
    ForeignKeyConstraint(
        ["project_id", "unit_id"],
        ["agent_work_unit.project_id", "agent_work_unit.unit_id"],
        name="fk_agent_step_unit_scope",
        ondelete="CASCADE",
    ),
    UniqueConstraint("unit_id", "step_no", name="uq_agent_step_unit_no"),
    UniqueConstraint("unit_id", "step_key", name="uq_agent_step_unit_key"),
    CheckConstraint(_in("kind", AGENT_STEP_KINDS), name="kind_known"),
    CheckConstraint(
        f"outcome IS NULL OR {_in('outcome', AGENT_STEP_OUTCOMES)}", name="outcome_known"
    ),
    CheckConstraint("step_no >= 1", name="no_positive"),
    CheckConstraint("char_length(summary) BETWEEN 1 AND 1200", name="summary_bounded"),
    CheckConstraint(
        "octet_length(detail::text) <= 12288 AND octet_length(evidence::text) <= 12288 "
        "AND jsonb_typeof(detail) = 'object' AND jsonb_typeof(evidence) = 'array'",
        name="payload_bounded",
    ),
    CheckConstraint("kind <> 'tool_call' OR tool_name IS NOT NULL", name="tool_named"),
)

# Retrieval index tables (TASK-011, migration 0007) register on this metadata after the tables
# they reference are defined.
from fieldlens.retrieval import tables as _retrieval_tables  # noqa: E402,F401

# Series storage tables (TASK-047, migration 0008).
from fieldlens.series import tables as _series_tables  # noqa: E402,F401

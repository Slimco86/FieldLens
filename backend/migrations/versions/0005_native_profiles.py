"""Native source profile extraction runs, extracted records and extraction findings (TASK-009).

Revision ID: 0005_native_profiles
Revises: 0004_provider_budget

Adds ``extraction_run`` (persistent, leased, one current run per document), ``extracted_record``
(attribute-level evidence in JSONB), ``extraction_issue`` (revision-local idempotent findings) and
widens ``document_processing.extraction_state``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_native_profiles"
down_revision: str | None = "0004_provider_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
RUN_STATUSES = (
    "queued",
    "running",
    "succeeded",
    "partial",
    "failed",
    "interrupted",
    "unsupported",
)
OLD_STATES = "extraction_state IN ('pending_extraction','unsupported')"
NEW_STATES = (
    "extraction_state IN ('pending_extraction','unsupported','extracted',"
    "'extracted_with_issues','extraction_failed')"
)


def upgrade() -> None:
    op.drop_constraint(
        F("ck_document_processing_extraction_state_known"), "document_processing", type_="check"
    )
    op.create_check_constraint(
        F("ck_document_processing_extraction_state_known"), "document_processing", NEW_STATES
    )

    op.create_table(
        "extraction_run",
        sa.Column("run_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("profile_name", sa.String(64), nullable=True),
        sa.Column("profile_version", sa.String(32), nullable=True),
        sa.Column("method", sa.String(64), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coverage", postgresql.JSONB(), nullable=True),
        sa.Column(
            "summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("superseded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name=F("pk_extraction_run")),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_extraction_run_document_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_extraction_run_revision_scope"),
        ),
        sa.CheckConstraint(
            "status IN (" + ", ".join(f"'{c}'" for c in RUN_STATUSES) + ")",
            name=F("ck_extraction_run_status_known"),
        ),
        sa.CheckConstraint("content_sha256 ~ '^[0-9a-f]{64}$'", name=F("ck_extraction_run_sha256")),
        sa.UniqueConstraint("project_id", "run_id", name=F("uq_extraction_run_project_run")),
    )
    op.create_index(
        F("uq_extraction_run_one_current_per_document"),
        "extraction_run",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("NOT superseded"),
    )

    op.create_table(
        "extracted_record",
        sa.Column("record_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("subject", postgresql.JSONB(), nullable=False),
        sa.Column("locator", postgresql.JSONB(), nullable=False),
        sa.Column("effective_time", postgresql.JSONB(), nullable=True),
        sa.Column("report_time", postgresql.JSONB(), nullable=True),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.PrimaryKeyConstraint("record_id", name=F("pk_extracted_record")),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["extraction_run.project_id", "extraction_run.run_id"],
            name=F("fk_extracted_record_run_scope"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "ordinal", name=F("uq_extracted_record_run_ordinal")),
    )
    op.create_index(
        F("ix_extracted_record_run_kind"), "extracted_record", ["run_id", "kind", "ordinal"]
    )

    op.create_table(
        "extraction_issue",
        sa.Column("issue_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("producer_key", sa.String(256), nullable=False),
        sa.Column("code", sa.String(48), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "attribute_keys", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "record_ordinals", postgresql.ARRAY(sa.Integer()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "locators", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column(
            "blocked_operations", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column("coverage", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("issue_id", name=F("pk_extraction_issue")),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["extraction_run.project_id", "extraction_run.run_id"],
            name=F("fk_extraction_issue_run_scope"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "producer_key", name=F("uq_extraction_issue_run_key")),
    )


def downgrade() -> None:
    op.drop_table("extraction_issue")
    op.drop_index(F("ix_extracted_record_run_kind"), table_name="extracted_record")
    op.drop_table("extracted_record")
    op.drop_index(F("uq_extraction_run_one_current_per_document"), table_name="extraction_run")
    op.drop_table("extraction_run")
    op.execute(
        "UPDATE document_processing SET extraction_state = 'pending_extraction' "
        "WHERE extraction_state IN ('extracted','extracted_with_issues','extraction_failed')"
    )
    op.drop_constraint(
        F("ck_document_processing_extraction_state_known"), "document_processing", type_="check"
    )
    op.create_check_constraint(
        F("ck_document_processing_extraction_state_known"), "document_processing", OLD_STATES
    )

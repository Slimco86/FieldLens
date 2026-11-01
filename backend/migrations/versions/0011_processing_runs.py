"""Processing runs: estimate, separate confirmation, per-document state (TASK-054).

Revision ID: 0011_processing_runs
Revises: 0010_extraction_candidates

``processing_run`` and ``processing_run_document`` are self-contained (they reference only the
project, source document and source revision tables). A partial unique index keeps a document in
at most one pending/running run; CHECK constraints make "started needs a confirmation" and "a
processed document read every selected page" structural.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_processing_runs"
down_revision: str | None = "0010_extraction_candidates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
USD = sa.Numeric(14, 6)


def upgrade() -> None:
    op.create_table(
        "processing_run",
        sa.Column("run_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("step", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("route", sa.String(16), nullable=False),
        sa.Column("idempotency_key", sa.String(80), nullable=True),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("retry_of_run_id", UUID, nullable=True),
        sa.Column("estimated_pages", sa.Integer, nullable=False),
        sa.Column("estimated_input_tokens", sa.BigInteger, nullable=False),
        sa.Column("estimated_output_tokens", sa.BigInteger, nullable=False),
        sa.Column("estimated_usd", USD, nullable=False),
        sa.Column("pricing_source", sa.String(40), nullable=False),
        sa.Column("total_cap_usd", USD, nullable=False),
        sa.Column("remaining_budget_usd", USD, nullable=False),
        sa.Column("confirmed_usd", USD, nullable=True),
        sa.Column("actual_usd", USD, server_default=sa.text("0"), nullable=False),
        sa.Column("cancel_requested", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("attempt_no", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("error_message", sa.String(400), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name=F("pk_processing_run")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_processing_run_project")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "retry_of_run_id"],
            ["processing_run.project_id", "processing_run.run_id"],
            name=F("fk_processing_run_retry_scope"),
        ),
        sa.UniqueConstraint("project_id", "run_id", name=F("uq_processing_run_project_scope")),
        sa.CheckConstraint(
            "status IN ('estimated', 'queued', 'running', 'succeeded', 'partial', 'failed', "
            "'cancelled', 'interrupted')",
            name=F("ck_processing_run_status_known"),
        ),
        sa.CheckConstraint("route = 'model'", name=F("ck_processing_run_route_model_only")),
        sa.CheckConstraint("provider = 'stub'", name=F("ck_processing_run_provider_known")),
        sa.CheckConstraint(
            "estimated_pages >= 0 AND estimated_usd >= 0 AND actual_usd >= 0 "
            "AND remaining_budget_usd >= 0 AND estimated_input_tokens >= 0 "
            "AND estimated_output_tokens >= 0",
            name=F("ck_processing_run_amounts_nonnegative"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('queued', 'running', 'succeeded', 'partial') "
            "OR confirmed_usd IS NOT NULL",
            name=F("ck_processing_run_started_requires_confirmation"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('succeeded', 'partial', 'failed', 'cancelled') "
            "OR finished_at IS NOT NULL",
            name=F("ck_processing_run_terminal_has_finish_time"),
        ),
    )
    op.create_index(
        F("uq_processing_run_idempotency"),
        "processing_run",
        ["project_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        F("ix_processing_run_project_recent"),
        "processing_run",
        ["project_id", sa.text("created_at DESC"), sa.text("run_id DESC")],
    )
    op.create_index(
        F("ix_processing_run_active"),
        "processing_run",
        ["status", "created_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    op.create_table(
        "processing_run_document",
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("page_count", sa.Integer, nullable=False),
        sa.Column("page_start", sa.Integer, nullable=False),
        sa.Column("page_end", sa.Integer, nullable=False),
        sa.Column("pages_done", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("label_hints", postgresql.ARRAY(sa.Text), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("estimated_usd", USD, nullable=False),
        sa.Column("actual_usd", USD, server_default=sa.text("0"), nullable=False),
        sa.Column("failure_code", sa.String(40), nullable=True),
        sa.Column("failure_message", sa.String(400), nullable=True),
        sa.Column("retryable", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", "document_id", name=F("pk_processing_run_document")),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["processing_run.project_id", "processing_run.run_id"],
            name=F("fk_processing_run_document_run_scope"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_processing_run_document_document_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_processing_run_document_revision_scope"),
        ),
        sa.CheckConstraint(
            "state IN ('estimated', 'pending', 'running', 'processed', 'failed', 'cancelled', "
            "'interrupted')",
            name=F("ck_processing_run_document_state_known"),
        ),
        sa.CheckConstraint(
            "page_start >= 1 AND page_end >= page_start AND page_end <= page_count "
            "AND page_end - page_start + 1 <= 500",
            name=F("ck_processing_run_document_page_range_bounded"),
        ),
        sa.CheckConstraint(
            "pages_done >= 0 AND pages_done <= page_end - page_start + 1",
            name=F("ck_processing_run_document_pages_done_bounded"),
        ),
        sa.CheckConstraint(
            "estimated_usd >= 0 AND actual_usd >= 0",
            name=F("ck_processing_run_document_amounts_nonnegative"),
        ),
        sa.CheckConstraint(
            "state <> 'processed' OR pages_done = page_end - page_start + 1",
            name=F("ck_processing_run_document_processed_read_all_pages"),
        ),
        sa.CheckConstraint(
            "state <> 'failed' OR failure_code IS NOT NULL",
            name=F("ck_processing_run_document_failed_has_failure_code"),
        ),
    )
    op.create_index(
        F("uq_processing_run_document_active"),
        "processing_run_document",
        ["project_id", "document_id"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending', 'running')"),
    )
    op.create_index(
        F("ix_processing_run_document_document"),
        "processing_run_document",
        ["project_id", "document_id"],
    )


def downgrade() -> None:
    op.drop_index(F("ix_processing_run_document_document"), table_name="processing_run_document")
    op.drop_index(F("uq_processing_run_document_active"), table_name="processing_run_document")
    op.drop_table("processing_run_document")
    op.drop_index(F("ix_processing_run_active"), table_name="processing_run")
    op.drop_index(F("ix_processing_run_project_recent"), table_name="processing_run")
    op.drop_index(F("uq_processing_run_idempotency"), table_name="processing_run")
    op.drop_table("processing_run")

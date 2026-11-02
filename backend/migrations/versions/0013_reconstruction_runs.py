"""Per-wellbore reconstruction runs with S1..S4 stage rows (TASK-068).

Revision ID: 0013_reconstruction_runs
Revises: 0012_merge_proposals

``reconstruction_estimate`` groups the runs one estimate created (one confirm covers the group).
``reconstruction_run`` is per wellbore; ``wellbore_id`` is not a foreign key because the identity
resolver may recreate wellbores. A partial unique index allows one queued/running run per wellbore
and source revision. ``reconstruction_run_stage`` holds the four stage rows; CHECK constraints make
"not_available has a reason and spent nothing" and "failed has an error code" structural.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_reconstruction_runs"
down_revision: str | None = "0012_merge_proposals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
USD = sa.Numeric(14, 6)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "reconstruction_estimate",
        sa.Column("estimate_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("total_estimated_usd", USD, nullable=False),
        sa.Column("pricing_source", sa.String(40), nullable=False),
        sa.Column("total_cap_usd", USD, nullable=False),
        sa.Column("remaining_budget_usd", USD, nullable=False),
        sa.Column("confirmed_usd", USD, nullable=True),
        sa.Column("confirmed_at", TS, nullable=True),
        sa.Column("created_at", TS, server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("estimate_id", name=F("pk_reconstruction_estimate")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_reconstruction_estimate_project")
        ),
        sa.UniqueConstraint("project_id", "estimate_id", name=F("uq_reconstruction_estimate_scope")),
        sa.CheckConstraint(
            "total_estimated_usd >= 0 AND remaining_budget_usd >= 0",
            name=F("ck_reconstruction_estimate_amounts_nonnegative"),
        ),
    )

    op.create_table(
        "reconstruction_run",
        sa.Column("run_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("estimate_id", UUID, nullable=False),
        sa.Column("well_id", UUID, nullable=False),
        sa.Column("wellbore_id", UUID, nullable=False),
        sa.Column("wellbore_name", sa.Text, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_revision", sa.String(64), nullable=False),
        sa.Column("retry_of_run_id", UUID, nullable=True),
        sa.Column("pricing_source", sa.String(40), nullable=False),
        sa.Column("estimated_usd", USD, nullable=False),
        sa.Column("confirmed_usd", USD, nullable=True),
        sa.Column("actual_usd", USD, server_default=sa.text("0"), nullable=False),
        sa.Column("cancel_requested", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("attempt_no", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("lease_owner", sa.String(128), nullable=True),
        sa.Column("lease_expires_at", TS, nullable=True),
        sa.Column("error_code", sa.String(48), nullable=True),
        sa.Column("error_message", sa.String(400), nullable=True),
        sa.Column("summary", postgresql.JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=NOW, nullable=False),
        sa.Column("confirmed_at", TS, nullable=True),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("finished_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("run_id", name=F("pk_reconstruction_run")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_reconstruction_run_project")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "estimate_id"],
            ["reconstruction_estimate.project_id", "reconstruction_estimate.estimate_id"],
            name=F("fk_reconstruction_run_estimate_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "retry_of_run_id"],
            ["reconstruction_run.project_id", "reconstruction_run.run_id"],
            name=F("fk_reconstruction_run_retry_scope"),
        ),
        sa.UniqueConstraint("project_id", "run_id", name=F("uq_reconstruction_run_scope")),
        sa.CheckConstraint(
            "status IN ('estimated', 'queued', 'running', 'succeeded', 'partial', 'failed', "
            "'cancelled', 'interrupted')",
            name=F("ck_reconstruction_run_status_known"),
        ),
        sa.CheckConstraint(
            "estimated_usd >= 0 AND actual_usd >= 0 AND char_length(source_revision) = 64",
            name=F("ck_reconstruction_run_amounts_nonnegative"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('queued', 'running', 'succeeded', 'partial') "
            "OR confirmed_usd IS NOT NULL",
            name=F("ck_reconstruction_run_started_requires_confirmation"),
        ),
        sa.CheckConstraint(
            "status NOT IN ('succeeded', 'partial', 'failed', 'cancelled', 'interrupted') "
            "OR finished_at IS NOT NULL",
            name=F("ck_reconstruction_run_terminal_has_finish_time"),
        ),
    )
    op.create_index(
        F("uq_reconstruction_run_active"),
        "reconstruction_run",
        ["project_id", "wellbore_id", "source_revision"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        F("ix_reconstruction_run_project_recent"),
        "reconstruction_run",
        ["project_id", sa.text("created_at DESC"), sa.text("run_id DESC")],
    )
    op.create_index(
        F("ix_reconstruction_run_claimable"),
        "reconstruction_run",
        ["status", "confirmed_at"],
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )
    op.create_index(
        F("ix_reconstruction_run_estimate"), "reconstruction_run", ["project_id", "estimate_id"]
    )

    op.create_table(
        "reconstruction_run_stage",
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("stage", sa.String(12), nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(14), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("reason_code", sa.String(48), nullable=True),
        sa.Column("message", sa.String(400), nullable=True),
        sa.Column("counts", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("input_tokens", sa.BigInteger, server_default=sa.text("0"), nullable=False),
        sa.Column("output_tokens", sa.BigInteger, server_default=sa.text("0"), nullable=False),
        sa.Column("estimated_usd", USD, server_default=sa.text("0"), nullable=False),
        sa.Column("actual_usd", USD, server_default=sa.text("0"), nullable=False),
        sa.Column("error_code", sa.String(48), nullable=True),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("finished_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("run_id", "stage", name=F("pk_reconstruction_run_stage")),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["reconstruction_run.project_id", "reconstruction_run.run_id"],
            name=F("fk_reconstruction_run_stage_run_scope"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "stage IN ('gather', 'extract', 'identify', 'assemble')",
            name=F("ck_reconstruction_run_stage_stage_known"),
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'succeeded', 'not_available', 'failed', "
            "'cancelled', 'interrupted', 'skipped')",
            name=F("ck_reconstruction_run_stage_state_known"),
        ),
        sa.CheckConstraint(
            "kind IN ('deterministic', 'agent')", name=F("ck_reconstruction_run_stage_kind_known")
        ),
        sa.CheckConstraint(
            "ordinal BETWEEN 1 AND 4", name=F("ck_reconstruction_run_stage_ordinal_bounded")
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND estimated_usd >= 0 AND actual_usd >= 0",
            name=F("ck_reconstruction_run_stage_amounts_nonnegative"),
        ),
        sa.CheckConstraint(
            "state <> 'not_available' OR reason_code IS NOT NULL",
            name=F("ck_reconstruction_run_stage_unavailable_has_reason"),
        ),
        sa.CheckConstraint(
            "state <> 'failed' OR error_code IS NOT NULL",
            name=F("ck_reconstruction_run_stage_failed_has_error_code"),
        ),
        sa.CheckConstraint(
            "state <> 'not_available' OR "
            "(actual_usd = 0 AND input_tokens = 0 AND output_tokens = 0)",
            name=F("ck_reconstruction_run_stage_unavailable_spent_nothing"),
        ),
    )


def downgrade() -> None:
    op.drop_table("reconstruction_run_stage")
    op.drop_index(F("ix_reconstruction_run_estimate"), table_name="reconstruction_run")
    op.drop_index(F("ix_reconstruction_run_claimable"), table_name="reconstruction_run")
    op.drop_index(F("ix_reconstruction_run_project_recent"), table_name="reconstruction_run")
    op.drop_index(F("uq_reconstruction_run_active"), table_name="reconstruction_run")
    op.drop_table("reconstruction_run")
    op.drop_table("reconstruction_estimate")

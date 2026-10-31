"""Agent activity log: one work unit row and ordered, bounded step rows (AX-10 backend).

Revision ID: 0006_agent_activity_log
Revises: 0005_native_profiles

Display/audit only; nothing here is an engineering fact. Steps carry summaries, bounded
excerpts and evidence locators, never hidden reasoning. Project scoping is structural: both
tables carry ``project_id`` and use composite foreign keys.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_agent_activity_log"
down_revision: str | None = "0005_native_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
ZERO = sa.text("0")
UNIT_STATES = "'running', 'succeeded', 'failed', 'interrupted', 'cancelled'"
STEP_KINDS = "'tool_call', 'candidate', 'validator', 'model_turn', 'lifecycle', 'note'"
STEP_OUTCOMES = "'ok', 'refused', 'error', 'passed', 'failed', 'flagged'"


def upgrade() -> None:
    op.create_table(
        "agent_work_unit",
        sa.Column("unit_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("unit_key", sa.String(200), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("state", sa.String(16), server_default=sa.text("'running'"), nullable=False),
        sa.Column("stop_reason", sa.String(64), nullable=True),
        sa.Column("stop_detail", sa.String(600), nullable=True),
        sa.Column("fence_counter", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("attempt_count", sa.Integer, server_default=sa.text("1"), nullable=False),
        sa.Column("step_count", sa.Integer, server_default=ZERO, nullable=False),
        sa.Column("tool_call_count", sa.Integer, server_default=ZERO, nullable=False),
        sa.Column("candidate_count", sa.Integer, server_default=ZERO, nullable=False),
        sa.Column("input_tokens", sa.BigInteger, server_default=ZERO, nullable=False),
        sa.Column("cached_input_tokens", sa.BigInteger, server_default=ZERO, nullable=False),
        sa.Column("output_tokens", sa.BigInteger, server_default=ZERO, nullable=False),
        sa.Column("cost_usd", sa.Numeric(14, 6), server_default=ZERO, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("unit_id", name=F("pk_agent_work_unit")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_agent_work_unit_project_id")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_agent_work_unit_revision_scope"),
        ),
        sa.UniqueConstraint("project_id", "unit_id", name=F("uq_agent_work_unit_project_scope")),
        sa.UniqueConstraint("project_id", "unit_key", name=F("uq_agent_work_unit_key")),
        sa.CheckConstraint(f"state IN ({UNIT_STATES})", name=F("ck_agent_work_unit_state_known")),
        sa.CheckConstraint(
            "(state = 'running' AND stop_reason IS NULL AND finished_at IS NULL) "
            "OR (state <> 'running' AND stop_reason IS NOT NULL AND finished_at IS NOT NULL)",
            name=F("ck_agent_work_unit_terminal_has_stop_reason"),
        ),
        sa.CheckConstraint(
            "char_length(question) BETWEEN 1 AND 2200",
            name=F("ck_agent_work_unit_question_bounded"),
        ),
        sa.CheckConstraint(
            "fence_counter >= 1 AND attempt_count >= 1 AND step_count BETWEEN 0 AND 200 "
            "AND tool_call_count >= 0 AND candidate_count >= 0 AND input_tokens >= 0 "
            "AND cached_input_tokens >= 0 AND output_tokens >= 0 AND cost_usd >= 0",
            name=F("ck_agent_work_unit_counters_bounded"),
        ),
    )
    op.create_index(
        F("ix_agent_work_unit_project_recent"),
        "agent_work_unit",
        ["project_id", sa.text("created_at DESC"), sa.text("unit_id DESC")],
    )
    op.create_index(
        F("ix_agent_work_unit_project_revision_state"),
        "agent_work_unit",
        ["project_id", "source_revision_id", "state"],
    )
    op.create_table(
        "agent_step",
        sa.Column("step_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("unit_id", UUID, nullable=False),
        sa.Column("step_no", sa.Integer, nullable=False),
        sa.Column("step_key", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("tool_name", sa.String(64), nullable=True),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB,
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "evidence",
            postgresql.JSONB,
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("truncated", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("step_id", name=F("pk_agent_step")),
        sa.ForeignKeyConstraint(
            ["project_id", "unit_id"],
            ["agent_work_unit.project_id", "agent_work_unit.unit_id"],
            name=F("fk_agent_step_unit_scope"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("unit_id", "step_no", name=F("uq_agent_step_unit_no")),
        sa.UniqueConstraint("unit_id", "step_key", name=F("uq_agent_step_unit_key")),
        sa.CheckConstraint(f"kind IN ({STEP_KINDS})", name=F("ck_agent_step_kind_known")),
        sa.CheckConstraint(
            f"outcome IS NULL OR outcome IN ({STEP_OUTCOMES})",
            name=F("ck_agent_step_outcome_known"),
        ),
        sa.CheckConstraint("step_no >= 1", name=F("ck_agent_step_no_positive")),
        sa.CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 1200", name=F("ck_agent_step_summary_bounded")
        ),
        sa.CheckConstraint(
            "octet_length(detail::text) <= 12288 AND octet_length(evidence::text) <= 12288 "
            "AND jsonb_typeof(detail) = 'object' AND jsonb_typeof(evidence) = 'array'",
            name=F("ck_agent_step_payload_bounded"),
        ),
        sa.CheckConstraint(
            "kind <> 'tool_call' OR tool_name IS NOT NULL", name=F("ck_agent_step_tool_named")
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_step")
    op.drop_index(F("ix_agent_work_unit_project_revision_state"), table_name="agent_work_unit")
    op.drop_index(F("ix_agent_work_unit_project_recent"), table_name="agent_work_unit")
    op.drop_table("agent_work_unit")

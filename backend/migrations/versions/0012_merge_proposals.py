"""AI identity-merge proposals, their review and the durable merge records (TASK-057, PF-7).

Revision ID: 0012_merge_proposals
Revises: 0011_processing_runs

``merge_proposal_run`` records one bounded model step (state, reason, usage). ``merge_proposal``
holds each proposal with its guard result and the user's decision (who/when); members carry the
alias evidence quotes. ``identity_merge`` is the only durable effect of an accepted proposal: the
deterministic resolver applies the active rows (``reverted_at IS NULL``) on every resolution, so a
revert restores the prior identities. Nothing here is written by the model; every status
transition is a user action or a server-side guard result. All rows are project scoped.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_merge_proposals"
down_revision: str | None = "0011_processing_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "merge_proposal_run",
        sa.Column("run_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(48), nullable=True),
        sa.Column("model_id", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("guard_version", sa.String(40), nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("blocks", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("deferred_blocks", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("proposals_created", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("proposals_dropped", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("drop_reasons", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("calls", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("provider_calls", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("run_id", name=F("pk_merge_proposal_run")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_merge_proposal_run_project_id_project")
        ),
        sa.UniqueConstraint("project_id", "run_id", name=F("uq_merge_proposal_run_scope")),
        sa.CheckConstraint(
            "state IN ('succeeded', 'partial', 'failed', 'no_candidates')",
            name=F("ck_merge_proposal_run_state_known"),
        ),
    )
    op.create_table(
        "merge_proposal",
        sa.Column("proposal_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("target_wellbore_id", UUID, nullable=True),
        sa.Column("target_key", sa.Text, nullable=False),
        sa.Column("guard_result", postgresql.JSONB, nullable=False),
        sa.Column("rationale", sa.Text, nullable=False),
        sa.Column("dataset_fingerprint", sa.String(64), nullable=False),
        sa.Column("decided_by", sa.String(80), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("proposal_id", name=F("pk_merge_proposal")),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["merge_proposal_run.project_id", "merge_proposal_run.run_id"],
            name=F("fk_merge_proposal_run_scope"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("project_id", "proposal_id", name=F("uq_merge_proposal_scope")),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'reverted', 'blocked')",
            name=F("ck_merge_proposal_status_known"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'blocked') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name=F("ck_merge_proposal_decision_recorded"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(guard_result) = 'array' AND octet_length(guard_result::text) <= 16384",
            name=F("ck_merge_proposal_guard_result_bounded"),
        ),
        sa.CheckConstraint(
            "status <> 'accepted' OR NOT (guard_result @> '[{\"passed\": false}]'::jsonb)",
            name=F("ck_merge_proposal_accepted_guards_passed"),
        ),
    )
    op.create_index(
        F("ix_merge_proposal_project_status"),
        "merge_proposal",
        ["project_id", "status", sa.text("created_at DESC"), sa.text("proposal_id DESC")],
    )
    op.create_table(
        "merge_proposal_member",
        sa.Column("proposal_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("role", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("source_key", sa.Text, nullable=False),
        sa.Column("display_name", sa.Text, nullable=False),
        sa.Column("wellbore_id", UUID, nullable=True),
        sa.Column("evidence", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.PrimaryKeyConstraint("proposal_id", "ordinal", name=F("pk_merge_proposal_member")),
        sa.ForeignKeyConstraint(
            ["project_id", "proposal_id"],
            ["merge_proposal.project_id", "merge_proposal.proposal_id"],
            name=F("fk_merge_proposal_member_proposal_scope"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("role IN ('target', 'member')", name=F("ck_merge_proposal_member_role_known")),
        sa.CheckConstraint("kind IN ('wellbore', 'label')", name=F("ck_merge_proposal_member_kind_known")),
        sa.CheckConstraint(
            "jsonb_typeof(evidence) = 'array' AND octet_length(evidence::text) <= 16384",
            name=F("ck_merge_proposal_member_evidence_bounded"),
        ),
    )
    op.create_table(
        "identity_merge",
        sa.Column("merge_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("proposal_id", UUID, nullable=False),
        sa.Column("source_kind", sa.String(8), nullable=False),
        sa.Column("source_key", sa.Text, nullable=False),
        sa.Column("target_key", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.Column("decided_by", sa.String(80), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverted_by", sa.String(80), nullable=True),
        sa.PrimaryKeyConstraint("merge_id", name=F("pk_identity_merge")),
        sa.ForeignKeyConstraint(
            ["project_id", "proposal_id"],
            ["merge_proposal.project_id", "merge_proposal.proposal_id"],
            name=F("fk_identity_merge_proposal_scope"),
        ),
        sa.CheckConstraint(
            "source_kind IN ('wellbore', 'label')", name=F("ck_identity_merge_source_kind_known")
        ),
        sa.CheckConstraint(
            "source_key <> target_key", name=F("ck_identity_merge_source_is_not_target")
        ),
        sa.CheckConstraint(
            "(reverted_at IS NULL) = (reverted_by IS NULL)",
            name=F("ck_identity_merge_revert_recorded"),
        ),
    )
    op.create_index(
        F("uq_identity_merge_active_source"),
        "identity_merge",
        ["project_id", "source_kind", "source_key"],
        unique=True,
        postgresql_where=sa.text("reverted_at IS NULL"),
    )
    op.create_index(F("ix_identity_merge_proposal"), "identity_merge", ["project_id", "proposal_id"])


def downgrade() -> None:
    op.drop_table("identity_merge")
    op.drop_table("merge_proposal_member")
    op.drop_table("merge_proposal")
    op.drop_table("merge_proposal_run")

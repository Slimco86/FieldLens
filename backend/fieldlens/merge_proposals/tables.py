"""Merge-proposal tables (migration 0012 is authoritative; constraints live there)."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from fieldlens.persistence.models import metadata

_NOW = text("now()")
_UUID_DEFAULT = text("gen_random_uuid()")

merge_proposal_run = Table(
    "merge_proposal_run",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("state", String(24), nullable=False),
    Column("reason", String(48), nullable=True),
    Column("model_id", String(80), nullable=False),
    Column("prompt_version", String(40), nullable=False),
    Column("guard_version", String(40), nullable=False),
    Column("dataset_fingerprint", String(64), nullable=False),
    Column("blocks", Integer, nullable=False, server_default=text("0")),
    Column("deferred_blocks", Integer, nullable=False, server_default=text("0")),
    Column("proposals_created", Integer, nullable=False, server_default=text("0")),
    Column("proposals_dropped", Integer, nullable=False, server_default=text("0")),
    Column("drop_reasons", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("calls", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("provider_calls", Integer, nullable=False, server_default=text("0")),
    Column("input_tokens", Integer, nullable=True),
    Column("output_tokens", Integer, nullable=True),
    Column("cost_usd", Numeric(12, 6), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=_NOW),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id"], ["project.project_id"], name="fk_merge_proposal_run_project_id_project"
    ),
    UniqueConstraint("project_id", "run_id", name="uq_merge_proposal_run_scope"),
    CheckConstraint(
        "state IN ('succeeded', 'partial', 'failed', 'no_candidates')", name="state_known"
    ),
)

merge_proposal = Table(
    "merge_proposal",
    metadata,
    Column("proposal_id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(12), nullable=False),
    Column("target_wellbore_id", UUID(as_uuid=True), nullable=True),
    Column("target_key", Text, nullable=False),
    Column("guard_result", JSONB, nullable=False),
    Column("rationale", Text, nullable=False),
    Column("dataset_fingerprint", String(64), nullable=False),
    Column("decided_by", String(80), nullable=True),
    Column("decided_at", DateTime(timezone=True), nullable=True),
    Column("decision_note", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=_NOW),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["merge_proposal_run.project_id", "merge_proposal_run.run_id"],
        name="fk_merge_proposal_run_scope",
        ondelete="CASCADE",
    ),
    UniqueConstraint("project_id", "proposal_id", name="uq_merge_proposal_scope"),
    CheckConstraint(
        "status IN ('pending', 'accepted', 'rejected', 'reverted', 'blocked')",
        name="status_known",
    ),
    CheckConstraint(
        "status IN ('pending', 'blocked') OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
        name="decision_recorded",
    ),
    CheckConstraint(
        "jsonb_typeof(guard_result) = 'array' AND octet_length(guard_result::text) <= 16384",
        name="guard_result_bounded",
    ),
    CheckConstraint(
        "status <> 'accepted' OR NOT (guard_result @> '[{\"passed\": false}]'::jsonb)",
        name="accepted_guards_passed",
    ),
    Index(
        "ix_merge_proposal_project_status",
        "project_id",
        "status",
        text("created_at DESC"),
        text("proposal_id DESC"),
    ),
)

merge_proposal_member = Table(
    "merge_proposal_member",
    metadata,
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("role", String(8), nullable=False),
    Column("kind", String(8), nullable=False),
    Column("source_key", Text, nullable=False),
    Column("display_name", Text, nullable=False),
    Column("wellbore_id", UUID(as_uuid=True), nullable=True),
    Column("evidence", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    PrimaryKeyConstraint("proposal_id", "ordinal"),
    ForeignKeyConstraint(
        ["project_id", "proposal_id"],
        ["merge_proposal.project_id", "merge_proposal.proposal_id"],
        name="fk_merge_proposal_member_proposal_scope",
        ondelete="CASCADE",
    ),
    CheckConstraint("role IN ('target', 'member')", name="role_known"),
    CheckConstraint("kind IN ('wellbore', 'label')", name="kind_known"),
    CheckConstraint(
        "jsonb_typeof(evidence) = 'array' AND octet_length(evidence::text) <= 16384",
        name="evidence_bounded",
    ),
)

STATUSES = ("pending", "accepted", "rejected", "reverted", "blocked")

"""Reconstruction-run tables (migration 0013 is authoritative).

``reconstruction_estimate`` groups the runs one estimate created; one confirm covers the group.
``reconstruction_run`` is per wellbore. ``wellbore_id`` is deliberately not a foreign key: the
deterministic identity resolver may delete and recreate wellbores, and a run must keep its
(snapshotted) identity as history. A partial unique index lets a wellbore + source revision have at
most one queued/running run. ``reconstruction_run_stage`` holds S1..S5 with honest per-stage state.
"""

from __future__ import annotations

from sqlalchemy import (
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
STAGES = ("gather", "extract", "identify", "assemble", "design")
STAGE_STATES = (
    "pending",
    "running",
    "succeeded",
    "not_available",
    "failed",
    "cancelled",
    "interrupted",
    "skipped",
    "stubbed",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


reconstruction_estimate = Table(
    "reconstruction_estimate",
    metadata,
    Column(
        "estimate_id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("total_estimated_usd", USD, nullable=False),
    Column("pricing_source", String(40), nullable=False),
    Column("total_cap_usd", USD, nullable=False),
    Column("remaining_budget_usd", USD, nullable=False),
    Column("confirmed_usd", USD, nullable=True),
    Column("confirmed_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id"], ["project.project_id"], name="fk_reconstruction_estimate_project"
    ),
    UniqueConstraint("project_id", "estimate_id", name="uq_reconstruction_estimate_scope"),
    CheckConstraint(
        "total_estimated_usd >= 0 AND remaining_budget_usd >= 0", name="amounts_nonnegative"
    ),
)

reconstruction_run = Table(
    "reconstruction_run",
    metadata,
    Column(
        "run_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("estimate_id", UUID(as_uuid=True), nullable=False),
    Column("well_id", UUID(as_uuid=True), nullable=False),
    Column("wellbore_id", UUID(as_uuid=True), nullable=False),
    Column("wellbore_name", Text, nullable=False),
    Column("status", String(16), nullable=False),
    Column("source_revision", String(64), nullable=False),
    Column("retry_of_run_id", UUID(as_uuid=True), nullable=True),
    Column("pricing_source", String(40), nullable=False),
    Column("estimated_usd", USD, nullable=False),
    Column("confirmed_usd", USD, nullable=True),
    Column("actual_usd", USD, nullable=False, server_default=text("0")),
    Column("cancel_requested", Boolean, nullable=False, server_default=text("false")),
    Column("attempt_no", Integer, nullable=False, server_default=text("0")),
    Column("lease_owner", String(128), nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("error_code", String(48), nullable=True),
    Column("error_message", String(400), nullable=True),
    Column("summary", JSONB, nullable=True),
    Column("invalidated_at", DateTime(timezone=True), nullable=True),
    Column("invalidated_reason", String(48), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("confirmed_at", DateTime(timezone=True), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id"], ["project.project_id"], name="fk_reconstruction_run_project"
    ),
    ForeignKeyConstraint(
        ["project_id", "estimate_id"],
        ["reconstruction_estimate.project_id", "reconstruction_estimate.estimate_id"],
        name="fk_reconstruction_run_estimate_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "retry_of_run_id"],
        ["reconstruction_run.project_id", "reconstruction_run.run_id"],
        name="fk_reconstruction_run_retry_scope",
    ),
    UniqueConstraint("project_id", "run_id", name="uq_reconstruction_run_scope"),
    CheckConstraint(_in("status", RUN_STATUSES), name="status_known"),
    CheckConstraint(
        "estimated_usd >= 0 AND actual_usd >= 0 AND char_length(source_revision) = 64",
        name="amounts_nonnegative",
    ),
    CheckConstraint(
        "status NOT IN ('queued', 'running', 'succeeded', 'partial') OR confirmed_usd IS NOT NULL",
        name="started_requires_confirmation",
    ),
    CheckConstraint(
        "status NOT IN ('succeeded', 'partial', 'failed', 'cancelled', 'interrupted') "
        "OR finished_at IS NOT NULL",
        name="terminal_has_finish_time",
    ),
    Index(
        "uq_reconstruction_run_active",
        "project_id",
        "wellbore_id",
        "source_revision",
        unique=True,
        postgresql_where=text("status IN ('queued', 'running')"),
    ),
    Index(
        "ix_reconstruction_run_project_recent",
        "project_id",
        text("created_at DESC"),
        text("run_id DESC"),
    ),
    Index(
        "ix_reconstruction_run_claimable",
        "status",
        "confirmed_at",
        postgresql_where=text("status IN ('queued', 'running')"),
    ),
    Index("ix_reconstruction_run_estimate", "project_id", "estimate_id"),
)

reconstruction_run_stage = Table(
    "reconstruction_run_stage",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("stage", String(12), primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("kind", String(14), nullable=False),
    Column("state", String(16), nullable=False),
    Column("reason_code", String(48), nullable=True),
    Column("message", String(400), nullable=True),
    Column("counts", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("input_tokens", BigInteger, nullable=False, server_default=text("0")),
    Column("output_tokens", BigInteger, nullable=False, server_default=text("0")),
    Column("estimated_usd", USD, nullable=False, server_default=text("0")),
    Column("actual_usd", USD, nullable=False, server_default=text("0")),
    Column("error_code", String(48), nullable=True),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["reconstruction_run.project_id", "reconstruction_run.run_id"],
        name="fk_reconstruction_run_stage_run_scope",
        ondelete="CASCADE",
    ),
    CheckConstraint(_in("stage", STAGES), name="stage_known"),
    CheckConstraint(_in("state", STAGE_STATES), name="state_known"),
    CheckConstraint("kind IN ('deterministic', 'agent')", name="kind_known"),
    CheckConstraint("ordinal BETWEEN 1 AND 5", name="ordinal_bounded"),
    CheckConstraint(
        "input_tokens >= 0 AND output_tokens >= 0 AND estimated_usd >= 0 AND actual_usd >= 0",
        name="amounts_nonnegative",
    ),
    CheckConstraint(
        "state <> 'not_available' OR reason_code IS NOT NULL", name="unavailable_has_reason"
    ),
    CheckConstraint("state <> 'failed' OR error_code IS NOT NULL", name="failed_has_error_code"),
    CheckConstraint(
        "state <> 'not_available' OR (actual_usd = 0 AND input_tokens = 0 AND output_tokens = 0)",
        name="unavailable_spent_nothing",
    ),
)

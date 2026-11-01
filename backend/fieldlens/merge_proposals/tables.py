"""Merge-proposal tables (migration 0012 is authoritative; constraints live there)."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
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
)

STATUSES = ("pending", "accepted", "rejected", "reverted", "blocked")

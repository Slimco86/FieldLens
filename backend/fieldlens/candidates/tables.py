"""Candidate table (migration 0010 is authoritative): model proposals and their validator state.

Project scoping is structural (composite foreign keys). The CHECK constraints are the last line
of defence for AX-13: a ``model_read`` row can never be ``accepted`` or ``valid``."""

from __future__ import annotations

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from fieldlens.persistence.models import metadata

CANDIDATE_STATES = ("candidate", "accepted", "rejected", "flagged")
CANDIDATE_METHODS = ("model_proposal", "model_read")

extraction_candidate = Table(
    "extraction_candidate",
    metadata,
    Column(
        "candidate_id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("unit_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("wellbore_id", UUID(as_uuid=True), nullable=True),
    Column("candidate_key", String(64), nullable=False),
    Column("subject", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("method", String(16), nullable=False),
    Column("evidence_class", String(24), nullable=False, server_default=text("'model_proposal'")),
    Column("validation_state", String(16), nullable=False),
    Column("state", String(16), nullable=False),
    Column("label", Text, nullable=False),
    Column("reason_codes", ARRAY(Text), nullable=False, server_default=text("'{}'")),
    Column("validator_results", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("attributes", JSONB, nullable=False),
    Column("quote", Text, nullable=True),
    Column("locator", JSONB, nullable=False),
    Column("conflicts_with_record_id", UUID(as_uuid=True), nullable=True),
    Column("model_id", String(80), nullable=False),
    Column("prompt_version", String(40), nullable=False),
    Column("harness_version", String(40), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "unit_id"],
        ["agent_work_unit.project_id", "agent_work_unit.unit_id"],
        name="fk_extraction_candidate_unit_scope",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_extraction_candidate_revision_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_extraction_candidate_document_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "wellbore_id"],
        ["wellbore.project_id", "wellbore.wellbore_id"],
        name="fk_extraction_candidate_wellbore_scope",
    ),
    UniqueConstraint("unit_id", "candidate_key", name="uq_extraction_candidate_unit_key"),
    CheckConstraint(
        "state IN ('candidate', 'accepted', 'rejected', 'flagged')", name="state_known"
    ),
    CheckConstraint("method IN ('model_proposal', 'model_read')", name="method_known"),
    CheckConstraint("evidence_class = 'model_proposal'", name="evidence_class_model_proposal"),
    CheckConstraint(
        "method <> 'model_read' OR (state <> 'accepted' AND validation_state = 'unverified')",
        name="model_read_never_accepted",
    ),
    CheckConstraint(
        "state <> 'accepted' OR (method = 'model_proposal' AND validation_state = 'valid')",
        name="accepted_requires_valid",
    ),
    CheckConstraint(
        "state NOT IN ('rejected', 'flagged') OR cardinality(reason_codes) >= 1",
        name="decided_has_reason",
    ),
    CheckConstraint(
        "jsonb_typeof(attributes) = 'object' AND attributes ? 'kind' "
        "AND octet_length(attributes::text) <= 8192 "
        "AND jsonb_typeof(validator_results) = 'array' "
        "AND octet_length(validator_results::text) <= 8192",
        name="payload_bounded",
    ),
    CheckConstraint("quote IS NULL OR char_length(quote) <= 400", name="quote_bounded"),
    Index(
        "ix_extraction_candidate_document_state",
        "project_id",
        "document_id",
        "state",
        text("created_at DESC"),
        text("candidate_id DESC"),
    ),
    Index("ix_extraction_candidate_unit", "unit_id"),
)

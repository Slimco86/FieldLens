"""Identity link table (migration 0008 is authoritative).

``record_wellbore_link`` maps an ``extracted_record`` (by its run and ordinal) to the resolved
``wellbore``. It is derived and rebuildable: deleting the record, its run or the wellbore removes
the link, and every row is project-scoped through composite foreign keys. The original record
and its subject stay the evidence authority."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from fieldlens.persistence.models import metadata

# Durable, user-decided identity merges (migration 0012 is authoritative). An accepted merge
# proposal inserts one row per merged source; the resolver applies the active rows
# (``reverted_at IS NULL``) on every resolution, so reverting restores the prior identities.
identity_merge = Table(
    "identity_merge",
    metadata,
    Column(
        "merge_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("source_kind", String(8), nullable=False),  # 'label' | 'wellbore'
    Column("source_key", Text, nullable=False),
    Column("target_key", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("decided_by", String(80), nullable=False),
    Column("reverted_at", DateTime(timezone=True), nullable=True),
    Column("reverted_by", String(80), nullable=True),
    Index(
        "uq_identity_merge_active_source",
        "project_id",
        "source_kind",
        "source_key",
        unique=True,
        postgresql_where=text("reverted_at IS NULL"),
    ),
)

record_wellbore_link = Table(
    "record_wellbore_link",
    metadata,
    Column("run_id", UUID(as_uuid=True), primary_key=True),
    Column("ordinal", Integer, primary_key=True),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("wellbore_id", UUID(as_uuid=True), nullable=False),
    Column("basis", String(24), nullable=False),
    ForeignKeyConstraint(
        ["run_id", "ordinal"],
        ["extracted_record.run_id", "extracted_record.ordinal"],
        name="fk_record_wellbore_link_record",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["extraction_run.project_id", "extraction_run.run_id"],
        name="fk_record_wellbore_link_run_scope",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "wellbore_id"],
        ["wellbore.project_id", "wellbore.wellbore_id"],
        name="fk_record_wellbore_link_wellbore_scope",
        ondelete="CASCADE",
    ),
    Index("ix_record_wellbore_link_wellbore", "project_id", "wellbore_id"),
)

"""Identity link table (migration 0008 is authoritative).

``record_wellbore_link`` maps an ``extracted_record`` (by its run and ordinal) to the resolved
``wellbore``. It is derived and rebuildable: deleting the record, its run or the wellbore removes
the link, and every row is project-scoped through composite foreign keys. The original record
and its subject stay the evidence authority."""

from __future__ import annotations

from sqlalchemy import (
    Column,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
)
from sqlalchemy.dialects.postgresql import UUID

from fieldlens.persistence.models import metadata

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

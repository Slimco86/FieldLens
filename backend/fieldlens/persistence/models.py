"""Core relational schema (SQLAlchemy Core metadata; the Alembic migration is authoritative).

Every child row carries ``project_id`` and uses composite ``(project_id, id)`` foreign keys, so
project/revision/subject joins cannot cross project scopes. No engineering, provider or job
tables live here; later packets add their own through their own migrations.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING)


def _uuid_pk(name: str) -> Column[Any]:
    return Column(
        name, UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _created_at() -> Column[Any]:
    return Column(
        "created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


project = Table(
    "project",
    metadata,
    _uuid_pk("project_id"),
    Column("name", String(120), nullable=False),
    Column("description", Text, nullable=False, server_default=text("''")),
    _created_at(),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("latest_source_revision_id", UUID(as_uuid=True), nullable=True),
    Column("active_model_revision_id", UUID(as_uuid=True), nullable=True),
    CheckConstraint("char_length(name) >= 1 AND name = btrim(name)", name="name_trimmed"),
    CheckConstraint("char_length(description) <= 4000", name="description_max_length"),
    Index(
        "ix_project_created_at_project_id",
        text("created_at DESC"),
        text("project_id DESC"),
    ),
)

source_revision = Table(
    "source_revision",
    metadata,
    _uuid_pk("source_revision_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("parent_source_revision_id", UUID(as_uuid=True), nullable=True),
    Column("manifest_hash", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    _created_at(),
    Column("coverage", JSONB, nullable=True),
    UniqueConstraint("project_id", "source_revision_id", name="uq_source_revision_project_scope"),
    ForeignKeyConstraint(
        ["project_id", "parent_source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_source_revision_parent_scope",
    ),
    CheckConstraint("manifest_hash ~ '^[0-9a-f]{64}$'", name="manifest_hash_sha256"),
    CheckConstraint(
        "status IN ('staging','ready','ready_with_issues','failed')", name="status_known"
    ),
    CheckConstraint(
        "parent_source_revision_id IS DISTINCT FROM source_revision_id", name="not_own_parent"
    ),
)

model_revision = Table(
    "model_revision",
    metadata,
    _uuid_pk("revision_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("pinned_source_revision_id", UUID(as_uuid=True), nullable=False),
    Column("base_revision_id", UUID(as_uuid=True), nullable=True),
    Column("status", String(32), nullable=False),
    _created_at(),
    Column("coverage", JSONB, nullable=True),
    UniqueConstraint("project_id", "revision_id", name="uq_model_revision_project_scope"),
    ForeignKeyConstraint(
        ["project_id", "pinned_source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_model_revision_source_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "base_revision_id"],
        ["model_revision.project_id", "model_revision.revision_id"],
        name="fk_model_revision_base_scope",
    ),
    CheckConstraint("status IN ('draft','validated','published','rejected')", name="status_known"),
    CheckConstraint("base_revision_id IS DISTINCT FROM revision_id", name="not_own_base"),
)

# Project pointers are project-qualified too (deferred: a project precedes its revisions).
project.append_constraint(
    ForeignKeyConstraint(
        ["project_id", "latest_source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_project_latest_source_scope",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    )
)
project.append_constraint(
    ForeignKeyConstraint(
        ["project_id", "active_model_revision_id"],
        ["model_revision.project_id", "model_revision.revision_id"],
        name="fk_project_active_model_scope",
        use_alter=True,
        deferrable=True,
        initially="DEFERRED",
    )
)

source_document = Table(
    "source_document",
    metadata,
    _uuid_pk("document_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("sha256", String(64), nullable=False),
    Column("size_bytes", BigInteger, nullable=False),
    Column("original_filename", String(512), nullable=False),
    Column("detected_media_type", String(255), nullable=True),
    Column("origin_metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("storage_key", Text, nullable=False),
    _created_at(),
    UniqueConstraint("project_id", "document_id", name="uq_source_document_project_scope"),
    CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
    CheckConstraint("size_bytes >= 0", name="size_nonnegative"),
)

source_revision_document = Table(
    "source_revision_document",
    metadata,
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("source_revision_id", UUID(as_uuid=True), primary_key=True),
    Column("document_id", UUID(as_uuid=True), primary_key=True),
    ForeignKeyConstraint(
        ["project_id", "source_revision_id"],
        ["source_revision.project_id", "source_revision.source_revision_id"],
        name="fk_srd_revision_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_srd_document_scope",
    ),
)

well = Table(
    "well",
    metadata,
    _uuid_pk("well_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("name", Text, nullable=False),
    UniqueConstraint("project_id", "well_id", name="uq_well_project_scope"),
    CheckConstraint("char_length(name) >= 1", name="name_nonempty"),
)

wellbore = Table(
    "wellbore",
    metadata,
    _uuid_pk("wellbore_id"),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("well_id", UUID(as_uuid=True), nullable=False),
    Column("parent_wellbore_id", UUID(as_uuid=True), nullable=True),
    Column("name", Text, nullable=False),
    UniqueConstraint("project_id", "wellbore_id", name="uq_wellbore_project_scope"),
    ForeignKeyConstraint(
        ["project_id", "well_id"],
        ["well.project_id", "well.well_id"],
        name="fk_wellbore_well_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "parent_wellbore_id"],
        ["wellbore.project_id", "wellbore.wellbore_id"],
        name="fk_wellbore_parent_scope",
    ),
    CheckConstraint("char_length(name) >= 1", name="name_nonempty"),
    CheckConstraint("parent_wellbore_id IS DISTINCT FROM wellbore_id", name="not_own_parent"),
)

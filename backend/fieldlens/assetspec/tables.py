"""Wellbore asset spec table (migration 0019 is authoritative).

One row per generated revision, keyed by project + wellbore + revision. ``wellbore_id`` is not a
foreign key (the identity resolver may recreate wellbores; the spec keeps its snapshot identity and
is invalidated by the merge/revert hook). A partial unique index allows exactly one ``current``
row per wellbore; earlier valid generations stay as ``superseded`` history.
"""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from fieldlens.persistence.models import metadata

SPEC_STATES = ("current", "superseded", "invalidated")
MAX_SPEC_JSON_BYTES = 262144

wellbore_asset_spec = Table(
    "wellbore_asset_spec",
    metadata,
    Column(
        "spec_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("wellbore_id", UUID(as_uuid=True), nullable=False),
    Column("revision", Integer, nullable=False),
    Column("state", String(16), nullable=False),
    Column("source_revision", String(64), nullable=False),
    Column("generator_provider", String(40), nullable=False),
    Column("generator_model", String(80), nullable=False),
    Column("spec", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id"], ["project.project_id"], name="fk_wellbore_asset_spec_project"
    ),
    UniqueConstraint(
        "project_id", "wellbore_id", "revision", name="uq_wellbore_asset_spec_revision"
    ),
    CheckConstraint("state IN ('current','superseded','invalidated')", name="state_known"),
    CheckConstraint("revision >= 1", name="revision_positive"),
    CheckConstraint(
        f"octet_length(spec::text) <= {MAX_SPEC_JSON_BYTES}",
        name="size_bounded",
    ),
    CheckConstraint("spec->>'visual_only' = 'true'", name="visual_only"),
    Index(
        "uq_wellbore_asset_spec_current",
        "project_id",
        "wellbore_id",
        unique=True,
        postgresql_where=text("state = 'current'"),
    ),
)

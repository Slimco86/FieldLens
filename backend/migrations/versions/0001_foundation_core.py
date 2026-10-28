"""Core identity, revision and membership tables; pgvector extension.

Revision ID: 0001_foundation_core
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation_core"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")


def _pk(table: str, col: str) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(col, UUID, primary_key=True, server_default=GEN_UUID)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "project",
        _pk("project", "project_id"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("latest_source_revision_id", UUID, nullable=True),
        sa.Column("active_model_revision_id", UUID, nullable=True),
        sa.CheckConstraint(
            "char_length(name) >= 1 AND name = btrim(name)", name=F("ck_project_name_trimmed")
        ),
        sa.PrimaryKeyConstraint("project_id", name=F("pk_project")),
    )

    op.create_table(
        "source_revision",
        _pk("source_revision", "source_revision_id"),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("parent_source_revision_id", UUID, nullable=True),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("coverage", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("source_revision_id", name=F("pk_source_revision")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_source_revision_project_id")
        ),
        sa.UniqueConstraint(
            "project_id", "source_revision_id", name=F("uq_source_revision_project_scope")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "parent_source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_source_revision_parent_scope"),
        ),
        sa.CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$'", name=F("ck_source_revision_manifest_hash_sha256")
        ),
        sa.CheckConstraint(
            "status IN ('staging','ready','ready_with_issues','failed')",
            name=F("ck_source_revision_status_known"),
        ),
        sa.CheckConstraint(
            "parent_source_revision_id IS DISTINCT FROM source_revision_id",
            name=F("ck_source_revision_not_own_parent"),
        ),
    )

    op.create_table(
        "model_revision",
        _pk("model_revision", "revision_id"),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("pinned_source_revision_id", UUID, nullable=False),
        sa.Column("base_revision_id", UUID, nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("coverage", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("revision_id", name=F("pk_model_revision")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_model_revision_project_id")
        ),
        sa.UniqueConstraint(
            "project_id", "revision_id", name=F("uq_model_revision_project_scope")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "pinned_source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_model_revision_source_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "base_revision_id"],
            ["model_revision.project_id", "model_revision.revision_id"],
            name=F("fk_model_revision_base_scope"),
        ),
        sa.CheckConstraint(
            "status IN ('draft','validated','published','rejected')",
            name=F("ck_model_revision_status_known"),
        ),
        sa.CheckConstraint(
            "base_revision_id IS DISTINCT FROM revision_id",
            name=F("ck_model_revision_not_own_base"),
        ),
    )

    op.create_foreign_key(
        F("fk_project_latest_source_scope"),
        "project",
        "source_revision",
        ["project_id", "latest_source_revision_id"],
        ["project_id", "source_revision_id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_foreign_key(
        F("fk_project_active_model_scope"),
        "project",
        "model_revision",
        ["project_id", "active_model_revision_id"],
        ["project_id", "revision_id"],
        deferrable=True,
        initially="DEFERRED",
    )

    op.create_table(
        "source_document",
        _pk("source_document", "document_id"),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("detected_media_type", sa.String(255), nullable=True),
        sa.Column(
            "origin_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.PrimaryKeyConstraint("document_id", name=F("pk_source_document")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_source_document_project_id")
        ),
        sa.UniqueConstraint(
            "project_id", "document_id", name=F("uq_source_document_project_scope")
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=F("ck_source_document_sha256_hex")),
        sa.CheckConstraint("size_bytes >= 0", name=F("ck_source_document_size_nonnegative")),
    )

    op.create_table(
        "source_revision_document",
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.PrimaryKeyConstraint(
            "source_revision_id", "document_id", name=F("pk_source_revision_document")
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_srd_revision_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_srd_document_scope"),
        ),
    )

    op.create_table(
        "well",
        _pk("well", "well_id"),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("well_id", name=F("pk_well")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_well_project_id")
        ),
        sa.UniqueConstraint("project_id", "well_id", name=F("uq_well_project_scope")),
        sa.CheckConstraint("char_length(name) >= 1", name=F("ck_well_name_nonempty")),
    )

    op.create_table(
        "wellbore",
        _pk("wellbore", "wellbore_id"),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("well_id", UUID, nullable=False),
        sa.Column("parent_wellbore_id", UUID, nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("wellbore_id", name=F("pk_wellbore")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_wellbore_project_id")
        ),
        sa.UniqueConstraint("project_id", "wellbore_id", name=F("uq_wellbore_project_scope")),
        sa.ForeignKeyConstraint(
            ["project_id", "well_id"],
            ["well.project_id", "well.well_id"],
            name=F("fk_wellbore_well_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "parent_wellbore_id"],
            ["wellbore.project_id", "wellbore.wellbore_id"],
            name=F("fk_wellbore_parent_scope"),
        ),
        sa.CheckConstraint("char_length(name) >= 1", name=F("ck_wellbore_name_nonempty")),
        sa.CheckConstraint(
            "parent_wellbore_id IS DISTINCT FROM wellbore_id",
            name=F("ck_wellbore_not_own_parent"),
        ),
    )

    # Sidetrack ancestry must stay acyclic (a self-parent is already a CHECK violation).
    op.execute(
        """
        CREATE FUNCTION wellbore_reject_parent_cycle() RETURNS trigger AS $$
        BEGIN
          IF NEW.parent_wellbore_id IS NULL THEN
            RETURN NEW;
          END IF;
          IF EXISTS (
            WITH RECURSIVE ancestors(id) AS (
              SELECT NEW.parent_wellbore_id
              UNION
              SELECT w.parent_wellbore_id
              FROM wellbore w JOIN ancestors a ON w.wellbore_id = a.id
              WHERE w.parent_wellbore_id IS NOT NULL
            )
            SELECT 1 FROM ancestors WHERE id = NEW.wellbore_id
          ) THEN
            RAISE EXCEPTION 'wellbore parent cycle' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER wellbore_parent_acyclic BEFORE INSERT OR UPDATE OF parent_wellbore_id "
        "ON wellbore FOR EACH ROW EXECUTE FUNCTION wellbore_reject_parent_cycle()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS wellbore_parent_acyclic ON wellbore")
    op.execute("DROP FUNCTION IF EXISTS wellbore_reject_parent_cycle()")
    op.drop_table("wellbore")
    op.drop_table("well")
    op.drop_table("source_revision_document")
    op.drop_table("source_document")
    op.drop_constraint(F("fk_project_active_model_scope"), "project", type_="foreignkey")
    op.drop_constraint(F("fk_project_latest_source_scope"), "project", type_="foreignkey")
    op.drop_table("model_revision")
    op.drop_table("source_revision")
    op.drop_table("project")
    op.execute("DROP EXTENSION IF EXISTS vector")

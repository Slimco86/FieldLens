"""Deterministic well/wellbore identity: canonical keys and the record -> wellbore link.

Revision ID: 0008_identity_links
Revises: 0007_source_retrieval

Adds nullable canonical key columns to the (so far empty) ``well``/``wellbore`` tables with
project-scoped unique indexes, and the derived ``record_wellbore_link`` table (TASK-046). Links
cascade away with their record, run or wellbore.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_identity_links"
down_revision: str | None = "0007_source_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("well", sa.Column("well_key", sa.Text, nullable=True))
    op.create_index("uq_well_project_key", "well", ["project_id", "well_key"], unique=True)
    op.add_column("wellbore", sa.Column("wellbore_key", sa.Text, nullable=True))
    op.add_column("wellbore", sa.Column("suffix", sa.Text, nullable=True))
    op.create_index(
        "uq_wellbore_project_key", "wellbore", ["project_id", "wellbore_key"], unique=True
    )
    op.create_table(
        "record_wellbore_link",
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("wellbore_id", UUID, nullable=False),
        sa.Column("basis", sa.String(24), nullable=False),
        sa.PrimaryKeyConstraint("run_id", "ordinal", name=F("pk_record_wellbore_link")),
        sa.ForeignKeyConstraint(
            ["run_id", "ordinal"],
            ["extracted_record.run_id", "extracted_record.ordinal"],
            name=F("fk_record_wellbore_link_record"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["extraction_run.project_id", "extraction_run.run_id"],
            name=F("fk_record_wellbore_link_run_scope"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "wellbore_id"],
            ["wellbore.project_id", "wellbore.wellbore_id"],
            name=F("fk_record_wellbore_link_wellbore_scope"),
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        F("ix_record_wellbore_link_wellbore"),
        "record_wellbore_link",
        ["project_id", "wellbore_id"],
    )


def downgrade() -> None:
    op.drop_index(F("ix_record_wellbore_link_wellbore"), table_name="record_wellbore_link")
    op.drop_table("record_wellbore_link")
    op.drop_index("uq_wellbore_project_key", table_name="wellbore")
    op.drop_column("wellbore", "suffix")
    op.drop_column("wellbore", "wellbore_key")
    op.drop_index("uq_well_project_key", table_name="well")
    op.drop_column("well", "well_key")

"""Visual asset spec table (TASK-077): one row per generated revision, one ``current`` per wellbore.

Revision ID: 0019_asset_spec
Revises: 0017_model_reply

NOTE FOR THE ORCHESTRATOR: ``down_revision`` is 0017 because this lane branched before TASK-076's
0018. When merging after 0018, change ``down_revision`` to the 0018 revision id (nothing else here
depends on it).

``wellbore_id`` is deliberately not a foreign key (the identity resolver may recreate wellbores);
the project purge handles the table (``wellbore_asset_spec`` in ``PURGE_ORDER``).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_asset_spec"
down_revision: str | None = "0017_model_reply"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "wellbore_asset_spec",
        sa.Column("spec_id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("wellbore_id", UUID, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("source_revision", sa.String(64), nullable=False),
        sa.Column("generator_provider", sa.String(40), nullable=False),
        sa.Column("generator_model", sa.String(80), nullable=False),
        sa.Column("spec", postgresql.JSONB, nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("spec_id", name=F("pk_wellbore_asset_spec")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_wellbore_asset_spec_project")
        ),
        sa.UniqueConstraint(
            "project_id", "wellbore_id", "revision", name=F("uq_wellbore_asset_spec_revision")
        ),
        sa.CheckConstraint(
            "state IN ('current','superseded','invalidated')",
            name=F("ck_wellbore_asset_spec_state_known"),
        ),
        sa.CheckConstraint("revision >= 1", name=F("ck_wellbore_asset_spec_revision_positive")),
        sa.CheckConstraint(
            "octet_length(spec::text) <= 262144", name=F("ck_wellbore_asset_spec_size_bounded")
        ),
        sa.CheckConstraint(
            "spec->>'visual_only' = 'true'", name=F("ck_wellbore_asset_spec_visual_only")
        ),
    )
    op.create_index(
        "uq_wellbore_asset_spec_current",
        "wellbore_asset_spec",
        ["project_id", "wellbore_id"],
        unique=True,
        postgresql_where=sa.text("state = 'current'"),
    )


def downgrade() -> None:
    op.drop_index("uq_wellbore_asset_spec_current", table_name="wellbore_asset_spec")
    op.drop_table("wellbore_asset_spec")

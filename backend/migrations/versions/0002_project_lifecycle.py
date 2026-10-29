"""Project lifecycle: description bound and newest-first keyset index.

Revision ID: 0002_project_lifecycle
Revises: 0001_foundation_core
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_project_lifecycle"
down_revision: str | None = "0001_foundation_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f


def upgrade() -> None:
    op.create_check_constraint(
        F("ck_project_description_max_length"), "project", "char_length(description) <= 4000"
    )
    op.create_index(
        F("ix_project_created_at_project_id"),
        "project",
        [sa.text("created_at DESC"), sa.text("project_id DESC")],
    )


def downgrade() -> None:
    op.drop_index(F("ix_project_created_at_project_id"), table_name="project")
    op.drop_constraint(F("ck_project_description_max_length"), "project", type_="check")

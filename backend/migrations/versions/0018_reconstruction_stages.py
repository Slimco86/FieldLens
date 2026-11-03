"""Reconstruction stage redesign: five stages, stubbed state, invalidated drafts (TASK-076).

Revision ID: 0018_reconstruction_stages
Revises: 0017_model_reply

* ``reconstruction_run_stage``: the stage list gains ``design`` (S5), ordinal up to 5 and a
  ``stubbed`` state (an agent step ran on the stub provider: no model was called).
* ``reconstruction_run``: ``invalidated_at`` / ``invalidated_reason`` mark a draft that a merge
  application or revert made out of date (WELLBORE_ASSET_GENERATION section 12).
No new table: the project purge is unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_reconstruction_stages"
down_revision: str | None = "0017_model_reply"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
T = "reconstruction_run_stage"
OLD_STAGES = "('gather', 'extract', 'identify', 'assemble')"
NEW_STAGES = "('gather', 'extract', 'identify', 'assemble', 'design')"
OLD_STATES = (
    "('pending', 'running', 'succeeded', 'not_available', 'failed', 'cancelled', "
    "'interrupted', 'skipped')"
)
NEW_STATES = (
    "('pending', 'running', 'succeeded', 'not_available', 'failed', 'cancelled', "
    "'interrupted', 'skipped', 'stubbed')"
)


def _swap(stage_sql: str, state_sql: str, max_ordinal: int) -> None:
    for name in ("stage_known", "state_known", "ordinal_bounded"):
        op.drop_constraint(F(f"ck_{T}_{name}"), T, type_="check")
    op.create_check_constraint(F(f"ck_{T}_stage_known"), T, f"stage IN {stage_sql}")
    op.create_check_constraint(F(f"ck_{T}_state_known"), T, f"state IN {state_sql}")
    op.create_check_constraint(
        F(f"ck_{T}_ordinal_bounded"), T, f"ordinal BETWEEN 1 AND {max_ordinal}"
    )


def upgrade() -> None:
    _swap(NEW_STAGES, NEW_STATES, 5)
    op.add_column(
        "reconstruction_run", sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "reconstruction_run", sa.Column("invalidated_reason", sa.String(48), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("reconstruction_run", "invalidated_reason")
    op.drop_column("reconstruction_run", "invalidated_at")
    op.execute(f"DELETE FROM {T} WHERE stage = 'design'")  # noqa: S608
    op.execute(f"UPDATE {T} SET state = 'not_available', reason_code = 'stub_provider' WHERE state = 'stubbed'")  # noqa: S608
    _swap(OLD_STAGES, OLD_STATES, 4)

"""Visual page reads and generic non-PDF reads by the model step (TASK-115).

Revision ID: 0021_visual_read
Revises: 0020_chat

* ``document_identity_proposal.read_mode`` (``text`` | ``image``, default ``text``): an identity read
  from a page image cannot have its quote checked against a text layer; it is stored as an
  unverified proposal flagged ``image`` (status stays ``model_proposal``).
* ``document_model_result.read_mode`` (``text`` | ``image`` | ``mixed`` | ``binary_preview``): the
  per-document summary shown with the stored read (additive; defaults to ``text``).

Downgrade deletes image-origin identity proposals: without the column they would be
indistinguishable from quote-verified text proposals, which they are not.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_visual_read"
down_revision: str | None = "0020_chat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f


def upgrade() -> None:
    op.add_column(
        "document_identity_proposal",
        sa.Column("read_mode", sa.String(16), nullable=False, server_default=sa.text("'text'")),
    )
    op.create_check_constraint(
        F("ck_document_identity_proposal_read_mode_known"),
        "document_identity_proposal",
        "read_mode IN ('text', 'image')",
    )
    op.add_column(
        "document_model_result",
        sa.Column("read_mode", sa.String(16), nullable=False, server_default=sa.text("'text'")),
    )
    op.create_check_constraint(
        F("ck_document_model_result_read_mode_known"),
        "document_model_result",
        "read_mode IN ('text', 'image', 'mixed', 'binary_preview')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM document_identity_proposal WHERE read_mode = 'image'")
    op.drop_constraint(
        F("ck_document_model_result_read_mode_known"), "document_model_result", type_="check"
    )
    op.drop_column("document_model_result", "read_mode")
    op.drop_constraint(
        F("ck_document_identity_proposal_read_mode_known"),
        "document_identity_proposal",
        type_="check",
    )
    op.drop_column("document_identity_proposal", "read_mode")

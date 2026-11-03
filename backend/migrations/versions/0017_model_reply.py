"""Re-processable, observable model processing (TASK-072).

Revision ID: 0017_model_reply
Revises: 0016_document_identity

* ``document_model_result.raw_reply`` / ``raw_reply_truncated``: the provider's text as stored
  (at most 8 KiB, untrusted data) so the owner can see what the model answered.
* The cache key of ``document_model_result`` stops being unique: a forced re-read stores a NEW
  result row for the same (document, page window, prompt, schema); the latest by time is the
  current read and earlier rows stay as history. A non-forced run still reuses the latest row.
  ``ix_document_model_result_document`` (project, document, created_at DESC) serves the lookup.
* ``processing_run.force_refresh`` (the run bypasses the cache; part of the confirmed estimate's
  identity) and ``processing_run.model`` (the model that ran, for the history).

No new table: the project purge is unchanged.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_model_reply"
down_revision: str | None = "0016_document_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
CACHE_KEY = F("uq_document_model_result_cache_key")


def upgrade() -> None:
    op.add_column("document_model_result", sa.Column("raw_reply", sa.Text(), nullable=True))
    op.add_column(
        "document_model_result",
        sa.Column(
            "raw_reply_truncated", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
    op.create_check_constraint(
        F("ck_document_model_result_raw_reply_bounded"),
        "document_model_result",
        "raw_reply IS NULL OR octet_length(raw_reply) <= 8192",
    )
    op.drop_constraint(CACHE_KEY, "document_model_result", type_="unique")
    op.add_column(
        "processing_run",
        sa.Column("force_refresh", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("processing_run", sa.Column("model", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("processing_run", "model")
    op.drop_column("processing_run", "force_refresh")
    # keep only the latest result per old cache key (its proposals cascade with the deleted rows)
    op.execute(
        "DELETE FROM document_model_result d USING document_model_result n "
        "WHERE d.project_id = n.project_id AND d.document_id = n.document_id "
        "AND d.page_start = n.page_start AND d.page_end = n.page_end "
        "AND d.prompt_version = n.prompt_version AND d.schema_version = n.schema_version "
        "AND (d.created_at, d.result_id) < (n.created_at, n.result_id)"
    )
    op.create_unique_constraint(
        CACHE_KEY,
        "document_model_result",
        [
            "project_id",
            "document_id",
            "page_start",
            "page_end",
            "prompt_version",
            "schema_version",
        ],
    )
    op.drop_constraint(
        F("ck_document_model_result_raw_reply_bounded"), "document_model_result", type_="check"
    )
    op.drop_column("document_model_result", "raw_reply_truncated")
    op.drop_column("document_model_result", "raw_reply")

"""Storage root identity, failed storage state and failure attribution (TASK-070).

Revision ID: 0014_storage_root_identity
Revises: 0013_reconstruction_runs

``storage_root_identity`` is a single-row table holding the id of the storage root this database
belongs to (the same id lives in ``<root>/.fieldlens-root-id``). The persisted storage state
``quarantined`` is renamed ``failed`` (the user-visible vocabulary is ``stored | failed``) and the
reason (``missing`` / ``size_mismatch`` / ``hash_mismatch``) plus the writing process are stored.
Existing rows are converted, including stored job results and coverage reasons that carry the old
word, so no persisted JSON contradicts the new contract. Files that were falsely marked are healed
by the startup heal pass, which re-verifies their bytes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_storage_root_identity"
down_revision: str | None = "0013_reconstruction_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = sa.sql.elements.conv
TS = sa.DateTime(timezone=True)
_STATE = F("ck_document_processing_storage_state_known")
_REASON = F("ck_document_processing_storage_failure_reason_known")


def upgrade() -> None:
    op.create_table(
        "storage_root_identity",
        sa.Column("singleton", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("root_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("adopted_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("singleton", name=F("pk_storage_root_identity")),
        sa.CheckConstraint("singleton", name=F("ck_storage_root_identity_single_row")),
    )
    op.add_column(
        "document_processing", sa.Column("storage_failure_reason", sa.String(32), nullable=True)
    )
    op.add_column("document_processing", sa.Column("storage_failed_by", sa.Text(), nullable=True))
    op.drop_constraint(_STATE, "document_processing", type_="check")
    op.execute(
        """
        UPDATE document_processing
        SET storage_state = 'failed',
            storage_failure_reason = CASE detail
                WHEN 'verification_size_mismatch' THEN 'size_mismatch'
                WHEN 'verification_hash_mismatch' THEN 'hash_mismatch'
                WHEN 'verification_content_hash_mismatch' THEN 'hash_mismatch'
                ELSE 'missing' END
        WHERE storage_state = 'quarantined'
        """
    )
    op.create_check_constraint(
        _STATE,
        "document_processing",
        "storage_state IN ('pending_verification','stored','failed')",
    )
    op.create_check_constraint(
        _REASON,
        "document_processing",
        "storage_failure_reason IS NULL OR storage_failure_reason IN "
        "('missing','size_mismatch','hash_mismatch')",
    )
    # Persisted result/coverage/error JSON written by earlier versions.
    op.execute(
        """
        UPDATE ingest_job SET result = jsonb_build_object('failed', result -> 'quarantined')
            || (result - 'quarantined')
        WHERE result ? 'quarantined'
        """
    )
    op.execute(
        """
        UPDATE ingest_job SET error = replace(error::text, 'quarantined', 'failed')::jsonb
        WHERE error::text LIKE '%quarantined%'
        """
    )
    # Finalized revisions are immutable by trigger; this is a wording-only rewrite of coverage
    # reasons, so the guard is lifted for exactly this statement.
    op.execute("ALTER TABLE source_revision DISABLE TRIGGER tr_source_revision_guard")
    op.execute(
        """
        UPDATE source_revision SET coverage = replace(coverage::text, 'quarantined', 'failed')::jsonb
        WHERE coverage::text LIKE '%quarantined%'
        """
    )
    op.execute("ALTER TABLE source_revision ENABLE TRIGGER tr_source_revision_guard")


def downgrade() -> None:
    op.drop_constraint(_REASON, "document_processing", type_="check")
    op.drop_constraint(_STATE, "document_processing", type_="check")
    op.execute("UPDATE document_processing SET storage_state = 'quarantined' WHERE storage_state = 'failed'")
    op.create_check_constraint(
        _STATE,
        "document_processing",
        "storage_state IN ('pending_verification','stored','quarantined')",
    )
    op.drop_column("document_processing", "storage_failed_by")
    op.drop_column("document_processing", "storage_failure_reason")
    op.drop_table("storage_root_identity")

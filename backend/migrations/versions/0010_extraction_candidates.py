"""Model-proposed extraction candidates and the unit-to-reservation link (TASK-036).

Revision ID: 0010_extraction_candidates
Revises: 0009_series_storage

``extraction_candidate`` stores model proposals with their validator results. Original values stay
as written inside the typed ``attributes`` payload (``kind`` discriminator), so later categories
need no migration. CHECK constraints make AX-13 structural: a ``model_read`` row is never
``accepted`` and always ``unverified``. ``agent_work_unit.reservation_id`` links the activity-log
cost to its BudgetLedger reservation (AX-15).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_extraction_candidates"
down_revision: str | None = "0009_series_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.add_column("agent_work_unit", sa.Column("reservation_id", UUID, nullable=True))
    op.create_foreign_key(
        F("fk_agent_work_unit_reservation_id"),
        "agent_work_unit",
        "spend_reservation",
        ["reservation_id"],
        ["reservation_id"],
    )
    op.create_table(
        "extraction_candidate",
        sa.Column("candidate_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("unit_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("wellbore_id", UUID, nullable=True),
        sa.Column("candidate_key", sa.String(64), nullable=False),
        sa.Column("ordinal", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("subject", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column(
            "evidence_class",
            sa.String(24),
            server_default=sa.text("'model_proposal'"),
            nullable=False,
        ),
        sa.Column("validation_state", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("reason_codes", postgresql.ARRAY(sa.Text), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "validator_results", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("attributes", postgresql.JSONB, nullable=False),
        sa.Column("quote", sa.Text, nullable=True),
        sa.Column("locator", postgresql.JSONB, nullable=False),
        sa.Column("conflicts_with_record_id", UUID, nullable=True),
        sa.Column("model_id", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("harness_version", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("candidate_id", name=F("pk_extraction_candidate")),
        sa.ForeignKeyConstraint(
            ["project_id", "unit_id"],
            ["agent_work_unit.project_id", "agent_work_unit.unit_id"],
            name=F("fk_extraction_candidate_unit_scope"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_extraction_candidate_revision_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_extraction_candidate_document_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "wellbore_id"],
            ["wellbore.project_id", "wellbore.wellbore_id"],
            name=F("fk_extraction_candidate_wellbore_scope"),
        ),
        sa.UniqueConstraint("unit_id", "candidate_key", name=F("uq_extraction_candidate_unit_key")),
        sa.CheckConstraint(
            "state IN ('candidate', 'accepted', 'rejected', 'flagged')",
            name=F("ck_extraction_candidate_state_known"),
        ),
        sa.CheckConstraint(
            "method IN ('model_proposal', 'model_read')",
            name=F("ck_extraction_candidate_method_known"),
        ),
        sa.CheckConstraint(
            "evidence_class = 'model_proposal'",
            name=F("ck_extraction_candidate_evidence_class_model_proposal"),
        ),
        sa.CheckConstraint(
            "method <> 'model_read' OR (state <> 'accepted' AND validation_state = 'unverified')",
            name=F("ck_extraction_candidate_model_read_never_accepted"),
        ),
        sa.CheckConstraint(
            "state <> 'accepted' OR (method = 'model_proposal' AND validation_state = 'valid')",
            name=F("ck_extraction_candidate_accepted_requires_valid"),
        ),
        sa.CheckConstraint(
            "state NOT IN ('rejected', 'flagged') OR cardinality(reason_codes) >= 1",
            name=F("ck_extraction_candidate_decided_has_reason"),
        ),
        sa.CheckConstraint(
            "jsonb_typeof(attributes) = 'object' AND attributes ? 'kind' "
            "AND octet_length(attributes::text) <= 8192 "
            "AND jsonb_typeof(validator_results) = 'array' "
            "AND octet_length(validator_results::text) <= 8192",
            name=F("ck_extraction_candidate_payload_bounded"),
        ),
        sa.CheckConstraint(
            "quote IS NULL OR char_length(quote) <= 400",
            name=F("ck_extraction_candidate_quote_bounded"),
        ),
    )
    op.create_index(
        F("ix_extraction_candidate_document_state"),
        "extraction_candidate",
        [
            "project_id",
            "document_id",
            "state",
            sa.text("created_at DESC"),
            sa.text("candidate_id DESC"),
        ],
    )
    op.create_index(F("ix_extraction_candidate_unit"), "extraction_candidate", ["unit_id"])


def downgrade() -> None:
    op.drop_index(F("ix_extraction_candidate_unit"), table_name="extraction_candidate")
    op.drop_index(F("ix_extraction_candidate_document_state"), table_name="extraction_candidate")
    op.drop_table("extraction_candidate")
    op.drop_constraint(F("fk_agent_work_unit_reservation_id"), "agent_work_unit", type_="foreignkey")
    op.drop_column("agent_work_unit", "reservation_id")

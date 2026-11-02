"""Model-read document classification and wellbore identity proposals (TASK-055).

Revision ID: 0016_document_identity
Revises: 0015_project_deletion

``document_model_result`` is the cached, project-scoped outcome of the model step for one
document (category, tags, warnings, provenance); its unique cache key is (document, page window,
prompt version, schema version), so an unchanged input never reaches the provider twice.
``document_identity_proposal`` holds the wellbore/well identities the model read, each with page
and quote and the fixed status ``model_proposal``; nothing here is an accepted fact.
``processing_run_document.cache_hit`` reports a reused result; ``processing_run.provider`` also
admits ``meta`` (the live provider is still selected only by explicit configuration).

Both new tables carry ``project_id`` and are covered by the project purge (``PURGE_ORDER``).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_document_identity"
down_revision: str | None = "0015_project_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
USD = sa.Numeric(14, 6)
CATEGORIES = (
    "trajectory",
    "completion_equipment",
    "perforation_history",
    "production_injection",
    "well_logs",
    "geology_reservoir",
    "terrain_bathymetry",
    "general_report",
)
CATEGORY_SQL = ", ".join(f"'{c}'" for c in CATEGORIES)


def upgrade() -> None:
    op.drop_constraint(F("ck_processing_run_provider_known"), "processing_run", type_="check")
    op.create_check_constraint(
        F("ck_processing_run_provider_known"), "processing_run", "provider IN ('stub', 'meta')"
    )
    op.add_column(
        "processing_run_document",
        sa.Column("cache_hit", sa.Boolean, server_default=sa.text("false"), nullable=False),
    )

    op.create_table(
        "document_model_result",
        sa.Column("result_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("page_start", sa.Integer, nullable=False),
        sa.Column("page_end", sa.Integer, nullable=False),
        sa.Column("pages_read", sa.Integer, nullable=False),
        sa.Column("prompt_version", sa.String(48), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("model_revision", sa.String(64), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("unclassified", sa.Boolean, nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text), server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "warnings", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("input_tokens", sa.BigInteger, nullable=True),
        sa.Column("output_tokens", sa.BigInteger, nullable=True),
        sa.Column("cost_usd", USD, server_default=sa.text("0"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("result_id", name=F("pk_document_model_result")),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_document_model_result_document_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_document_model_result_revision_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["processing_run.project_id", "processing_run.run_id"],
            name=F("fk_document_model_result_run_scope"),
        ),
        sa.UniqueConstraint(
            "project_id", "result_id", name=F("uq_document_model_result_project_scope")
        ),
        sa.UniqueConstraint(
            "project_id",
            "document_id",
            "page_start",
            "page_end",
            "prompt_version",
            "schema_version",
            name=F("uq_document_model_result_cache_key"),
        ),
        sa.CheckConstraint(
            f"category IN ({CATEGORY_SQL})", name=F("ck_document_model_result_category_known")
        ),
        sa.CheckConstraint(
            "extraction_method = 'model_classification'",
            name=F("ck_document_model_result_method_known"),
        ),
        sa.CheckConstraint(
            "page_start >= 1 AND page_end >= page_start AND pages_read >= 0 "
            "AND pages_read <= page_end - page_start + 1 AND cardinality(tags) <= 5",
            name=F("ck_document_model_result_pages_and_tags_bounded"),
        ),
    )
    op.create_index(
        F("ix_document_model_result_document"),
        "document_model_result",
        ["project_id", "document_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "document_identity_proposal",
        sa.Column("proposal_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("result_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("subject_kind", sa.String(16), nullable=False),
        sa.Column("name_as_written", sa.Text, nullable=False),
        sa.Column("normalized_key", sa.Text, nullable=True),
        sa.Column("page", sa.Integer, nullable=False),
        sa.Column("quote", sa.Text, nullable=False),
        sa.Column(
            "status", sa.String(24), server_default=sa.text("'model_proposal'"), nullable=False
        ),
        sa.Column("extraction_method", sa.String(32), nullable=False),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("model_revision", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(48), nullable=False),
        sa.Column("schema_version", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("proposal_id", name=F("pk_document_identity_proposal")),
        sa.ForeignKeyConstraint(
            ["project_id", "result_id"],
            ["document_model_result.project_id", "document_model_result.result_id"],
            name=F("fk_document_identity_proposal_result_scope"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_document_identity_proposal_document_scope"),
        ),
        sa.UniqueConstraint(
            "result_id", "ordinal", name=F("uq_document_identity_proposal_ordinal")
        ),
        sa.CheckConstraint(
            "subject_kind IN ('well', 'wellbore')",
            name=F("ck_document_identity_proposal_subject_kind_known"),
        ),
        sa.CheckConstraint(
            "status = 'model_proposal'", name=F("ck_document_identity_proposal_status_unverified")
        ),
        sa.CheckConstraint(
            "extraction_method = 'model_classification'",
            name=F("ck_document_identity_proposal_method_known"),
        ),
        sa.CheckConstraint(
            "page >= 1 AND char_length(quote) >= 1 AND char_length(name_as_written) >= 1",
            name=F("ck_document_identity_proposal_evidence_present"),
        ),
    )
    op.create_index(
        F("ix_document_identity_proposal_document"),
        "document_identity_proposal",
        ["project_id", "document_id"],
    )


def downgrade() -> None:
    op.drop_table("document_identity_proposal")
    op.drop_table("document_model_result")
    op.drop_column("processing_run_document", "cache_hit")
    op.execute("DELETE FROM processing_run WHERE provider = 'meta'")  # cascades its documents
    op.drop_constraint(F("ck_processing_run_provider_known"), "processing_run", type_="check")
    op.create_check_constraint(
        F("ck_processing_run_provider_known"), "processing_run", "provider = 'stub'"
    )

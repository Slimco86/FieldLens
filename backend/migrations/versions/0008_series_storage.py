"""Series storage: full-resolution log samples and production series (TASK-047).

Revision ID: 0008_series_storage
Revises: 0007_source_retrieval

Derived, rebuildable data over ``extracted_record``/the original source. ``series_axis`` holds
the shared index (plus per-sample source line/row numbers) of one data block; ``series_curve``
holds one float64 value array per curve or production measure (NaN = missing sample). Arrays are
``bytea`` with ``STORAGE EXTERNAL`` so a window is a cheap ``substring``. Project scoping is
structural (composite foreign keys); rows cascade away with their extraction run, their document
or the extracted record they are anchored to, so an interrupted/superseded/removed source cannot
leave samples behind.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_series_storage"
down_revision: str | None = "0007_source_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
DOUBLE = postgresql.DOUBLE_PRECISION
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "series_axis",
        sa.Column("axis_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("index_type", sa.String(16), nullable=False),
        sa.Column("index_encoding", sa.String(16), nullable=False),
        sa.Column("index_name", sa.String(128), nullable=False),
        sa.Column("index_unit", sa.Text, nullable=True),
        sa.Column("index_unit_status", sa.String(16), nullable=False),
        sa.Column("index_order", sa.String(16), nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("index_first", DOUBLE, nullable=False),
        sa.Column("index_last", DOUBLE, nullable=False),
        sa.Column("index_min", DOUBLE, nullable=False),
        sa.Column("index_max", DOUBLE, nullable=False),
        sa.Column("position_kind", sa.String(8), nullable=False),
        sa.Column("well_name", sa.Text, nullable=True),
        sa.Column("wellbore_label", sa.Text, nullable=True),
        sa.Column("subject", postgresql.JSONB, nullable=False),
        sa.Column("evidence", postgresql.JSONB, nullable=False),
        sa.Column("index_data", sa.LargeBinary, nullable=False),
        sa.Column("positions_data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("axis_id", name=F("pk_series_axis")),
        sa.ForeignKeyConstraint(
            ["project_id", "run_id"],
            ["extraction_run.project_id", "extraction_run.run_id"],
            name=F("fk_series_axis_run_scope"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_series_axis_document_scope"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "project_id", "axis_id", "run_id", "document_id", name=F("uq_series_axis_scope")
        ),
        sa.UniqueConstraint("run_id", "ordinal", name=F("uq_series_axis_run_ordinal")),
        sa.CheckConstraint("kind IN ('log', 'production')", name=F("ck_series_axis_kind_known")),
        sa.CheckConstraint(
            "index_type IN ('depth', 'time', 'unknown')", name=F("ck_series_axis_index_type_known")
        ),
        sa.CheckConstraint(
            "index_encoding IN ('numeric', 'epoch_days')",
            name=F("ck_series_axis_index_encoding_known"),
        ),
        sa.CheckConstraint(
            "index_unit_status IN ('stated', 'missing')",
            name=F("ck_series_axis_index_unit_status_known"),
        ),
        sa.CheckConstraint(
            "index_order IN ('increasing', 'non_decreasing', 'decreasing', 'non_increasing', 'unordered')",
            name=F("ck_series_axis_index_order_known"),
        ),
        sa.CheckConstraint(
            "position_kind IN ('line', 'row')", name=F("ck_series_axis_position_kind_known")
        ),
        sa.CheckConstraint("sample_count > 0", name=F("ck_series_axis_has_samples")),
        sa.CheckConstraint("index_min <= index_max", name=F("ck_series_axis_index_range_ordered")),
        sa.CheckConstraint(
            "octet_length(index_data) = sample_count * 8", name=F("ck_series_axis_index_data_size")
        ),
        sa.CheckConstraint(
            "octet_length(positions_data) = sample_count * 4",
            name=F("ck_series_axis_positions_data_size"),
        ),
    )
    op.create_index(
        "ix_series_axis_project_document", "series_axis", ["project_id", "document_id"]
    )
    op.create_index(
        "ix_series_axis_project_wellbore", "series_axis", ["project_id", "wellbore_label"]
    )
    op.execute("ALTER TABLE series_axis ALTER COLUMN index_data SET STORAGE EXTERNAL")
    op.execute("ALTER TABLE series_axis ALTER COLUMN positions_data SET STORAGE EXTERNAL")

    op.create_table(
        "series_curve",
        sa.Column("series_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("axis_id", UUID, nullable=False),
        sa.Column("run_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("column_ordinal", sa.Integer, nullable=False),
        sa.Column("measure", sa.String(128), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("unit", sa.Text, nullable=True),
        sa.Column("unit_status", sa.String(16), nullable=False),
        sa.Column("sample_count", sa.Integer, nullable=False),
        sa.Column("valid_count", sa.Integer, nullable=False),
        sa.Column("null_count", sa.Integer, nullable=False),
        sa.Column("first_valid_index", DOUBLE, nullable=True),
        sa.Column("last_valid_index", DOUBLE, nullable=True),
        sa.Column("min_value", DOUBLE, nullable=True),
        sa.Column("max_value", DOUBLE, nullable=True),
        sa.Column("null_sentinel", DOUBLE, nullable=True),
        sa.Column("record_ordinal", sa.Integer, nullable=True),
        sa.Column("evidence", postgresql.JSONB, nullable=False),
        sa.Column("data_sha256", sa.String(64), nullable=False),
        sa.Column("values_data", sa.LargeBinary, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=NOW, nullable=False),
        sa.PrimaryKeyConstraint("series_id", name=F("pk_series_curve")),
        sa.ForeignKeyConstraint(
            ["project_id", "axis_id", "run_id", "document_id"],
            [
                "series_axis.project_id",
                "series_axis.axis_id",
                "series_axis.run_id",
                "series_axis.document_id",
            ],
            name=F("fk_series_curve_axis_scope"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id", "record_ordinal"],
            ["extracted_record.run_id", "extracted_record.ordinal"],
            name=F("fk_series_curve_record"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("axis_id", "column_ordinal", name=F("uq_series_curve_axis_column")),
        sa.CheckConstraint(
            "unit_status IN ('stated', 'missing', 'mixed')",
            name=F("ck_series_curve_unit_status_known"),
        ),
        sa.CheckConstraint(
            "valid_count >= 0 AND null_count >= 0 AND valid_count + null_count = sample_count",
            name=F("ck_series_curve_counts_consistent"),
        ),
        sa.CheckConstraint(
            "octet_length(values_data) = sample_count * 8",
            name=F("ck_series_curve_values_data_size"),
        ),
        sa.CheckConstraint(
            "(valid_count = 0) = (min_value IS NULL AND max_value IS NULL)",
            name=F("ck_series_curve_range_iff_valid"),
        ),
        sa.CheckConstraint(
            "min_value IS NULL OR min_value <= max_value", name=F("ck_series_curve_range_ordered")
        ),
        sa.CheckConstraint("data_sha256 ~ '^[0-9a-f]{64}$'", name=F("ck_series_curve_sha256")),
    )
    op.create_index("ix_series_curve_axis", "series_curve", ["axis_id"])
    op.create_index(
        "ix_series_curve_project_measure",
        "series_curve",
        ["project_id", sa.text("lower(measure)")],
    )
    op.create_index("ix_series_curve_run", "series_curve", ["run_id"])
    op.execute("ALTER TABLE series_curve ALTER COLUMN values_data SET STORAGE EXTERNAL")


def downgrade() -> None:
    op.drop_index("ix_series_curve_run", table_name="series_curve")
    op.drop_index("ix_series_curve_project_measure", table_name="series_curve")
    op.drop_index("ix_series_curve_axis", table_name="series_curve")
    op.drop_table("series_curve")
    op.drop_index("ix_series_axis_project_wellbore", table_name="series_axis")
    op.drop_index("ix_series_axis_project_document", table_name="series_axis")
    op.drop_table("series_axis")

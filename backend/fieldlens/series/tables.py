"""Series tables (migration 0008 is authoritative): derived, rebuildable sample storage.

``series_axis`` holds the shared index of one data block (a LAS data section or one
wellbore's production days) plus per-sample source positions; ``series_curve`` holds one value
array per curve/measure. Arrays are little-endian float64 ``bytea`` (NaN encodes a missing
sample; no source value can be NaN because the parsers reject it) with ``STORAGE EXTERNAL``,
so a window is a cheap ``substring`` and not a detoast of the whole array. Rows are
project-scoped through composite foreign keys and cascade away with their extraction run or
their document (the source-removal hook)."""

from __future__ import annotations

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION, JSONB, UUID

from fieldlens.persistence.models import metadata

series_axis = Table(
    "series_axis",
    metadata,
    Column(
        "axis_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("kind", String(16), nullable=False),
    Column("index_type", String(16), nullable=False),
    Column("index_encoding", String(16), nullable=False),
    Column("index_name", String(128), nullable=False),
    Column("index_unit", Text, nullable=True),
    Column("index_unit_status", String(16), nullable=False),
    Column("index_order", String(16), nullable=False),
    Column("sample_count", Integer, nullable=False),
    Column("index_first", DOUBLE_PRECISION, nullable=False),
    Column("index_last", DOUBLE_PRECISION, nullable=False),
    Column("index_min", DOUBLE_PRECISION, nullable=False),
    Column("index_max", DOUBLE_PRECISION, nullable=False),
    Column("position_kind", String(8), nullable=False),
    Column("well_name", Text, nullable=True),
    Column("wellbore_label", Text, nullable=True),
    Column("subject", JSONB, nullable=False),
    Column("evidence", JSONB, nullable=False),
    Column("index_data", LargeBinary, nullable=False),
    Column("positions_data", LargeBinary, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "run_id"],
        ["extraction_run.project_id", "extraction_run.run_id"],
        name="fk_series_axis_run_scope",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["project_id", "document_id"],
        ["source_document.project_id", "source_document.document_id"],
        name="fk_series_axis_document_scope",
        ondelete="CASCADE",
    ),
    UniqueConstraint("project_id", "axis_id", "run_id", "document_id", name="uq_series_axis_scope"),
    UniqueConstraint("run_id", "ordinal", name="uq_series_axis_run_ordinal"),
    CheckConstraint("kind IN ('log', 'production')", name="kind_known"),
    CheckConstraint("index_type IN ('depth', 'time', 'unknown')", name="index_type_known"),
    CheckConstraint("index_encoding IN ('numeric', 'epoch_days')", name="index_encoding_known"),
    CheckConstraint("index_unit_status IN ('stated', 'missing')", name="index_unit_status_known"),
    CheckConstraint(
        "index_order IN ('increasing', 'non_decreasing', 'decreasing', 'non_increasing', 'unordered')",
        name="index_order_known",
    ),
    CheckConstraint("position_kind IN ('line', 'row')", name="position_kind_known"),
    CheckConstraint("index_min <= index_max", name="index_range_ordered"),
    CheckConstraint("sample_count > 0", name="has_samples"),
    CheckConstraint("octet_length(index_data) = sample_count * 8", name="index_data_size"),
    CheckConstraint("octet_length(positions_data) = sample_count * 4", name="positions_data_size"),
    Index("ix_series_axis_project_document", "project_id", "document_id"),
    Index("ix_series_axis_project_wellbore", "project_id", "wellbore_label"),
)

series_curve = Table(
    "series_curve",
    metadata,
    Column(
        "series_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("axis_id", UUID(as_uuid=True), nullable=False),
    Column("run_id", UUID(as_uuid=True), nullable=False),
    Column("document_id", UUID(as_uuid=True), nullable=False),
    Column("column_ordinal", Integer, nullable=False),
    Column("measure", String(128), nullable=False),
    Column("description", Text, nullable=True),
    Column("unit", Text, nullable=True),
    Column("unit_status", String(16), nullable=False),
    Column("sample_count", Integer, nullable=False),
    Column("valid_count", Integer, nullable=False),
    Column("null_count", Integer, nullable=False),
    Column("first_valid_index", DOUBLE_PRECISION, nullable=True),
    Column("last_valid_index", DOUBLE_PRECISION, nullable=True),
    Column("min_value", DOUBLE_PRECISION, nullable=True),
    Column("max_value", DOUBLE_PRECISION, nullable=True),
    Column("null_sentinel", DOUBLE_PRECISION, nullable=True),
    Column("record_ordinal", Integer, nullable=True),
    Column("evidence", JSONB, nullable=False),
    Column("data_sha256", String(64), nullable=False),
    Column("values_data", LargeBinary, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "axis_id", "run_id", "document_id"],
        [
            "series_axis.project_id",
            "series_axis.axis_id",
            "series_axis.run_id",
            "series_axis.document_id",
        ],
        name="fk_series_curve_axis_scope",
        ondelete="CASCADE",
    ),
    ForeignKeyConstraint(
        ["run_id", "record_ordinal"],
        ["extracted_record.run_id", "extracted_record.ordinal"],
        name="fk_series_curve_record",
        ondelete="CASCADE",
    ),
    UniqueConstraint("axis_id", "column_ordinal", name="uq_series_curve_axis_column"),
    CheckConstraint("unit_status IN ('stated', 'missing', 'mixed')", name="unit_status_known"),
    CheckConstraint(
        "valid_count >= 0 AND null_count >= 0 AND valid_count + null_count = sample_count",
        name="counts_consistent",
    ),
    CheckConstraint("octet_length(values_data) = sample_count * 8", name="values_data_size"),
    CheckConstraint(
        "(valid_count = 0) = (min_value IS NULL AND max_value IS NULL)", name="range_iff_valid"
    ),
    CheckConstraint("min_value IS NULL OR min_value <= max_value", name="range_ordered"),
    CheckConstraint("data_sha256 ~ '^[0-9a-f]{64}$'", name="sha256"),
    Index("ix_series_curve_axis", "axis_id"),
    Index("ix_series_curve_project_measure", "project_id", text("lower(measure)")),
    Index("ix_series_curve_run", "run_id"),
)

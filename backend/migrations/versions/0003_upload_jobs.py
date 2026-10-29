"""Upload batches, immutable source documents/revisions, classification and persistent jobs.

Revision ID: 0003_upload_jobs
Revises: 0002_project_lifecycle

Adds project-scoped hash uniqueness, replacement links, document processing/classification
tables with an append-only audit, import batches (idempotency), persistent jobs/attempts with
fencing tokens, a one-staging-revision-per-project index, a single-running-attempt index and
triggers that make documents and finalized source revisions immutable.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_upload_jobs"
down_revision: str | None = "0002_project_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
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
JOB_STATUS_SQL = ", ".join(
    f"'{c}'"
    for c in ("queued", "running", "succeeded", "partial", "failed", "cancelled", "interrupted")
)


def _ts(name: str, *, nullable: bool = False, default: bool = True) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=nullable,
        server_default=NOW if default else None,
    )


def upgrade() -> None:
    op.add_column(
        "source_document",
        sa.Column("format_family", sa.String(32), nullable=False, server_default="unknown"),
    )
    op.create_unique_constraint(
        F("uq_source_document_project_sha256"), "source_document", ["project_id", "sha256"]
    )
    op.add_column(
        "source_revision_document", sa.Column("replaces_document_id", UUID, nullable=True)
    )
    op.create_foreign_key(
        F("fk_srd_replaces_scope"),
        "source_revision_document",
        "source_document",
        ["project_id", "replaces_document_id"],
        ["project_id", "document_id"],
    )
    op.create_check_constraint(
        F("ck_source_revision_document_srd_not_self_replace"),
        "source_revision_document",
        "replaces_document_id IS DISTINCT FROM document_id",
    )
    op.create_index(
        F("uq_source_revision_one_staging_per_project"),
        "source_revision",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status = 'staging'"),
    )

    op.create_table(
        "document_processing",
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("storage_state", sa.String(32), nullable=False),
        sa.Column("extraction_state", sa.String(32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("document_id", name=F("pk_document_processing")),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_document_processing_document_scope"),
        ),
        sa.CheckConstraint(
            "storage_state IN ('pending_verification','stored','quarantined')",
            name=F("ck_document_processing_storage_state_known"),
        ),
        sa.CheckConstraint(
            "extraction_state IN ('pending_extraction','unsupported')",
            name=F("ck_document_processing_extraction_state_known"),
        ),
    )

    op.create_table(
        "document_classification",
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column(
            "user_categories", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"
        ),
        sa.Column(
            "suggested_categories",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("categories_origin", sa.String(32), nullable=False),
        sa.Column("classification_method", sa.String(64), nullable=False),
        sa.Column("classification_version", sa.String(32), nullable=False),
        sa.Column("metadata_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _ts("updated_at"),
        sa.PrimaryKeyConstraint("document_id", name=F("pk_document_classification")),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_document_classification_document_scope"),
        ),
        sa.CheckConstraint(
            f"user_categories <@ ARRAY[{CATEGORY_SQL}]::text[] "
            f"AND suggested_categories <@ ARRAY[{CATEGORY_SQL}]::text[]",
            name=F("ck_document_classification_categories_known"),
        ),
        sa.CheckConstraint(
            "cardinality(tags) <= 20", name=F("ck_document_classification_tags_max")
        ),
        sa.CheckConstraint(
            "categories_origin IN ('none','upload_hint','user_override')",
            name=F("ck_document_classification_origin_known"),
        ),
        sa.CheckConstraint(
            "metadata_version >= 1", name=F("ck_document_classification_version_positive")
        ),
    )

    op.create_table(
        "document_classification_event",
        sa.Column("event_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("metadata_version", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(32), nullable=False),
        sa.Column("categories", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("event_id", name=F("pk_document_classification_event")),
        sa.ForeignKeyConstraint(
            ["project_id", "document_id"],
            ["source_document.project_id", "source_document.document_id"],
            name=F("fk_document_classification_event_document_scope"),
        ),
        sa.UniqueConstraint(
            "document_id", "metadata_version", name=F("uq_document_classification_event_version")
        ),
        sa.CheckConstraint(
            "origin IN ('upload_hint','user_override','none')",
            name=F("ck_document_classification_event_origin_known"),
        ),
    )

    op.create_table(
        "ingest_job",
        sa.Column("job_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("stage", sa.String(32), nullable=True),
        sa.Column("progress_processed", sa.Integer(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=True),
        sa.Column("progress_unit", sa.String(16), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.Column("fence_counter", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("2")),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("finished_at", nullable=True, default=False),
        sa.PrimaryKeyConstraint("job_id", name=F("pk_ingest_job")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.project_id"], name=F("fk_ingest_job_project_id")
        ),
        sa.UniqueConstraint("project_id", "job_id", name=F("uq_ingest_job_project_scope")),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_ingest_job_revision_scope"),
        ),
        sa.CheckConstraint("kind IN ('storage_verification')", name=F("ck_ingest_job_kind_known")),
        sa.CheckConstraint(
            f"status IN ({JOB_STATUS_SQL})", name=F("ck_ingest_job_status_known")
        ),
        sa.CheckConstraint(
            "attempt_count <= max_attempts", name=F("ck_ingest_job_attempts_bounded")
        ),
    )
    op.create_index(
        F("ix_ingest_job_status_created_at"), "ingest_job", ["status", "created_at"]
    )

    op.create_table(
        "ingest_job_attempt",
        sa.Column("attempt_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("job_id", UUID, nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("stage", sa.String(32), nullable=True),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("lease_owner", sa.Text(), nullable=False),
        _ts("lease_expires_at", default=False),
        _ts("heartbeat_at", default=False),
        _ts("started_at"),
        _ts("ended_at", nullable=True, default=False),
        sa.Column("error", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("attempt_id", name=F("pk_ingest_job_attempt")),
        sa.ForeignKeyConstraint(
            ["project_id", "job_id"],
            ["ingest_job.project_id", "ingest_job.job_id"],
            name=F("fk_ingest_job_attempt_job_scope"),
        ),
        sa.UniqueConstraint("job_id", "attempt_no", name=F("uq_ingest_job_attempt_no")),
        sa.UniqueConstraint("job_id", "fencing_token", name=F("uq_ingest_job_attempt_fence")),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','interrupted','cancelled')",
            name=F("ck_ingest_job_attempt_status_known"),
        ),
    )
    op.create_index(
        F("uq_ingest_job_attempt_single_running"),
        "ingest_job_attempt",
        [sa.text("(true)")],
        unique=True,
        postgresql_where=sa.text("status = 'running'"),
    )

    op.create_table(
        "import_batch",
        sa.Column("batch_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("source_revision_id", UUID, nullable=False),
        sa.Column("job_id", UUID, nullable=True),
        sa.Column("deduplicated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("document_ids", postgresql.ARRAY(UUID), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("batch_id", name=F("pk_import_batch")),
        sa.ForeignKeyConstraint(
            ["project_id", "source_revision_id"],
            ["source_revision.project_id", "source_revision.source_revision_id"],
            name=F("fk_import_batch_revision_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "job_id"],
            ["ingest_job.project_id", "ingest_job.job_id"],
            name=F("fk_import_batch_job_scope"),
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'", name=F("ck_import_batch_fingerprint_sha256")
        ),
    )
    op.create_index(
        F("uq_import_batch_project_idempotency_key"),
        "import_batch",
        ["project_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # Immutability: documents never change; a source revision is mutable only while staging;
    # membership may be inserted only into a staging revision and is never updated/deleted.
    op.execute(
        """
        CREATE FUNCTION fl_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable (% refused)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION fl_source_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'source_revision is immutable (DELETE refused)'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF OLD.status <> 'staging' THEN
                RAISE EXCEPTION 'finalized source_revision is immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            IF NEW.project_id <> OLD.project_id
               OR NEW.parent_source_revision_id IS DISTINCT FROM OLD.parent_source_revision_id
               OR NEW.manifest_hash <> OLD.manifest_hash
               OR NEW.source_revision_id <> OLD.source_revision_id THEN
                RAISE EXCEPTION 'source_revision identity and membership are immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION fl_membership_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE current_status text;
        BEGIN
            IF TG_OP <> 'INSERT' THEN
                RAISE EXCEPTION 'source_revision_document is immutable (% refused)', TG_OP
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            SELECT status INTO current_status FROM source_revision
                WHERE source_revision_id = NEW.source_revision_id;
            IF current_status IS DISTINCT FROM 'staging' THEN
                RAISE EXCEPTION 'membership of a finalized source revision is immutable'
                    USING ERRCODE = 'integrity_constraint_violation';
            END IF;
            RETURN NEW;
        END $$
        """
    )
    op.execute(
        "CREATE TRIGGER tr_source_document_immutable BEFORE UPDATE OR DELETE ON source_document "
        "FOR EACH ROW EXECUTE FUNCTION fl_forbid_change()"
    )
    op.execute(
        "CREATE TRIGGER tr_source_revision_guard BEFORE UPDATE OR DELETE ON source_revision "
        "FOR EACH ROW EXECUTE FUNCTION fl_source_revision_guard()"
    )
    op.execute(
        "CREATE TRIGGER tr_membership_guard BEFORE INSERT OR UPDATE OR DELETE "
        "ON source_revision_document FOR EACH ROW EXECUTE FUNCTION fl_membership_guard()"
    )
    op.execute(
        "CREATE TRIGGER tr_classification_event_append_only "
        "BEFORE UPDATE OR DELETE ON document_classification_event "
        "FOR EACH ROW EXECUTE FUNCTION fl_forbid_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER tr_classification_event_append_only ON document_classification_event")
    op.execute("DROP TRIGGER tr_membership_guard ON source_revision_document")
    op.execute("DROP TRIGGER tr_source_revision_guard ON source_revision")
    op.execute("DROP TRIGGER tr_source_document_immutable ON source_document")
    op.execute("DROP FUNCTION fl_membership_guard()")
    op.execute("DROP FUNCTION fl_source_revision_guard()")
    op.execute("DROP FUNCTION fl_forbid_change()")
    op.drop_index(F("uq_import_batch_project_idempotency_key"), table_name="import_batch")
    op.drop_table("import_batch")
    op.drop_index(F("uq_ingest_job_attempt_single_running"), table_name="ingest_job_attempt")
    op.drop_table("ingest_job_attempt")
    op.drop_index(F("ix_ingest_job_status_created_at"), table_name="ingest_job")
    op.drop_table("ingest_job")
    op.drop_table("document_classification_event")
    op.drop_table("document_classification")
    op.drop_table("document_processing")
    op.drop_index(F("uq_source_revision_one_staging_per_project"), table_name="source_revision")
    op.drop_constraint(
        F("ck_source_revision_document_srd_not_self_replace"),
        "source_revision_document",
        type_="check",
    )
    op.drop_constraint(F("fk_srd_replaces_scope"), "source_revision_document", type_="foreignkey")
    op.drop_column("source_revision_document", "replaces_document_id")
    op.drop_constraint(F("uq_source_document_project_sha256"), "source_document", type_="unique")
    op.drop_column("source_document", "format_family")

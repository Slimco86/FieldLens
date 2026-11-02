"""Project deletion state and the designed purge path through the immutability guards (TASK-071).

Revision ID: 0015_project_deletion
Revises: 0013_reconstruction_runs

``project.deletion_state`` is ``none`` | ``deleting`` | ``failed``. ``deletion_storage_purged_at``
records that the project's files are gone, so a resumed deletion never has to re-verify a storage
root that no longer holds the originals.

The four immutability guards (``source_document``, ``source_revision``,
``source_revision_document``, ``document_classification_event``) stay enabled for every other
path. A DELETE is allowed only when the row's project equals the transaction-local setting
``fieldlens.purge_project_id`` (``SET LOCAL`` by the purge executor), so a purge of project A can
never delete a row of project B and no session can delete without setting it first.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_project_deletion"
down_revision: str | None = "0013_reconstruction_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f

_PURGING = "OLD.project_id::text = NULLIF(current_setting('fieldlens.purge_project_id', true), '')"


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column("deletion_state", sa.String(16), server_default=sa.text("'none'"), nullable=False),
    )
    op.add_column(
        "project", sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("project", sa.Column("deletion_error", sa.Text(), nullable=True))
    op.add_column(
        "project", sa.Column("deletion_storage_purged_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        F("ck_project_deletion_state_known"),
        "project",
        "deletion_state IN ('none', 'deleting', 'failed')",
    )
    op.create_check_constraint(
        F("ck_project_deletion_state_consistent"),
        "project",
        "(deletion_state = 'none') = (deletion_requested_at IS NULL) "
        "AND (deletion_state <> 'none' OR (deletion_error IS NULL "
        "AND deletion_storage_purged_at IS NULL))",
    )

    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION fl_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' AND {_PURGING} THEN
                RETURN OLD;
            END IF;
            RAISE EXCEPTION '% is immutable (% refused)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END $$
        """
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION fl_source_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                IF {_PURGING} THEN
                    RETURN OLD;
                END IF;
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
        f"""
        CREATE OR REPLACE FUNCTION fl_membership_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE current_status text;
        BEGIN
            IF TG_OP = 'DELETE' AND {_PURGING} THEN
                RETURN OLD;
            END IF;
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


def downgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fl_forbid_change() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION '% is immutable (% refused)', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'integrity_constraint_violation';
        END $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fl_source_revision_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
        CREATE OR REPLACE FUNCTION fl_membership_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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
    op.drop_constraint(F("ck_project_deletion_state_consistent"), "project", type_="check")
    op.drop_constraint(F("ck_project_deletion_state_known"), "project", type_="check")
    op.drop_column("project", "deletion_storage_purged_at")
    op.drop_column("project", "deletion_error")
    op.drop_column("project", "deletion_requested_at")
    op.drop_column("project", "deletion_state")

"""Provider budget: periods, pricing revisions, spend reservations and provider attempts.

Revision ID: 0004_provider_budget
Revises: 0003_upload_jobs

Self-contained (no foreign keys into project tables). The ledger cap is capped at USD 150 by a
check constraint; ``committed_usd`` on a reservation is the liability summed by the ceiling check.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_provider_budget"
down_revision: str | None = "0003_upload_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
GEN_UUID = sa.text("gen_random_uuid()")
NOW = sa.text("now()")
USD = sa.Numeric(14, 6)
STATES = ", ".join(f"'{s}'" for s in ("reserved", "settled", "released", "liable"))
STATUSES = ", ".join(
    f"'{s}'"
    for s in ("dispatched", "completed", "refused", "truncated", "failed", "timeout", "unknown")
)


def _ts(name: str, *, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=nullable, server_default=None if nullable else NOW
    )


def upgrade() -> None:
    op.create_table(
        "budget_period",
        sa.Column("period_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'USD'"), nullable=False),
        sa.Column("ledger_cap_usd", USD, nullable=False),
        sa.Column("warn_usd", USD, nullable=False),
        sa.Column("unattended_block_usd", USD, nullable=False),
        sa.Column("starting_balance_usd", USD, nullable=True),
        sa.Column("balance_source", sa.Text, nullable=True),
        _ts("balance_confirmed_at", nullable=True),
        sa.Column("paused", sa.Boolean, server_default=sa.text("false"), nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("period_id", name=F("pk_budget_period")),
        sa.UniqueConstraint("name", name=F("uq_budget_period_name")),
        sa.CheckConstraint("currency = 'USD'", name=F("ck_budget_period_currency_usd")),
        sa.CheckConstraint(
            "ledger_cap_usd > 0 AND ledger_cap_usd <= 150", name=F("ck_budget_period_cap_range")
        ),
        sa.CheckConstraint(
            "warn_usd > 0 AND warn_usd <= unattended_block_usd "
            "AND unattended_block_usd <= ledger_cap_usd",
            name=F("ck_budget_period_thresholds_ordered"),
        ),
        sa.CheckConstraint(
            "starting_balance_usd IS NULL OR starting_balance_usd >= 0",
            name=F("ck_budget_period_balance_nonneg"),
        ),
        sa.CheckConstraint(
            "(starting_balance_usd IS NULL) = (balance_confirmed_at IS NULL)",
            name=F("ck_budget_period_balance_confirmed"),
        ),
    )
    op.create_table(
        "pricing_revision",
        sa.Column("pricing_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("revision", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("input_usd_per_mtok", USD, nullable=False),
        sa.Column("cached_input_usd_per_mtok", USD, nullable=True),
        sa.Column("output_usd_per_mtok", USD, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        _ts("created_at"),
        sa.PrimaryKeyConstraint("pricing_id", name=F("pk_pricing_revision")),
        sa.UniqueConstraint("revision", name=F("uq_pricing_revision_revision")),
        sa.CheckConstraint(
            "input_usd_per_mtok >= 0 AND output_usd_per_mtok >= 0 "
            "AND (cached_input_usd_per_mtok IS NULL OR cached_input_usd_per_mtok >= 0)",
            name=F("ck_pricing_revision_rates_nonneg"),
        ),
    )
    op.create_table(
        "spend_reservation",
        sa.Column("reservation_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("period_id", UUID, nullable=False),
        sa.Column("pricing_id", UUID, nullable=False),
        sa.Column("request_key", sa.String(200), nullable=False),
        sa.Column("work_unit", sa.String(120), nullable=False),
        sa.Column("state", sa.String(16), server_default=sa.text("'reserved'"), nullable=False),
        sa.Column("reserved_usd", USD, nullable=False),
        sa.Column("committed_usd", USD, nullable=False),
        sa.Column("attempts_dispatched", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column("tool_calls_used", sa.Integer, server_default=sa.text("0"), nullable=False),
        sa.Column(
            "reconciliation_status",
            sa.String(16),
            server_default=sa.text("'not_needed'"),
            nullable=False,
        ),
        sa.Column("overrun", sa.Boolean, server_default=sa.text("false"), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        _ts("closed_at", nullable=True),
        sa.PrimaryKeyConstraint("reservation_id", name=F("pk_spend_reservation")),
        sa.ForeignKeyConstraint(
            ["period_id"], ["budget_period.period_id"], name=F("fk_spend_reservation_period_id")
        ),
        sa.ForeignKeyConstraint(
            ["pricing_id"], ["pricing_revision.pricing_id"], name=F("fk_spend_reservation_pricing_id")
        ),
        sa.UniqueConstraint("period_id", "request_key", name=F("uq_spend_reservation_request")),
        sa.CheckConstraint(f"state IN ({STATES})", name=F("ck_spend_reservation_state_known")),
        sa.CheckConstraint(
            "reserved_usd > 0 AND committed_usd >= 0", name=F("ck_spend_reservation_amounts")
        ),
        sa.CheckConstraint(
            "state <> 'reserved' OR committed_usd = reserved_usd",
            name=F("ck_spend_reservation_open_commits_reserved"),
        ),
        sa.CheckConstraint(
            "state <> 'released' OR (committed_usd = 0 AND attempts_dispatched = 0)",
            name=F("ck_spend_reservation_released_unused"),
        ),
        sa.CheckConstraint(
            "attempts_dispatched >= 0 AND tool_calls_used >= 0",
            name=F("ck_spend_reservation_counters_nonneg"),
        ),
        sa.CheckConstraint(
            "reconciliation_status IN ('not_needed', 'pending', 'reconciled')",
            name=F("ck_spend_reservation_reconciliation_known"),
        ),
        sa.CheckConstraint(
            "(state = 'liable') = (reconciliation_status = 'pending')",
            name=F("ck_spend_reservation_liable_pending"),
        ),
    )
    op.create_index(
        F("ix_spend_reservation_period_state"), "spend_reservation", ["period_id", "state"]
    )
    op.create_table(
        "provider_attempt",
        sa.Column("attempt_id", UUID, server_default=GEN_UUID, nullable=False),
        sa.Column("reservation_id", UUID, nullable=False),
        sa.Column("attempt_no", sa.Integer, nullable=False),
        sa.Column("retry_of_attempt_no", sa.Integer, nullable=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), server_default=sa.text("'dispatched'"), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("provider_request_id", sa.String(128), nullable=True),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("cached_input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("web_search_queries", sa.Integer, nullable=True),
        sa.Column("elapsed_ms", sa.Integer, nullable=True),
        sa.Column("estimated_usd", USD, nullable=False),
        sa.Column("billed_usd", USD, nullable=True),
        sa.Column("reconciled", sa.Boolean, server_default=sa.text("false"), nullable=False),
        _ts("started_at"),
        _ts("finished_at", nullable=True),
        sa.PrimaryKeyConstraint("attempt_id", name=F("pk_provider_attempt")),
        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["spend_reservation.reservation_id"],
            name=F("fk_provider_attempt_reservation_id"),
        ),
        sa.UniqueConstraint("reservation_id", "attempt_no", name=F("uq_provider_attempt_no")),
        sa.CheckConstraint(f"status IN ({STATUSES})", name=F("ck_provider_attempt_status_known")),
        sa.CheckConstraint(
            "attempt_no >= 1 AND (retry_of_attempt_no IS NULL OR retry_of_attempt_no < attempt_no)",
            name=F("ck_provider_attempt_numbering"),
        ),
        sa.CheckConstraint(
            "estimated_usd >= 0 AND (billed_usd IS NULL OR billed_usd >= 0)",
            name=F("ck_provider_attempt_amounts_nonneg"),
        ),
    )


def downgrade() -> None:
    op.drop_table("provider_attempt")
    op.drop_index(F("ix_spend_reservation_period_state"), table_name="spend_reservation")
    op.drop_table("spend_reservation")
    op.drop_table("pricing_revision")
    op.drop_table("budget_period")

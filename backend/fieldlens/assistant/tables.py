"""Budget, pricing, reservation and provider-attempt tables (migration 0004 is authoritative).

Registered on the shared metadata so model/migration drift is caught by the foundation test.
Amounts are ``NUMERIC(14,6)`` USD. ``committed_usd`` is the liability the ceiling check sums:
the reserved amount while open, the billed/estimated amount once closed, 0 when released.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID

from fieldlens.persistence.models import metadata

USD = Numeric(14, 6)
RESERVATION_STATES = ("reserved", "settled", "released", "liable")
ATTEMPT_STATUSES = (
    "dispatched",
    "completed",
    "refused",
    "truncated",
    "failed",
    "timeout",
    "unknown",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _ts(name: str, *, nullable: bool = False) -> Column:  # type: ignore[type-arg]
    return Column(
        name,
        DateTime(timezone=True),
        nullable=nullable,
        server_default=None if nullable else text("now()"),
    )


budget_period = Table(
    "budget_period",
    metadata,
    Column(
        "period_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("name", String(64), nullable=False),
    Column("currency", String(3), nullable=False, server_default=text("'USD'")),
    Column("ledger_cap_usd", USD, nullable=False),
    Column("warn_usd", USD, nullable=False),
    Column("unattended_block_usd", USD, nullable=False),
    Column("starting_balance_usd", USD, nullable=True),
    Column("balance_source", Text, nullable=True),
    _ts("balance_confirmed_at", nullable=True),
    Column("paused", Boolean, nullable=False, server_default=text("false")),
    _ts("created_at"),
    UniqueConstraint("name", name="uq_budget_period_name"),
    CheckConstraint("currency = 'USD'", name="currency_usd"),
    CheckConstraint("ledger_cap_usd > 0 AND ledger_cap_usd <= 150", name="cap_range"),
    CheckConstraint(
        "warn_usd > 0 AND warn_usd <= unattended_block_usd AND unattended_block_usd <= ledger_cap_usd",
        name="thresholds_ordered",
    ),
    CheckConstraint(
        "starting_balance_usd IS NULL OR starting_balance_usd >= 0", name="balance_nonneg"
    ),
    CheckConstraint(
        "(starting_balance_usd IS NULL) = (balance_confirmed_at IS NULL)", name="balance_confirmed"
    ),
)

pricing_revision = Table(
    "pricing_revision",
    metadata,
    Column(
        "pricing_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("revision", String(64), nullable=False),
    Column("model", String(128), nullable=False),
    Column("input_usd_per_mtok", USD, nullable=False),
    Column("cached_input_usd_per_mtok", USD, nullable=True),
    Column("output_usd_per_mtok", USD, nullable=False),
    Column("source", Text, nullable=False),
    _ts("created_at"),
    UniqueConstraint("revision", name="uq_pricing_revision_revision"),
    CheckConstraint(
        "input_usd_per_mtok >= 0 AND output_usd_per_mtok >= 0 "
        "AND (cached_input_usd_per_mtok IS NULL OR cached_input_usd_per_mtok >= 0)",
        name="rates_nonneg",
    ),
)

spend_reservation = Table(
    "spend_reservation",
    metadata,
    Column(
        "reservation_id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("period_id", UUID(as_uuid=True), ForeignKey("budget_period.period_id"), nullable=False),
    Column(
        "pricing_id", UUID(as_uuid=True), ForeignKey("pricing_revision.pricing_id"), nullable=False
    ),
    Column("request_key", String(200), nullable=False),
    Column("work_unit", String(120), nullable=False),
    Column("state", String(16), nullable=False, server_default=text("'reserved'")),
    Column("reserved_usd", USD, nullable=False),
    Column("committed_usd", USD, nullable=False),
    Column("attempts_dispatched", Integer, nullable=False, server_default=text("0")),
    Column("tool_calls_used", Integer, nullable=False, server_default=text("0")),
    Column(
        "reconciliation_status", String(16), nullable=False, server_default=text("'not_needed'")
    ),
    _ts("created_at"),
    _ts("updated_at"),
    _ts("closed_at", nullable=True),
    UniqueConstraint("period_id", "request_key", name="uq_spend_reservation_request"),
    CheckConstraint(_in("state", RESERVATION_STATES), name="state_known"),
    CheckConstraint("reserved_usd > 0 AND committed_usd >= 0", name="amounts"),
    CheckConstraint(
        "state <> 'reserved' OR committed_usd = reserved_usd", name="open_commits_reserved"
    ),
    CheckConstraint(
        "state <> 'released' OR (committed_usd = 0 AND attempts_dispatched = 0)",
        name="released_unused",
    ),
    CheckConstraint("attempts_dispatched >= 0 AND tool_calls_used >= 0", name="counters_nonneg"),
    CheckConstraint(
        "reconciliation_status IN ('not_needed', 'pending', 'reconciled')",
        name="reconciliation_known",
    ),
    CheckConstraint(
        "(state = 'liable') = (reconciliation_status = 'pending')", name="liable_pending"
    ),
)
Index("ix_spend_reservation_period_state", spend_reservation.c.period_id, spend_reservation.c.state)

provider_attempt = Table(
    "provider_attempt",
    metadata,
    Column(
        "attempt_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column(
        "reservation_id",
        UUID(as_uuid=True),
        ForeignKey("spend_reservation.reservation_id"),
        nullable=False,
    ),
    Column("attempt_no", Integer, nullable=False),
    Column("retry_of_attempt_no", Integer, nullable=True),
    Column("provider", String(32), nullable=False),
    Column("model", String(128), nullable=False),
    Column("status", String(16), nullable=False, server_default=text("'dispatched'")),
    Column("error_code", String(64), nullable=True),
    Column("provider_request_id", String(128), nullable=True),
    Column("input_tokens", Integer, nullable=True),
    Column("cached_input_tokens", Integer, nullable=True),
    Column("output_tokens", Integer, nullable=True),
    Column("web_search_queries", Integer, nullable=True),
    Column("elapsed_ms", Integer, nullable=True),
    Column("estimated_usd", USD, nullable=False),
    Column("billed_usd", USD, nullable=True),
    Column("reconciled", Boolean, nullable=False, server_default=text("false")),
    _ts("started_at"),
    _ts("finished_at", nullable=True),
    UniqueConstraint("reservation_id", "attempt_no", name="uq_provider_attempt_no"),
    CheckConstraint(_in("status", ATTEMPT_STATUSES), name="status_known"),
    CheckConstraint(
        "attempt_no >= 1 AND (retry_of_attempt_no IS NULL OR retry_of_attempt_no < attempt_no)",
        name="numbering",
    ),
    CheckConstraint(
        "estimated_usd >= 0 AND (billed_usd IS NULL OR billed_usd >= 0)", name="amounts_nonneg"
    ),
)

__all__ = ["budget_period", "pricing_revision", "provider_attempt", "spend_reservation"]

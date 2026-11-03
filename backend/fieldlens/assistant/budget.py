"""PostgreSQL budget ledger: reserve -> attempt records -> settle / release / reconcile.

Every mutation is one transaction. ``reserve`` locks the budget period row, so concurrent
reservations serialize and can never push the committed total above the effective cap
(``min(ledger cap, confirmed starting balance)``). Reservation-scoped changes lock the
reservation row. Idempotency: a repeated ``request_key`` returns the original reservation;
``settle``/``release``/``reconcile`` on a closed reservation return the stored result. Nothing
here replays a paid call; ``recover_interrupted`` only converts in-flight state to liability.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.persistence.session import session_scope

from .errors import BudgetExceeded, ProviderUnavailable, ReservationStateError
from .provider import Pricing
from .tables import budget_period, pricing_revision, provider_attempt, spend_reservation

logger = logging.getLogger("fieldlens.assistant.budget")

ZERO = Decimal("0")
QUANT = Decimal("0.000001")
_REASON = re.compile(r"[a-z][a-z0-9_]{0,31}")
CHARGEABLE_UNKNOWN = ("dispatched", "timeout", "unknown")


def usd(value: Decimal | str | int) -> Decimal:
    return Decimal(value).quantize(QUANT)


@dataclass(frozen=True)
class BudgetStatus:
    period_id: UUID
    cap_usd: Decimal
    committed_usd: Decimal
    available_usd: Decimal
    warn: bool
    paused: bool


@dataclass(frozen=True)
class Reservation:
    reservation_id: UUID
    period_id: UUID
    request_key: str
    state: str
    reserved_usd: Decimal
    committed_usd: Decimal
    pricing_id: UUID
    attempts_dispatched: int
    tool_calls_used: int
    reconciliation_status: str
    warn: bool = False
    overrun: bool = False


def _row_to_reservation(row: Any, warn: bool = False) -> Reservation:
    return Reservation(
        reservation_id=row.reservation_id,
        period_id=row.period_id,
        request_key=row.request_key,
        state=row.state,
        reserved_usd=row.reserved_usd,
        committed_usd=row.committed_usd,
        pricing_id=row.pricing_id,
        attempts_dispatched=row.attempts_dispatched,
        tool_calls_used=row.tool_calls_used,
        reconciliation_status=row.reconciliation_status,
        warn=warn,
        overrun=row.overrun,
    )


class BudgetLedger:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    # -- configuration (owner-operated) -----------------------------------------------------
    def ensure_period(
        self,
        name: str,
        *,
        ledger_cap_usd: Decimal,
        warn_usd: Decimal,
        unattended_block_usd: Decimal,
    ) -> UUID:
        """Create the period if absent; an existing period is never modified."""
        with session_scope(self._factory) as s:
            s.execute(
                insert(budget_period)
                .values(
                    name=name,
                    ledger_cap_usd=usd(ledger_cap_usd),
                    warn_usd=usd(warn_usd),
                    unattended_block_usd=usd(unattended_block_usd),
                )
                .on_conflict_do_nothing(index_elements=["name"])
            )
            found = s.execute(
                select(budget_period.c.period_id).where(budget_period.c.name == name)
            ).scalar_one()
            return found  # type: ignore[no-any-return]

    def confirm_balance(self, period_id: UUID, balance_usd: Decimal, source: str) -> None:
        """Owner-confirmed starting balance. Set once; re-baselining needs a new period."""
        with session_scope(self._factory) as s:
            row = s.execute(
                select(budget_period)
                .where(budget_period.c.period_id == period_id)
                .with_for_update()
            ).one()
            if row.starting_balance_usd is not None:
                raise ReservationStateError(
                    "starting balance is already confirmed; use a new period"
                )
            s.execute(
                update(budget_period)
                .where(budget_period.c.period_id == period_id)
                .values(
                    starting_balance_usd=usd(balance_usd),
                    balance_source=source[:500],
                    balance_confirmed_at=datetime.now(UTC),
                )
            )

    def set_paused(self, period_id: UUID, paused: bool) -> None:
        with session_scope(self._factory) as s:
            s.execute(
                update(budget_period)
                .where(budget_period.c.period_id == period_id)
                .values(paused=paused)
            )

    def register_pricing(self, pricing: Pricing, source: str) -> UUID:
        """Idempotent by revision; the same revision with different rates is rejected."""
        pricing.validate()  # typed InvalidPricing before any database write
        values = dict(
            revision=pricing.revision,
            model=pricing.model,
            input_usd_per_mtok=usd(pricing.input_usd_per_mtok),
            cached_input_usd_per_mtok=None
            if pricing.cached_input_usd_per_mtok is None
            else usd(pricing.cached_input_usd_per_mtok),
            output_usd_per_mtok=usd(pricing.output_usd_per_mtok),
        )
        with session_scope(self._factory) as s:
            s.execute(
                insert(pricing_revision)
                .values(source=source[:500], **values)
                .on_conflict_do_nothing(index_elements=["revision"])
            )
            row = s.execute(
                select(pricing_revision).where(pricing_revision.c.revision == pricing.revision)
            ).one()
            if any(getattr(row, k) != v for k, v in values.items()):
                raise ReservationStateError("pricing revision exists with different values")
            return row.pricing_id  # type: ignore[no-any-return]

    def get_pricing(self, pricing_id: UUID) -> Pricing:
        with session_scope(self._factory) as s:
            row = s.execute(
                select(pricing_revision).where(pricing_revision.c.pricing_id == pricing_id)
            ).one_or_none()
        if row is None:
            raise ProviderUnavailable("pricing revision is not recorded")
        return Pricing(
            revision=row.revision,
            model=row.model,
            input_usd_per_mtok=row.input_usd_per_mtok,
            output_usd_per_mtok=row.output_usd_per_mtok,
            cached_input_usd_per_mtok=row.cached_input_usd_per_mtok,
        )

    # -- status -----------------------------------------------------------------------------
    def status(self, period_id: UUID) -> BudgetStatus:
        with session_scope(self._factory) as s:
            return self._status(s, period_id)

    def _status(self, s: Session, period_id: UUID, *, lock: bool = False) -> BudgetStatus:
        query = select(budget_period).where(budget_period.c.period_id == period_id)
        row = s.execute(query.with_for_update() if lock else query).one()
        committed = s.execute(
            select(func.coalesce(func.sum(spend_reservation.c.committed_usd), 0)).where(
                spend_reservation.c.period_id == period_id
            )
        ).scalar_one()
        if row.starting_balance_usd is None:
            cap = ZERO  # unusable until the owner confirms a balance
        else:
            cap = min(row.ledger_cap_usd, row.starting_balance_usd)
        return BudgetStatus(
            period_id=period_id,
            cap_usd=cap,
            committed_usd=committed,
            available_usd=max(cap - committed, ZERO),
            warn=committed >= row.warn_usd,
            paused=row.paused,
        )

    # -- reserve ----------------------------------------------------------------------------
    def reserve(
        self,
        period_id: UUID,
        request_key: str,
        amount_usd: Decimal,
        pricing_id: UUID,
        *,
        work_unit: str,
        unattended: bool = False,
    ) -> Reservation:
        amount = usd(amount_usd)
        if amount <= 0:
            raise BudgetExceeded(amount, ZERO, "non_positive")
        with session_scope(self._factory) as s:
            period = s.execute(
                select(budget_period)
                .where(budget_period.c.period_id == period_id)
                .with_for_update()
            ).one()
            existing = s.execute(
                select(spend_reservation).where(
                    spend_reservation.c.period_id == period_id,
                    spend_reservation.c.request_key == request_key,
                )
            ).one_or_none()
            if existing is not None:
                if existing.reserved_usd != amount:
                    raise ReservationStateError("request key reused with a different amount")
                return _row_to_reservation(existing)
            if period.paused:
                raise ProviderUnavailable("budget is paused")
            if period.starting_balance_usd is None:
                raise ProviderUnavailable("starting balance is not confirmed")
            status = self._status(s, period_id)
            if amount > status.available_usd:
                raise BudgetExceeded(amount, status.available_usd)
            after = status.committed_usd + amount
            if unattended and after > period.unattended_block_usd:
                raise BudgetExceeded(
                    amount,
                    max(period.unattended_block_usd - status.committed_usd, ZERO),
                    "unattended_block",
                )
            row = s.execute(
                insert(spend_reservation)
                .values(
                    period_id=period_id,
                    pricing_id=pricing_id,
                    request_key=request_key,
                    work_unit=work_unit[:120],
                    reserved_usd=amount,
                    committed_usd=amount,
                )
                .returning(spend_reservation)
            ).one()
            return _row_to_reservation(row, warn=after >= period.warn_usd)

    def get(self, reservation_id: UUID) -> Reservation:
        with session_scope(self._factory) as s:
            return _row_to_reservation(self._lock(s, reservation_id, lock=False))

    @staticmethod
    def _lock(s: Session, reservation_id: UUID, *, lock: bool = True) -> Any:
        query = select(spend_reservation).where(
            spend_reservation.c.reservation_id == reservation_id
        )
        row = s.execute(query.with_for_update() if lock else query).one_or_none()
        if row is None:
            raise ReservationStateError("unknown reservation")
        return row

    # -- attempts ---------------------------------------------------------------------------
    def begin_attempt(
        self,
        reservation_id: UUID,
        *,
        provider: str,
        model: str,
        estimated_usd: Decimal,
        retry_of: int | None = None,
    ) -> int:
        """Persist the dispatch *before* the call so a crash retains the liability."""
        with session_scope(self._factory) as s:
            row = self._lock(s, reservation_id)
            if row.state != "reserved":
                raise ReservationStateError("reservation is closed")
            number = int(row.attempts_dispatched) + 1
            s.execute(
                insert(provider_attempt).values(
                    reservation_id=reservation_id,
                    attempt_no=number,
                    retry_of_attempt_no=retry_of,
                    provider=provider[:32],
                    model=model[:128],
                    estimated_usd=usd(estimated_usd),
                )
            )
            s.execute(
                update(spend_reservation)
                .where(spend_reservation.c.reservation_id == reservation_id)
                .values(attempts_dispatched=number, updated_at=func.now())
            )
            return number

    def finish_attempt(
        self,
        reservation_id: UUID,
        attempt_no: int,
        *,
        status: str,
        billed_usd: Decimal | None,
        error_code: str | None = None,
        provider_request_id: str | None = None,
        input_tokens: int | None = None,
        cached_input_tokens: int | None = None,
        output_tokens: int | None = None,
        web_search_queries: int | None = None,
        elapsed_ms: int | None = None,
    ) -> None:
        """``billed_usd=None`` keeps the attempt as estimated liability (never as zero)."""
        request_id = provider_request_id[:128] if provider_request_id else None
        with session_scope(self._factory) as s:
            self._lock(s, reservation_id)
            s.execute(
                update(provider_attempt)
                .where(
                    provider_attempt.c.reservation_id == reservation_id,
                    provider_attempt.c.attempt_no == attempt_no,
                )
                .values(
                    status=status,
                    billed_usd=None if billed_usd is None else usd(billed_usd),
                    error_code=error_code,
                    provider_request_id=request_id,
                    input_tokens=input_tokens,
                    cached_input_tokens=cached_input_tokens,
                    output_tokens=output_tokens,
                    web_search_queries=web_search_queries,
                    elapsed_ms=elapsed_ms,
                    finished_at=func.now(),
                )
            )

    def add_tool_calls(self, reservation_id: UUID, count: int) -> int:
        with session_scope(self._factory) as s:
            self._lock(s, reservation_id)
            return s.execute(  # type: ignore[no-any-return]
                update(spend_reservation)
                .where(spend_reservation.c.reservation_id == reservation_id)
                .values(
                    tool_calls_used=spend_reservation.c.tool_calls_used + count,
                    updated_at=func.now(),
                )
                .returning(spend_reservation.c.tool_calls_used)
            ).scalar_one()

    def spent_so_far(self, reservation_id: UUID) -> Decimal:
        """Billed amount plus estimated liability of attempts with unknown billing."""
        with session_scope(self._factory) as s:
            return self._attempt_total(s, reservation_id)[0]

    def attempt_tokens(self, reservation_id: UUID) -> tuple[int, int]:
        """Provider-reported (input, output) tokens summed over the reservation's attempts."""
        with session_scope(self._factory) as s:
            row = s.execute(
                select(
                    func.coalesce(func.sum(provider_attempt.c.input_tokens), 0),
                    func.coalesce(func.sum(provider_attempt.c.output_tokens), 0),
                ).where(provider_attempt.c.reservation_id == reservation_id)
            ).one()
        return int(row[0]), int(row[1])

    @staticmethod
    def _known_billed(s: Session, reservation_id: UUID) -> Decimal:
        total = s.execute(
            select(func.coalesce(func.sum(provider_attempt.c.billed_usd), 0)).where(
                provider_attempt.c.reservation_id == reservation_id,
                provider_attempt.c.billed_usd.is_not(None),
            )
        ).scalar_one()
        return usd(total)

    @staticmethod
    def _attempt_total(s: Session, reservation_id: UUID) -> tuple[Decimal, bool]:
        rows = s.execute(
            select(provider_attempt.c.billed_usd, provider_attempt.c.estimated_usd).where(
                provider_attempt.c.reservation_id == reservation_id
            )
        ).all()
        total = sum(
            (r.billed_usd if r.billed_usd is not None else r.estimated_usd for r in rows), ZERO
        )
        unresolved = any(r.billed_usd is None for r in rows)
        return total, unresolved

    # -- close ------------------------------------------------------------------------------
    def settle(self, reservation_id: UUID) -> Reservation:
        """Close from attempt records. Unknown billing stays liable until ``reconcile``."""
        with session_scope(self._factory) as s:
            row = self._lock(s, reservation_id)
            if row.state != "reserved":
                return _row_to_reservation(row)  # idempotent
            if row.attempts_dispatched == 0:
                state, committed, recon = "released", ZERO, "not_needed"
            else:
                committed, unresolved = self._attempt_total(s, reservation_id)
                state = "liable" if unresolved else "settled"
                recon = "pending" if unresolved else "not_needed"
            overrun = committed > row.reserved_usd
            out = s.execute(
                update(spend_reservation)
                .where(spend_reservation.c.reservation_id == reservation_id)
                .values(
                    state=state,
                    committed_usd=committed,
                    reconciliation_status=recon,
                    overrun=overrun,
                    closed_at=func.now(),
                    updated_at=func.now(),
                )
                .returning(spend_reservation)
            ).one()
            if overrun:
                self._flag_overrun(s, out)
            return _row_to_reservation(out)

    @staticmethod
    def _flag_overrun(s: Session, row: Any) -> None:
        """Honest record of spend above the reservation: warn loudly and pause the period."""
        s.execute(
            update(budget_period)
            .where(budget_period.c.period_id == row.period_id)
            .values(paused=True)
        )
        logger.warning(
            "budget overrun: reservation %s committed USD %s above reserved USD %s; "
            "period %s paused until the owner reviews",
            row.reservation_id,
            row.committed_usd,
            row.reserved_usd,
            row.period_id,
        )

    def release(self, reservation_id: UUID) -> Reservation:
        """Free a reservation only if no attempt was ever dispatched."""
        with session_scope(self._factory) as s:
            row = self._lock(s, reservation_id)
            if row.state == "released":
                return _row_to_reservation(row)
            if row.state != "reserved":
                raise ReservationStateError("only an open reservation can be released")
            if row.attempts_dispatched > 0:
                raise ReservationStateError(
                    "a dispatched attempt keeps its liability; settle instead"
                )
            out = s.execute(
                update(spend_reservation)
                .where(spend_reservation.c.reservation_id == reservation_id)
                .values(
                    state="released",
                    committed_usd=ZERO,
                    closed_at=func.now(),
                    updated_at=func.now(),
                )
                .returning(spend_reservation)
            ).one()
            return _row_to_reservation(out)

    def list_liable(self, period_id: UUID) -> list[Reservation]:
        """Liable (billing-unknown) reservations awaiting reconciliation; survives restarts."""
        with session_scope(self._factory) as s:
            rows = s.execute(
                select(spend_reservation)
                .where(
                    spend_reservation.c.period_id == period_id,
                    spend_reservation.c.state == "liable",
                )
                .order_by(spend_reservation.c.created_at)
            ).all()
        return [_row_to_reservation(r) for r in rows]

    def release_liable(self, reservation_id: UUID, reason: str) -> Reservation:
        """Release the *unresolved* attempts of a liable reservation as not billed.

        The reservation settles at the sum of its attempts with known billed amounts (the known
        floor), never below it; it only drops to 0 when no attempt has a known bill. The reason
        slug is appended to the unresolved attempts' error code (``provider_timeout>reason``).
        The row ends ``settled`` (``released`` is reserved for never-dispatched reservations by a
        table constraint).
        """
        return self.reconcile(reservation_id, None, reason=reason)

    def reconcile(
        self,
        reservation_id: UUID,
        billed_total_usd: Decimal | None,
        *,
        reason: str | None = None,
    ) -> Reservation:
        """Owner/provider-confirmed total for a liable reservation (idempotent for equal totals).

        The total may not be negative, non-finite or below the known billed floor (completed
        attempts' billed amounts); that raises ``ReservationStateError``. A total above the
        reservation is accepted but flagged as an overrun and pauses the period. ``None`` means
        the known floor (used by ``release_liable``). ``reason`` (a short slug) is recorded on the
        unresolved attempts; a repeat call with an unchanged total returns the stored result, so
        the first reason wins. When the total equals the floor, unresolved attempts are recorded
        as billed 0.
        """
        if reason is not None and not _REASON.fullmatch(reason):
            raise ReservationStateError("reconcile reason must be a short lowercase slug")
        if billed_total_usd is not None and (
            not billed_total_usd.is_finite() or billed_total_usd < 0
        ):
            raise ReservationStateError("reconciled total must be a finite non-negative amount")
        with session_scope(self._factory) as s:
            row = self._lock(s, reservation_id)
            floor = self._known_billed(s, reservation_id)
            total = floor if billed_total_usd is None else usd(billed_total_usd)
            if row.reconciliation_status == "reconciled":
                if row.committed_usd == total:
                    return _row_to_reservation(row)
                raise ReservationStateError("reservation already reconciled with a different total")
            if row.state != "liable":
                raise ReservationStateError("only a liable reservation can be reconciled")
            if total < floor:
                raise ReservationStateError("reconciled total is below the known billed amount")
            unresolved = s.execute(
                select(provider_attempt.c.attempt_no, provider_attempt.c.error_code).where(
                    provider_attempt.c.reservation_id == reservation_id,
                    provider_attempt.c.billed_usd.is_(None),
                )
            ).all()
            for attempt in unresolved:
                values: dict[str, Any] = {}
                if total == floor:
                    values["billed_usd"] = ZERO
                if reason is not None:
                    values["error_code"] = f"{attempt.error_code or 'unknown'}>{reason}"[:64]
                if values:
                    s.execute(
                        update(provider_attempt)
                        .where(
                            provider_attempt.c.reservation_id == reservation_id,
                            provider_attempt.c.attempt_no == attempt.attempt_no,
                        )
                        .values(**values)
                    )
            s.execute(
                update(provider_attempt)
                .where(provider_attempt.c.reservation_id == reservation_id)
                .values(reconciled=True)
            )
            out = s.execute(
                update(spend_reservation)
                .where(spend_reservation.c.reservation_id == reservation_id)
                .values(
                    state="settled",
                    committed_usd=total,
                    reconciliation_status="reconciled",
                    overrun=total > row.reserved_usd,
                    updated_at=func.now(),
                )
                .returning(spend_reservation)
            ).one()
            if out.overrun:
                self._flag_overrun(s, out)
            return _row_to_reservation(out)

    def recover_interrupted(self, period_id: UUID) -> list[Reservation]:
        """After a restart: in-flight attempts become unknown liability; unused ones release.

        Never re-dispatches a call. Returns the reservations that were closed.
        """
        with session_scope(self._factory) as s:
            open_ids = (
                s.execute(
                    select(spend_reservation.c.reservation_id).where(
                        spend_reservation.c.period_id == period_id,
                        spend_reservation.c.state == "reserved",
                    )
                )
                .scalars()
                .all()
            )
        closed: list[Reservation] = []
        for rid in open_ids:
            with session_scope(self._factory) as s:
                s.execute(
                    update(provider_attempt)
                    .where(
                        provider_attempt.c.reservation_id == rid,
                        provider_attempt.c.status == "dispatched",
                    )
                    .values(status="unknown", finished_at=func.now())
                )
            closed.append(self.settle(rid))
        return closed


__all__ = ["BudgetLedger", "BudgetStatus", "Reservation", "usd"]

"""MI-3: concurrent reservations cannot exceed the cap; reservations survive restart."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.errors import BudgetExceeded, ProviderUnavailable, ReservationStateError
from fieldlens.persistence.session import create_session_factory

D = Decimal


def _small_period(ledger: BudgetLedger, cap: str = "100", balance: str = "100") -> UUID:
    pid = ledger.ensure_period(
        f"small-{cap}-{balance}",
        ledger_cap_usd=D(cap),
        warn_usd=D(cap) * D("0.6"),
        unattended_block_usd=D(cap) * D("0.8"),
    )
    ledger.confirm_balance(pid, D(balance), "test")
    return pid


def test_concurrent_reservations_never_exceed_cap(
    factory: sessionmaker[Session], ledger: BudgetLedger, pricing_id: UUID
) -> None:
    pid = _small_period(ledger)

    def attempt(i: int) -> str:
        try:
            BudgetLedger(factory).reserve(pid, f"k{i}", D("30"), pricing_id, work_unit="race")
            return "ok"
        except BudgetExceeded:
            return "denied"

    with ThreadPoolExecutor(max_workers=12) as pool:
        results = list(pool.map(attempt, range(12)))
    assert results.count("ok") == 3 and results.count("denied") == 9  # 3 * 30 <= 100 < 4 * 30
    assert ledger.status(pid).committed_usd == D("90")
    assert ledger.status(pid).available_usd == D("10")


def test_concurrent_same_key_is_idempotent(
    factory: sessionmaker[Session], ledger: BudgetLedger, pricing_id: UUID
) -> None:
    pid = _small_period(ledger)

    def attempt(_: int) -> UUID:
        return (
            BudgetLedger(factory)
            .reserve(pid, "same", D("40"), pricing_id, work_unit="u")
            .reservation_id
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = set(pool.map(attempt, range(8)))
    assert len(ids) == 1 and ledger.status(pid).committed_usd == D("40")


def test_key_reuse_with_other_amount_is_rejected(ledger: BudgetLedger, pricing_id: UUID) -> None:
    pid = _small_period(ledger)
    ledger.reserve(pid, "k", D("5"), pricing_id, work_unit="u")
    with pytest.raises(ReservationStateError):
        ledger.reserve(pid, "k", D("6"), pricing_id, work_unit="u")


def test_effective_cap_is_lower_of_ceiling_and_confirmed_balance(
    ledger: BudgetLedger, pricing_id: UUID
) -> None:
    pid = _small_period(ledger, cap="100", balance="20")
    assert ledger.status(pid).cap_usd == D("20")
    ledger.reserve(pid, "a", D("20"), pricing_id, work_unit="u")
    with pytest.raises(BudgetExceeded):
        ledger.reserve(pid, "b", D("0.01"), pricing_id, work_unit="u")


def test_unconfirmed_balance_and_pause_fail_before_reserving(
    ledger: BudgetLedger, pricing_id: UUID
) -> None:
    pid = ledger.ensure_period(
        "nobal", ledger_cap_usd=D("10"), warn_usd=D("5"), unattended_block_usd=D("8")
    )
    with pytest.raises(ProviderUnavailable, match="balance"):
        ledger.reserve(pid, "k", D("1"), pricing_id, work_unit="u")
    ledger.confirm_balance(pid, D("10"), "owner")
    with pytest.raises(ReservationStateError):
        ledger.confirm_balance(pid, D("9"), "owner")  # re-baselining needs a new period
    ledger.set_paused(pid, True)
    with pytest.raises(ProviderUnavailable, match="paused"):
        ledger.reserve(pid, "k", D("1"), pricing_id, work_unit="u")


def test_warn_and_unattended_block_thresholds(ledger: BudgetLedger, pricing_id: UUID) -> None:
    pid = _small_period(ledger)  # warn 60, block 80
    assert not ledger.reserve(pid, "a", D("50"), pricing_id, work_unit="u").warn
    assert ledger.reserve(pid, "b", D("20"), pricing_id, work_unit="u").warn
    with pytest.raises(BudgetExceeded) as info:
        ledger.reserve(pid, "c", D("20"), pricing_id, work_unit="u", unattended=True)
    assert info.value.reason == "unattended_block"
    ledger.reserve(
        pid, "d", D("20"), pricing_id, work_unit="u"
    )  # attended spend may use the reserve


def test_settle_release_and_idempotency(ledger: BudgetLedger, pricing_id: UUID) -> None:
    pid = _small_period(ledger)
    r = ledger.reserve(pid, "a", D("30"), pricing_id, work_unit="u")
    released = ledger.release(r.reservation_id)
    assert released.state == "released" and released.committed_usd == 0
    assert ledger.release(r.reservation_id) == released  # idempotent
    assert ledger.settle(r.reservation_id) == released  # idempotent, no state change
    assert ledger.status(pid).committed_usd == 0

    r2 = ledger.reserve(pid, "b", D("30"), pricing_id, work_unit="u")
    n = ledger.begin_attempt(r2.reservation_id, provider="stub", model="m", estimated_usd=D("2"))
    with pytest.raises(ReservationStateError):
        ledger.release(r2.reservation_id)  # a dispatched attempt keeps its liability
    ledger.finish_attempt(r2.reservation_id, n, status="completed", billed_usd=D("1.25"))
    settled = ledger.settle(r2.reservation_id)
    assert settled.state == "settled" and settled.committed_usd == D("1.25")
    assert ledger.settle(r2.reservation_id) == settled
    assert ledger.status(pid).committed_usd == D("1.25")


def test_reservations_survive_restart(
    migrated_url: URL, ledger: BudgetLedger, pricing_id: UUID
) -> None:
    pid = _small_period(ledger)
    r = ledger.reserve(pid, "persist", D("25"), pricing_id, work_unit="u")
    n = ledger.begin_attempt(r.reservation_id, provider="stub", model="m", estimated_usd=D("3"))
    assert n == 1
    # "Restart": a brand-new engine/ledger sees the same liability and never replays the call.
    fresh_engine: Engine = create_engine(migrated_url)
    try:
        fresh = BudgetLedger(create_session_factory(fresh_engine))
        assert fresh.status(pid).committed_usd == D("25")
        assert (
            fresh.reserve(pid, "persist", D("25"), pricing_id, work_unit="u").reservation_id
            == r.reservation_id
        )
        closed = fresh.recover_interrupted(pid)
        assert [c.state for c in closed] == ["liable"] and closed[0].committed_usd == D("3")
        assert fresh.status(pid).committed_usd == D("3")
    finally:
        fresh_engine.dispose()


def test_recovery_releases_units_that_never_dispatched(
    ledger: BudgetLedger, pricing_id: UUID
) -> None:
    pid = _small_period(ledger)
    ledger.reserve(pid, "idle", D("25"), pricing_id, work_unit="u")
    [closed] = ledger.recover_interrupted(pid)
    assert closed.state == "released" and ledger.status(pid).committed_usd == 0


def test_database_rejects_a_cap_above_150(engine: Engine) -> None:
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO budget_period (name, ledger_cap_usd, warn_usd, unattended_block_usd) "
                "VALUES ('big', 151, 100, 120)"
            )
        )


def test_settle_overrun_is_recorded_flagged_and_pauses_the_period(
    ledger: BudgetLedger, pricing_id: UUID, caplog: pytest.LogCaptureFixture
) -> None:
    pid = _small_period(ledger, cap="1", balance="0.60")
    res = ledger.reserve(pid, "big", D("0.50"), pricing_id, work_unit="u")
    number = ledger.begin_attempt(
        res.reservation_id, provider="stub", model="m", estimated_usd=D("0.10"), retry_of=None
    )
    ledger.finish_attempt(res.reservation_id, number, status="completed", billed_usd=D("20.00001"))
    with caplog.at_level("WARNING", logger="fieldlens.assistant.budget"):
        closed = ledger.settle(res.reservation_id)
    assert closed.committed_usd == D("20.00001") and closed.overrun  # recorded honestly
    assert "budget overrun" in caplog.text
    assert ledger.status(pid).paused
    with pytest.raises(ProviderUnavailable, match="paused"):
        ledger.reserve(pid, "next", D("0.01"), pricing_id, work_unit="u")
    assert ledger.settle(res.reservation_id) == closed  # idempotent
    ok = ledger.reserve(
        _small_period(ledger, cap="2", balance="2"), "fine", D("0.5"), pricing_id, work_unit="u"
    )
    assert not ok.overrun


def test_spend_within_reservation_does_not_flag_or_pause(
    ledger: BudgetLedger, pricing_id: UUID
) -> None:
    pid = _small_period(ledger, cap="1", balance="0.60")
    res = ledger.reserve(pid, "ok", D("0.50"), pricing_id, work_unit="u")
    n = ledger.begin_attempt(
        res.reservation_id, provider="stub", model="m", estimated_usd=D("0.10"), retry_of=None
    )
    ledger.finish_attempt(res.reservation_id, n, status="completed", billed_usd=D("0.40"))
    closed = ledger.settle(res.reservation_id)
    assert not closed.overrun and not ledger.status(pid).paused

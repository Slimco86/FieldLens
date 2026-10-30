"""MI-4: timeout liability, single retry for 429/5xx, no automatic retry for 401/403/refusal/bad schema."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from fieldlens.assistant import errors
from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.messages import ProviderResponse, Usage
from fieldlens.assistant.stub import (
    StubProvider,
    refusal_response,
    text_response,
    tool_call_response,
    truncated_response,
)
from tests.assistant_support import LOOKUP_TOOL, MakeUnit, user

USAGE = Usage(input_tokens=1000, cached_input_tokens=0, output_tokens=500)  # 0.001 + 0.002 USD


def _attempts(engine: Engine, rid: UUID) -> list[tuple[int, str, str | None, Decimal | None]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT attempt_no, status, error_code, billed_usd FROM provider_attempt "
                "WHERE reservation_id = :r ORDER BY attempt_no"
            ),
            {"r": rid},
        ).all()
    return [tuple(r) for r in rows]  # type: ignore[misc]


def test_success_accounts_billed_usage_and_releases_remainder(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID, engine: Engine
) -> None:
    stub = StubProvider([text_response("ok", USAGE)])
    with make_unit(stub) as unit:
        assert unit.step([user("hi")]).text() == "ok"
    assert unit.closed is not None and unit.closed.state == "settled"
    assert unit.closed.committed_usd == Decimal("0.003000")
    assert ledger.status(period).committed_usd == Decimal("0.003")


def test_timeout_retains_estimated_liability_until_reconciliation(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID, engine: Engine
) -> None:
    stub = StubProvider([errors.ProviderTimeout("late")])
    with pytest.raises(errors.ProviderTimeout):
        with make_unit(stub) as unit:
            unit.step([user("hi")])
    closed = unit.closed
    assert (
        closed is not None
        and closed.state == "liable"
        and closed.reconciliation_status == "pending"
    )
    assert closed.committed_usd > 0  # estimated upper bound stays committed
    assert ledger.status(period).committed_usd == closed.committed_usd
    [(_, status, code, billed)] = _attempts(engine, closed.reservation_id)
    assert (status, code, billed) == ("timeout", "provider_timeout", None)  # unknown, not zero
    final = ledger.reconcile(closed.reservation_id, Decimal("0.002"))
    assert final.state == "settled" and ledger.status(period).committed_usd == Decimal("0.002")
    assert ledger.reconcile(closed.reservation_id, Decimal("0.002")) == final  # idempotent
    with pytest.raises(errors.ReservationStateError):
        ledger.reconcile(closed.reservation_id, Decimal("0.5"))


@pytest.mark.parametrize(
    "failure", [errors.ProviderRateLimited(), errors.ProviderServerError("5xx")]
)
def test_429_and_5xx_retry_once_then_succeed(
    make_unit: MakeUnit, engine: Engine, failure: errors.AssistantError
) -> None:
    stub = StubProvider([failure, text_response("ok", USAGE)])
    with make_unit(stub) as unit:
        assert unit.step([user("hi")]).text() == "ok"
    assert len(stub.calls) == 2 and unit.attempts == 2
    rows = _attempts(engine, unit.reservation.reservation_id)  # type: ignore[union-attr]
    assert [r[1] for r in rows] == ["failed", "completed"]


@pytest.mark.parametrize(
    "failure", [errors.ProviderRateLimited(), errors.ProviderServerError("5xx")]
)
def test_a_second_429_or_5xx_is_not_retried_again(
    make_unit: MakeUnit, failure: errors.AssistantError
) -> None:
    stub = StubProvider([failure, failure, text_response("never")])
    with pytest.raises(type(failure)):
        with make_unit(stub) as unit:
            unit.step([user("hi")])
    assert len(stub.calls) == 2  # exactly one retry


def test_429_then_5xx_raises_after_one_retry_and_only_5xx_is_liable(
    make_unit: MakeUnit, engine: Engine
) -> None:
    stub = StubProvider([errors.ProviderRateLimited(), errors.ProviderServerError("x")])
    with pytest.raises(errors.ProviderServerError):
        with make_unit(stub) as unit:
            unit.step([user("hi")])
    rows = _attempts(engine, unit.reservation.reservation_id)  # type: ignore[union-attr]
    assert rows[0][3] == Decimal("0") and rows[1][3] is None
    assert unit.closed is not None and unit.closed.state == "liable"


@pytest.mark.parametrize(
    "failure", [errors.ProviderAuthError("401"), errors.ProviderMalformed("bad")]
)
def test_auth_and_malformed_are_not_retried(
    make_unit: MakeUnit, engine: Engine, failure: errors.AssistantError
) -> None:
    stub = StubProvider([failure, text_response("never")])
    with pytest.raises(type(failure)):
        with make_unit(stub) as unit:
            unit.step([user("hi")])
    assert len(stub.calls) == 1


def test_auth_failure_is_definitively_not_billed(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    with pytest.raises(errors.ProviderAuthError):
        with make_unit(StubProvider([errors.ProviderAuthError("403")])) as unit:
            unit.step([user("hi")])
    assert unit.closed is not None and unit.closed.state == "settled"
    assert unit.closed.committed_usd == 0 and ledger.status(period).committed_usd == 0


def test_refusal_is_not_retried_and_usage_is_accounted(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    stub = StubProvider([refusal_response(USAGE), text_response("never")])
    with pytest.raises(errors.ProviderRefusal):
        with make_unit(stub) as unit:
            unit.step([user("hi")])
    assert len(stub.calls) == 1
    assert ledger.status(period).committed_usd == Decimal("0.003")


def test_truncation_is_typed_and_not_a_success(make_unit: MakeUnit) -> None:
    stub = StubProvider([truncated_response("partial", USAGE)])
    with pytest.raises(errors.ProviderTruncated):
        with make_unit(stub) as unit:
            unit.step([user("hi")])
    assert len(stub.calls) == 1


def test_missing_usage_stays_estimated_liability_not_zero(make_unit: MakeUnit) -> None:
    with make_unit(StubProvider([text_response("ok", None)])) as unit:
        unit.step([user("hi")])
    assert unit.closed is not None
    assert unit.closed.state == "liable" and unit.closed.committed_usd > 0


@pytest.mark.parametrize(
    "bad",
    [
        ProviderResponse(parts=()),
        tool_call_response(("c1", "delete_everything", {})),
        tool_call_response(("c1", "read_page", {"page": "three"})),
        tool_call_response(("c1", "read_page", {})),
    ],
    ids=["empty", "unknown_tool", "bad_argument_type", "missing_argument"],
)
def test_malformed_output_is_typed_and_not_retried(
    make_unit: MakeUnit, bad: ProviderResponse
) -> None:
    stub = StubProvider([bad, text_response("never")])
    with pytest.raises(errors.ProviderMalformed):
        with make_unit(stub, tools=[LOOKUP_TOOL]) as unit:
            unit.step([user("hi")])
    assert len(stub.calls) == 1


def test_unexpected_exception_keeps_liability(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    def boom(_: object) -> ProviderResponse:
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        with make_unit(StubProvider([boom])) as unit:
            unit.step([user("hi")])
    assert unit.closed is not None and unit.closed.state == "liable"
    assert ledger.status(period).committed_usd > 0


def test_cancel_raised_after_dispatch_is_chargeable_unknown_not_zero(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID, engine: Engine
) -> None:
    stub = StubProvider([errors.RequestCancelled()])
    with pytest.raises(errors.RequestCancelled):
        with make_unit(stub) as unit:
            unit.step([user("hi")])
    closed = unit.closed
    assert closed is not None and closed.state == "liable"
    assert closed.reconciliation_status == "pending" and closed.committed_usd > 0
    [(_, status, _, billed)] = _attempts(engine, closed.reservation_id)
    assert (status, billed) == ("unknown", None)

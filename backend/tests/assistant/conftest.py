"""Shared fixtures for the offline provider/budget tests (PostgreSQL only; zero network)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.provider import CancelToken
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.assistant.stub import StubProvider
from fieldlens.persistence.session import create_session_factory
from tests.assistant_support import MODEL, PRICING, MakeUnit


@pytest.fixture
def factory(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def ledger(factory: sessionmaker[Session]) -> BudgetLedger:
    return BudgetLedger(factory)


@pytest.fixture
def period(ledger: BudgetLedger) -> UUID:
    pid = ledger.ensure_period(
        "test",
        ledger_cap_usd=Decimal("150"),
        warn_usd=Decimal("100"),
        unattended_block_usd=Decimal("120"),
    )
    ledger.confirm_balance(pid, Decimal("150"), "test fixture")
    return pid


@pytest.fixture
def pricing_id(ledger: BudgetLedger) -> UUID:
    return ledger.register_pricing(PRICING, "synthetic test rates")


@pytest.fixture
def make_unit(ledger: BudgetLedger, period: UUID, pricing_id: UUID) -> MakeUnit:
    counter = iter(range(10_000))

    def make(provider: Any = None, **overrides: Any) -> WorkUnit:
        limits = overrides.pop("limits", RequestLimits(retry_backoff_s=0.0))
        return WorkUnit(
            provider=provider or StubProvider(),
            ledger=ledger,
            period_id=overrides.pop("period_id", period),
            pricing_id=pricing_id,
            pricing=PRICING,
            model=overrides.pop("model", MODEL),
            request_key=overrides.pop("request_key", f"req-{next(counter)}"),
            work_unit="test-unit",
            limits=limits,
            cancel=overrides.pop("cancel", CancelToken()),
            **overrides,
        )

    return make

"""TASK-055 opt-in live check: one synthetic page through the real Meta provider.

Skipped by default (``-m 'not live_meta'``). Run only with explicit orchestrator authorization:
``MODEL_API_KEY=... FIELDLENS_LIVE_META=1 FIELDLENS_LIVE_META_INPUT_USD=.. FIELDLENS_LIVE_META_OUTPUT_USD=..
uv run pytest backend/tests/processing/test_document_identity_live.py -m live_meta``
The input is synthetic, the per-run cap is the ledger period ceiling below, and only the sanitized
outcome (category, counts, cost) is asserted; no key or prompt is written anywhere.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.meta import MetaProvider
from fieldlens.assistant.provider import Pricing
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.config import Settings
from fieldlens.persistence.session import create_session_factory
from fieldlens.processing import identity_read as ir
from tests import live_meta_support as lms

pytestmark = pytest.mark.live_meta

CAP = Decimal("0.25")  # per-run cap for this check
PAGE = {
    1: "Completion summary\nWellbore 15/9-F-12 B\nProduction packer set at 2100 m MD\n"
    "Tubing 4.5 in, perforated interval 2150-2180 m",
}


@pytest.fixture
def live_network() -> Iterator[None]:
    saved = [(o, n, getattr(o, n)) for o, n, _ in lms.GUARD_UNDO]
    for owner, name, original in lms.GUARD_UNDO:
        setattr(owner, name, original)
    try:
        yield
    finally:
        for owner, name, patched in saved:
            setattr(owner, name, patched)


def test_live_identity_read(live_network: None) -> None:
    key = lms.STASHED_KEY.get("key")
    problem = lms.live_opt_in_problem(os.environ, key)
    if problem:
        pytest.fail(problem, pytrace=False)
    rate_in = os.environ.get("FIELDLENS_LIVE_META_INPUT_USD", "")
    rate_out = os.environ.get("FIELDLENS_LIVE_META_OUTPUT_USD", "")
    assert rate_in and rate_out, "owner-confirmed Meta rates are required; none are assumed"
    assert key is not None
    settings = Settings(MODEL_API_KEY=key)
    lane_url = dotenv_values(Path(".env")).get("FIELDLENS_DATABASE_URL") or ""
    assert "fieldlens_task_055" in lane_url or "fieldlens_task_005" in lane_url, "lane DB only"
    ledger = BudgetLedger(create_session_factory(create_engine(lane_url)))
    period = ledger.ensure_period(
        "t055-live", ledger_cap_usd=CAP, warn_usd=CAP, unattended_block_usd=CAP
    )
    pricing = Pricing(
        revision="t055-live-owner-rates",
        model=settings.meta_model,
        input_usd_per_mtok=Decimal(rate_in),
        output_usd_per_mtok=Decimal(rate_out),
    )
    pricing_id = ledger.register_pricing(pricing, "owner-confirmed rates for the TASK-055 check")
    provider = MetaProvider(settings)
    unit = WorkUnit(
        provider=provider,
        ledger=ledger,
        period_id=period,
        pricing_id=pricing_id,
        pricing=pricing,
        model=settings.meta_model,
        request_key="t055-live-1",
        work_unit="t055-live-1",
        limits=RequestLimits(max_attempts=1, max_tool_calls=0, max_output_tokens=1200),
        effort="low",
    )
    with unit:
        response = unit.step(ir.build_messages(PAGE))
    outcome = ir.validate(ir.parse_output(response.text()), PAGE)
    assert outcome.category
    assert unit.closed is not None and unit.closed.committed_usd <= CAP
    assert all(i.page == 1 for i in outcome.identities)

"""TASK-074: the live processing period needs no owner step; a failed run says why.

Offline: a scripted provider, no network, throwaway databases only.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.engine import URL

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.errors import ProviderUnavailable
from fieldlens.assistant.runner import RequestLimits
from fieldlens.candidates.pages import PageRenderer
from fieldlens.contracts.processing import ProcessingFailureCode
from fieldlens.processing.model_step import (
    FailureMapping,
    ModelClassificationStep,
    ModelStepConfig,
    map_failure,
)
from fieldlens.processing.runtime import (
    AUTO_BALANCE_SOURCE,
    _ensure_usable_balance,
    build_runtime,
)
from tests.assistant_support import MODEL, PRICING
from tests.processing.conftest import World, build_world
from tests.processing.test_document_identity import (
    Model,
    PricingProvider,
    answer,
    build_model,
)

FAKE_KEY = "not-a-real-key-for-tests"
META = {
    "processing_provider": "meta",
    "processing_meta_input_usd_per_mtok": Decimal("0.3"),
    "processing_meta_output_usd_per_mtok": Decimal("2.5"),
}  # no run cap: it is optional


def meta_world(migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setenv("MODEL_API_KEY", FAKE_KEY)
    return build_world(migrated_url, tmp_path, **META)


def period_row(world: World, name: str = "processing-live") -> Any:
    rows = world.sql(
        "SELECT starting_balance_usd, balance_source, balance_confirmed_at, paused "
        "FROM budget_period WHERE name = :n",
        n=name,
    )
    return rows[0] if rows else None


def rebuild(world: World) -> None:
    app: Any = world.api.client.app
    app.state.processing = build_runtime(
        app.state.session_factory, app.state.blob_store, app.state.settings
    )


# -- the period is usable without any owner step -----------------------------------------------------
def test_fresh_database_gets_a_confirmed_balance_equal_to_the_ledger_cap(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = meta_world(migrated_url, tmp_path, monkeypatch)
    row = period_row(world)
    assert row.starting_balance_usd == Decimal("150") and row.balance_confirmed_at is not None
    assert row.balance_source == AUTO_BALANCE_SOURCE and row.paused is False
    info = world.api.client.get(f"{world.base}/documents").json()["provider_info"]
    assert info["status"] == "live"
    created = world.estimate("report.pdf")  # a blank run cap does not block a normal run
    assert created.status_code == 201, created.text
    assert created.json()["estimate"]["confirmable"] is True


def test_existing_period_with_a_null_balance_is_repaired_once(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = meta_world(migrated_url, tmp_path, monkeypatch)
    world.sql(
        "UPDATE budget_period SET starting_balance_usd = NULL, balance_source = NULL, "
        "balance_confirmed_at = NULL WHERE name = 'processing-live'"
    )
    assert period_row(world).starting_balance_usd is None  # the owner's real state
    rebuild(world)
    row = period_row(world)
    assert row.starting_balance_usd == Decimal("150") and row.balance_source == AUTO_BALANCE_SOURCE


def test_an_already_confirmed_balance_is_never_changed(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = meta_world(migrated_url, tmp_path, monkeypatch)
    world.sql(
        "UPDATE budget_period SET starting_balance_usd = 7, balance_source = 'owner' "
        "WHERE name = 'processing-live'"
    )
    rebuild(world)
    row = period_row(world)
    assert row.starting_balance_usd == Decimal("7") and row.balance_source == "owner"


def test_other_periods_keep_their_explicit_confirmation(
    migrated_url: URL, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = meta_world(migrated_url, tmp_path, monkeypatch)
    ledger = BudgetLedger(world.api.client.app.state.session_factory)
    ledger.ensure_period(
        "equipment-live",
        ledger_cap_usd=Decimal("150"),
        warn_usd=Decimal("100"),
        unattended_block_usd=Decimal("120"),
    )
    rebuild(world)
    assert period_row(world, "equipment-live").starting_balance_usd is None


# -- end to end through reserve / commit, failure reasons, log -----------------------------------------
def step_for(m: Model, period: UUID, ledger: BudgetLedger) -> ModelClassificationStep:
    app: Any = m.world.api.client.app
    return ModelClassificationStep(
        app.state.session_factory,
        ledger,
        m.provider,
        ModelStepConfig(
            period_id=period,
            pricing_id=ledger.register_pricing(PRICING, "synthetic test rates"),
            pricing=PRICING,
            model=MODEL,
            max_pages=5,
            limits=RequestLimits(
                max_attempts=2,
                max_tool_calls=0,
                max_output_tokens=300,
                max_reserved_usd=Decimal("0.10"),
                retry_backoff_s=0.0,
            ),
        ),
        PageRenderer(app.state.blob_store, concurrency=2).page_text,
    )


def fresh_period(m: Model, name: str, *, auto: bool) -> BudgetLedger:
    """Swap in a step on a new, never owner-confirmed period (``auto`` applies the runtime rule)."""
    app: Any = m.world.api.client.app
    ledger = BudgetLedger(app.state.session_factory)
    period = ledger.ensure_period(
        name,
        ledger_cap_usd=Decimal("150"),
        warn_usd=Decimal("100"),
        unattended_block_usd=Decimal("120"),
    )
    if auto:
        _ensure_usable_balance(ledger, period, app.state.settings)
    app.state.processing = build_runtime(
        app.state.session_factory,
        app.state.blob_store,
        app.state.settings,
        provider=PricingProvider(app.state.settings),
        step=step_for(m, period, ledger),
    )
    return ledger


def run_one(m: Model, name: str = "wellbore.pdf") -> dict[str, Any]:
    r = m.world.estimate(name)
    assert r.status_code == 201, r.text
    run = r.json()
    assert m.world.confirm(run).status_code == 202
    assert m.world.drain() == 1
    return m.world.get(run["run_id"])


def test_run_succeeds_on_the_auto_confirmed_period_without_an_owner_step(
    migrated_url: URL, tmp_path: Path
) -> None:
    m = build_model(migrated_url, tmp_path, [answer()])
    fresh_period(m, "t074-auto", auto=True)
    done = run_one(m)
    assert done["status"] == "succeeded", done
    assert done["documents"][0]["state"] == "processed" and len(m.provider.calls) == 1
    assert Decimal(done["actual_usd"]) > 0  # the ledger recorded real reserve/commit spend


def test_without_a_balance_the_failure_says_why_and_one_log_line_is_written(
    migrated_url: URL, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    m = build_model(migrated_url, tmp_path, [answer()])
    fresh_period(m, "t074-none", auto=False)
    with caplog.at_level(logging.WARNING, logger="fieldlens.processing.runner"):
        done = run_one(m)
    doc = done["documents"][0]
    assert doc["state"] == "failed" and doc["failure_code"] == "provider_error"
    assert "provider_unavailable" in doc["failure_message"]
    assert "no starting balance" in doc["failure_message"]
    lines = [r.getMessage() for r in caplog.records if "document failed" in r.getMessage()]
    assert len(lines) == 1
    assert (
        f"run_id={done['run_id']}" in lines[0] and f"document_id={doc['document_id']}" in lines[0]
    )
    assert "code=provider_error" in lines[0] and "no starting balance" in lines[0]
    assert FAKE_KEY not in lines[0] and "wellbore page" not in lines[0]  # no key, no document text
    assert m.provider.calls == []  # nothing was dispatched


def test_a_paused_period_still_blocks_with_a_clear_reason(
    migrated_url: URL, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    m = build_model(migrated_url, tmp_path, [answer()])
    ledger = fresh_period(m, "t074-paused", auto=True)
    app: Any = m.world.api.client.app
    period = ledger.ensure_period(
        "t074-paused",
        ledger_cap_usd=Decimal("150"),
        warn_usd=Decimal("100"),
        unattended_block_usd=Decimal("120"),
    )
    ledger.set_paused(period, True)
    assert app.state.processing is not None
    with caplog.at_level(logging.WARNING, logger="fieldlens.processing.runner"):
        done = run_one(m)
    doc = done["documents"][0]
    assert doc["state"] == "failed" and "paused" in doc["failure_message"]
    assert any("paused" in r.getMessage() for r in caplog.records)
    assert m.provider.calls == []


def test_failure_mapping_names_each_ledger_reason() -> None:
    for reason, needle in (
        ("starting balance is not confirmed", "no starting balance"),
        ("budget is paused", "paused"),
        ("pricing revision is not recorded", "pricing revision"),
    ):
        mapped = map_failure(ProviderUnavailable(reason))
        assert isinstance(mapped, FailureMapping)
        assert mapped.code is ProcessingFailureCode.PROVIDER_ERROR
        assert mapped.message.startswith("provider error: provider_unavailable: ")
        assert needle in mapped.message and len(mapped.message) <= 400

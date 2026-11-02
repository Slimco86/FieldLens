"""Composition of the processing package (provider, step, page counter, runner)."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.meta import MetaProvider
from fieldlens.assistant.provider import Pricing as ModelPricing
from fieldlens.assistant.runner import RequestLimits
from fieldlens.candidates.pages import PageRenderer
from fieldlens.config import Settings
from fieldlens.contracts.processing import ProcessingFailureCode
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.evidence.storage import BlobStore
from fieldlens.jobs.repository import new_owner
from fieldlens.processing.model_step import ModelClassificationStep, ModelStepConfig
from fieldlens.processing.runner import ProcessingRunner
from fieldlens.processing.service import PageCounter
from fieldlens.processing.steps import (
    DocumentTask,
    PageFailure,
    PageProvider,
    PageUsage,
    Pricing,
    ProcessingStep,
    StubProvider,
    StubStep,
)


@dataclass
class ProcessingRuntime:
    counter: PageCounter
    provider: PageProvider
    step: ProcessingStep
    runner: ProcessingRunner


def is_dead_owner(owner: str, own: str) -> bool:
    """Same-host owner whose process is gone; another owner id in this process counts as dead."""
    host, _, rest = owner.partition(":")
    pid_text = rest.split(":", 1)[0]
    if host != socket.gethostname() or not pid_text.isdigit():
        return False
    pid = int(pid_text)
    if pid == os.getpid():
        return owner != own
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError:
        return False
    return False


class PricingOnlyProvider:
    """Estimate-time identity of the live provider: name + owner rates. It never reads a page (the
    model step owns its own ledger-bound call), so it cannot spend."""

    def __init__(self, name: str, pricing: Pricing) -> None:
        self.name = name
        self.pricing = pricing

    def read_page(self, task: DocumentTask, page: int) -> PageUsage:
        raise PageFailure(ProcessingFailureCode.PROVIDER_ERROR, "pricing-only provider")


def _build_meta(
    factory: sessionmaker[Session], store: BlobStore, settings: Settings
) -> tuple[PageProvider, ProcessingStep]:
    """Live Meta step, refused unless the owner's key, rates and a per-run cap are configured.
    The budget balance is NOT confirmed here: that is an owner action on the ledger."""
    key = settings.meta_api_key
    in_rate = settings.processing_meta_input_usd_per_mtok
    out_rate = settings.processing_meta_output_usd_per_mtok
    if (
        key is None
        or not key.get_secret_value().strip()
        or in_rate is None
        or out_rate is None
        or settings.processing_run_cap_usd is None
    ):
        raise ValueError(
            "PROCESSING_PROVIDER=meta needs MODEL_API_KEY, both owner Meta rates "
            "(PROCESSING_META_INPUT/OUTPUT_USD_PER_MTOK) and PROCESSING_RUN_CAP_USD"
        )
    model_pricing = ModelPricing(
        revision=f"processing-{settings.meta_model}"[:64],
        model=settings.meta_model,
        input_usd_per_mtok=in_rate,
        output_usd_per_mtok=out_rate,
    ).validate()
    ledger = BudgetLedger(factory)
    period = ledger.ensure_period(
        settings.processing_live_period,
        ledger_cap_usd=settings.budget_ledger_cap_usd,
        warn_usd=settings.budget_warn_usd,
        unattended_block_usd=settings.budget_unattended_block_usd,
    )
    pricing_id = ledger.register_pricing(model_pricing, "owner-supplied processing rates")
    renderer = PageRenderer(store, concurrency=2)
    step = ModelClassificationStep(
        factory,
        ledger,
        MetaProvider(settings),
        ModelStepConfig(
            period_id=period,
            pricing_id=pricing_id,
            pricing=model_pricing,
            model=settings.meta_model,
            max_pages=settings.processing_model_pages,
            limits=RequestLimits(
                max_attempts=2,
                max_tool_calls=0,
                deadline_s=settings.provider_deadline_s,
                max_output_tokens=1200,
                max_reserved_usd=settings.provider_max_reserved_usd,
            ),
        ),
        renderer.page_text,
    )
    return PricingOnlyProvider("meta", Pricing("owner_meta_rates", in_rate, out_rate)), step


def build_runtime(
    factory: sessionmaker[Session],
    store: BlobStore,
    settings: Settings,
    *,
    provider: PageProvider | None = None,
    step: ProcessingStep | None = None,
) -> ProcessingRuntime:
    """Stub provider and stub step by default. ``meta`` is used only when explicitly configured
    (and fails closed when incomplete); an injected provider/step (tests) always wins."""
    counter = PageCounter(store)
    if provider is None and step is None and settings.processing_provider == "meta":
        chosen_provider, chosen_step = _build_meta(factory, store, settings)
    else:
        chosen_provider = provider or StubProvider(settings)
        chosen_step = step or StubStep()
    owner = new_owner()
    runner = ProcessingRunner(
        factory,
        counter,
        settings,
        chosen_provider,
        chosen_step,
        owner,
        lambda other: is_dead_owner(other, owner),
        StorageRootGuard(factory, store, lane=settings.lane),
    )
    return ProcessingRuntime(counter, chosen_provider, chosen_step, runner)

"""Composition of the processing package (provider, step, page counter, runner)."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.errors import ReservationStateError
from fieldlens.assistant.meta import MetaProvider
from fieldlens.assistant.provider import Pricing as ModelPricing
from fieldlens.assistant.runner import RequestLimits
from fieldlens.candidates.pages import PageRenderer
from fieldlens.config import Settings
from fieldlens.contracts.processing import (
    ProcessingFailureCode,
    ProcessingProvider,
    ProcessingProviderInfo,
    ProviderStatus,
)
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.evidence.storage import BlobStore
from fieldlens.jobs.repository import new_owner
from fieldlens.processing.model_step import ModelClassificationStep, ModelStepConfig
from fieldlens.processing.runner import ProcessingRunner
from fieldlens.processing.service import PageCounter
from fieldlens.processing.steps import (
    STUB_NOTICE,
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
class MetaContext:
    """What the live Meta step was built from, so other agent steps (reconstruction S2/S3) use the
    same provider, ledger period and owner-supplied rates instead of constructing their own."""

    ledger: BudgetLedger
    period_id: UUID
    pricing_id: UUID
    pricing: ModelPricing
    provider: MetaProvider
    renderer: PageRenderer
    rates: Pricing


@dataclass
class ProcessingRuntime:
    counter: PageCounter
    provider: PageProvider
    step: ProcessingStep
    runner: ProcessingRunner
    info: ProcessingProviderInfo
    model: str
    meta: MetaContext | None = None


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


def missing_meta_items(settings: Settings) -> list[str]:
    """Names (never values) of what the live provider still needs."""
    key = settings.meta_api_key
    missing: list[str] = []
    if key is None or not key.get_secret_value().strip():
        missing.append("MODEL_API_KEY")
    if settings.processing_meta_input_usd_per_mtok is None:
        missing.append("FIELDLENS_PROCESSING_META_INPUT_USD_PER_MTOK")
    if settings.processing_meta_output_usd_per_mtok is None:
        missing.append("FIELDLENS_PROCESSING_META_OUTPUT_USD_PER_MTOK")
    return missing


def _info(
    settings: Settings, active: str, model: str, missing: list[str] | None = None
) -> ProcessingProviderInfo:
    requested = ProcessingProvider(settings.processing_provider)
    if missing:
        return ProcessingProviderInfo(
            requested=requested,
            active=ProcessingProvider.STUB,
            model=model,
            status=ProviderStatus.PROVIDER_MISCONFIGURED,
            missing=missing,
            spends_money=False,
            message=(
                "FIELDLENS_PROCESSING_PROVIDER=meta is set but incomplete (missing: "
                + ", ".join(missing)
                + "); processing is refused until it is complete."
            ),
        )
    live = active != ProcessingProvider.STUB.value
    return ProcessingProviderInfo(
        requested=requested,
        active=ProcessingProvider(active),
        model=model,
        status=ProviderStatus.LIVE if live else ProviderStatus.STUB,
        spends_money=live,
        message=f"Live provider active: model {model}." if live else STUB_NOTICE,
    )


AUTO_BALANCE_SOURCE = "auto: processing-live, per-run user confirmation"


def _ensure_usable_balance(ledger: BudgetLedger, period: UUID, settings: Settings) -> None:
    """The live processing period needs no owner step: every run is authorised by the user's
    confirmation of its estimate, so the starting balance is the ledger cap (accounting only; the
    spend ceilings stay). Done once, also for an existing period whose balance is still unset.
    A balance that is already confirmed (by anyone) is never changed. Only this period."""
    try:
        ledger.confirm_balance(period, settings.budget_ledger_cap_usd, AUTO_BALANCE_SOURCE)
    except ReservationStateError:
        pass  # already confirmed


def _build_meta(
    factory: sessionmaker[Session], store: BlobStore, settings: Settings
) -> tuple[PageProvider, ProcessingStep, MetaContext]:
    """Live Meta step; the caller has checked :func:`missing_meta_items`.
    The period's balance is made usable here (see :func:`_ensure_usable_balance`)."""
    in_rate = settings.processing_meta_input_usd_per_mtok
    out_rate = settings.processing_meta_output_usd_per_mtok
    assert in_rate is not None and out_rate is not None
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
    _ensure_usable_balance(ledger, period, settings)
    pricing_id = ledger.register_pricing(model_pricing, "owner-supplied processing rates")
    renderer = PageRenderer(store, concurrency=2)
    meta_provider = MetaProvider(settings)
    step = ModelClassificationStep(
        factory,
        ledger,
        meta_provider,
        ModelStepConfig(
            period_id=period,
            pricing_id=pricing_id,
            pricing=model_pricing,
            model=settings.meta_model,
            pages_per_call=settings.processing_pages_per_call,
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
    rates = Pricing("owner_meta_rates", in_rate, out_rate)
    context = MetaContext(ledger, period, pricing_id, model_pricing, meta_provider, renderer, rates)
    return PricingOnlyProvider("meta", rates), step, context


def build_runtime(
    factory: sessionmaker[Session],
    store: BlobStore,
    settings: Settings,
    *,
    provider: PageProvider | None = None,
    step: ProcessingStep | None = None,
) -> ProcessingRuntime:
    """Stub provider and stub step by default. ``meta`` is used only when explicitly configured
    and complete. An incomplete ``meta`` configuration does not stop the app: it runs on the stub
    with ``info.status == provider_misconfigured`` (naming what is missing) and the routes refuse
    estimate/confirm/retry. An injected provider/step (tests) always wins."""
    counter = PageCounter(store)
    missing: list[str] = []
    meta: MetaContext | None = None
    if provider is None and step is None and settings.processing_provider == "meta":
        missing = missing_meta_items(settings)
        if not missing:
            chosen_provider, chosen_step, meta = _build_meta(factory, store, settings)
        else:
            chosen_provider, chosen_step = StubProvider(settings), StubStep()
    else:
        chosen_provider = provider or StubProvider(settings)
        chosen_step = step or StubStep()
    model = str(getattr(chosen_step, "model_name", None) or chosen_provider.name)
    info = _info(settings, chosen_provider.name, model, missing)
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
    return ProcessingRuntime(counter, chosen_provider, chosen_step, runner, info, model, meta)

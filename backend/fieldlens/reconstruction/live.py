"""Live S2 reader and S3 proposer for the real app (TASK-076 D2).

Both reuse the model-processing runtime's provider, ledger period and owner-supplied rates (the
:class:`~fieldlens.processing.runtime.MetaContext`): no second provider is constructed. They exist
only when that runtime is live (``FIELDLENS_PROCESSING_PROVIDER=meta`` with a complete
configuration); otherwise nothing is built, S2/S3 report *Not available: no model configured* and
no call is possible. A user-confirmed run is the authorization; the estimate is informational."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from fieldlens.candidates.sources import SourceReader
from fieldlens.config import Settings
from fieldlens.evidence.storage import BlobStore
from fieldlens.merge_proposals.evidence import ReaderSourceText
from fieldlens.merge_proposals.proposer import MergeProposer, ProposerConfig
from fieldlens.processing.runtime import ProcessingRuntime
from fieldlens.reconstruction.reading import DocumentReader, ProcessingStepReader


def build_live_agents(
    processing: ProcessingRuntime | None,
    factory: sessionmaker[Session],
    store: BlobStore,
    settings: Settings,
) -> tuple[DocumentReader | None, MergeProposer | None]:
    meta = processing.meta if processing is not None else None
    if processing is None or meta is None:
        return None, None
    per_page = meta.rates.cost(
        settings.processing_input_tokens_per_page, settings.processing_output_tokens_per_page
    )
    reader = ProcessingStepReader(
        factory,
        settings,
        processing.step,
        processing.provider,
        processing.counter.count,
        per_page * settings.processing_model_pages,
    )
    proposer = MergeProposer(
        factory,
        meta.ledger,
        meta.provider,
        ProposerConfig(
            period_id=meta.period_id,
            pricing_id=meta.pricing_id,
            pricing=meta.pricing,
            model=settings.meta_model,
        ),
        ReaderSourceText(factory, SourceReader(factory, store, meta.renderer)),
    )
    return reader, proposer

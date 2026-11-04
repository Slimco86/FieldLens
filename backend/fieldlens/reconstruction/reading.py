"""S2 *Read documents*: the TASK-055 model read through the StageExecutor seam (TASK-076).

Scope: PDFs of the project's latest source revision that are stored, have no native parser and have
no stored model result at the current prompt/schema version. A stored result is **reused**, never
read again silently (a forced re-read stays a processing action). Nothing here calls a model unless
the reader is live; on the stub provider the stage reports ``stubbed`` and spends nothing.

The live reader drives the existing :class:`~fieldlens.processing.model_step.ModelClassificationStep`
for one document at a time inside a small, terminal ``processing_run`` row (the stored result's
foreign key), so the stored result, identity proposals and cache are exactly TASK-055's.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings
from fieldlens.contracts.imports import ExtractionState
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope
from fieldlens.processing import tables as pt
from fieldlens.processing.document_text import FAMILIES as TEXT_FAMILIES
from fieldlens.processing.identity_read import PROMPT_VERSION, SCHEMA_VERSION
from fieldlens.processing.steps import (
    DocumentTask,
    PageFailure,
    PageProvider,
    PageUsage,
    ProcessingStep,
    RunStop,
    quantize,
)

log = logging.getLogger(__name__)
pr, prd, dmr = pt.processing_run, pt.processing_run_document, pt.document_model_result
ZERO = Decimal("0")


@dataclass(frozen=True)
class ReadTarget:
    document_id: UUID
    filename: str
    storage_key: str
    source_revision_id: UUID
    labels: tuple[str, ...]
    format_family: str = "pdf"
    sha256: str = ""
    text_encoding: str | None = None


@dataclass(frozen=True)
class ReadScope:
    to_read: list[ReadTarget]
    reused: int


@dataclass(frozen=True)
class ReadOutcome:
    usd: Decimal = ZERO
    pages: int = 0


class ReadFailure(Exception):
    """A typed provider/document failure; ``code`` is stable and secret-free."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class DocumentReader(Protocol):
    name: str

    @property
    def live(self) -> bool:
        """False: nothing is read (stub provider)."""
        ...

    @property
    def usd_per_document(self) -> Decimal:
        """Informational planning figure for one document."""
        ...

    def read(
        self, project_id: UUID, target: ReadTarget, checkpoint: Callable[[], None]
    ) -> ReadOutcome:
        """Read and store one document; raises :class:`ReadFailure` or the checkpoint's stop."""
        ...


def read_scope(session: Session, project_id: UUID) -> ReadScope:
    latest = session.execute(
        select(m.project.c.latest_source_revision_id).where(m.project.c.project_id == project_id)
    ).scalar()
    if latest is None:
        return ReadScope([], 0)
    sd, dp, dc, srd = (
        m.source_document,
        m.document_processing,
        m.document_classification,
        m.source_revision_document,
    )
    rows = session.execute(
        select(
            sd.c.document_id,
            sd.c.original_filename,
            sd.c.storage_key,
            sd.c.format_family,
            sd.c.sha256,
            sd.c.origin_metadata,
            dp.c.storage_state,
            dp.c.extraction_state,
            dc.c.user_categories,
        )
        .select_from(
            srd.join(
                sd,
                (sd.c.project_id == srd.c.project_id) & (sd.c.document_id == srd.c.document_id),
            )
            .outerjoin(
                dp, (dp.c.project_id == sd.c.project_id) & (dp.c.document_id == sd.c.document_id)
            )
            .outerjoin(
                dc, (dc.c.project_id == sd.c.project_id) & (dc.c.document_id == sd.c.document_id)
            )
        )
        .where(srd.c.project_id == project_id, srd.c.source_revision_id == latest)
        .order_by(sd.c.original_filename, sd.c.document_id)
    ).all()
    done = {
        r.document_id
        for r in session.execute(
            select(dmr.c.document_id)
            .where(
                dmr.c.project_id == project_id,
                dmr.c.prompt_version == PROMPT_VERSION,
                dmr.c.schema_version == SCHEMA_VERSION,
            )
            .distinct()
        )
    }
    todo: list[ReadTarget] = []
    reused = 0
    for r in rows:
        if (
            (r.format_family != "pdf" and r.format_family not in TEXT_FAMILIES)
            or r.storage_state != "stored"
            or r.extraction_state != ExtractionState.UNSUPPORTED.value
        ):
            continue
        if r.document_id in done:
            reused += 1
            continue
        todo.append(
            ReadTarget(
                r.document_id,
                r.original_filename,
                r.storage_key,
                latest,
                tuple(r.user_categories or ()),
                r.format_family,
                r.sha256,
                (r.origin_metadata or {}).get("text_encoding"),
            )
        )
    return ReadScope(todo, reused)


class ProcessingStepReader:
    """Live reader over a TASK-055 ``ProcessingStep`` (the model step); stub provider -> not live."""

    def __init__(
        self,
        factory: sessionmaker[Session],
        settings: Settings,
        step: ProcessingStep,
        provider: PageProvider,
        page_count: Callable[..., int],
        per_document_usd: Decimal,
    ) -> None:
        self._factory = factory
        self._settings = settings
        self._step = step
        self._provider = provider
        self._count = page_count
        self._usd = per_document_usd
        self.name = provider.name

    @property
    def live(self) -> bool:
        return self._provider.name != "stub"

    @property
    def usd_per_document(self) -> Decimal:
        return self._usd

    def read(
        self, project_id: UUID, target: ReadTarget, checkpoint: Callable[[], None]
    ) -> ReadOutcome:
        try:
            if target.format_family == "pdf":
                pages = self._count(target.storage_key)
            else:
                pages = self._count(target.storage_key, target.format_family, target.text_encoding)
        except Exception as exc:
            raise ReadFailure(
                "document_unavailable", "the stored document could not be read"
            ) from exc
        if pages <= 0:
            raise ReadFailure("document_unavailable", "the document has no pages")
        window = min(
            pages, self._step.max_pages_per_document or pages, self._settings.processing_model_pages
        )
        run_id = self._open_run(project_id, target, pages, window)
        task = DocumentTask(
            project_id, run_id, target.document_id, target.source_revision_id,
            target.storage_key, pages, 1, window, target.labels,
            target.format_family, target.sha256, target.text_encoding,
        )  # fmt: skip
        spent = ZERO
        done = 0

        def page_checkpoint(page: int, usage: PageUsage) -> None:
            nonlocal spent, done
            spent += usage.cost_usd
            done += 1
            checkpoint()

        failure: ReadFailure | None = None
        stop: BaseException | None = None
        try:
            self._step.run_document(task, self._provider, page_checkpoint)
        except PageFailure as exc:
            failure = ReadFailure(f"read_{exc.code.value}", exc.message)
        except RunStop as exc:
            failure = ReadFailure(f"read_{exc.code.value}", exc.message)
        except BaseException as exc:  # the cancel StageStop from the checkpoint, or a crash
            stop = exc
        self._close_run(
            run_id,
            target.document_id,
            spent,
            done,
            window,
            failure is None and stop is None,
            failure,
        )
        if stop is not None:
            raise stop
        if failure is not None:
            raise failure
        return ReadOutcome(quantize(spent), window)

    def _open_run(self, project_id: UUID, target: ReadTarget, pages: int, window: int) -> UUID:
        fingerprint = hashlib.sha256(f"reconstruction-s2:{target.document_id}".encode()).hexdigest()
        try:
            with session_scope(self._factory) as s:
                run_id: UUID = s.execute(
                    insert(pr)
                    .values(
                        project_id=project_id,
                        status="running",
                        step=getattr(self._step, "name", "model_classification")[:32],
                        provider="meta" if self.live else "stub",
                        route="model",
                        request_fingerprint=fingerprint,
                        estimated_pages=window,
                        estimated_input_tokens=0,
                        estimated_output_tokens=0,
                        estimated_usd=self._usd,
                        pricing_source="reconstruction_s2",
                        total_cap_usd=ZERO,
                        remaining_budget_usd=ZERO,
                        confirmed_usd=self._usd,
                        model=str(getattr(self._step, "model_name", ""))[:64] or None,
                        started_at=func.now(),
                    )
                    .returning(pr.c.run_id)
                ).scalar_one()
                s.execute(
                    insert(prd).values(
                        run_id=run_id,
                        document_id=target.document_id,
                        project_id=project_id,
                        source_revision_id=target.source_revision_id,
                        ordinal=0,
                        state="running",
                        page_count=pages,
                        page_start=1,
                        page_end=window,
                        label_hints=list(target.labels),
                        estimated_usd=self._usd,
                    )
                )
            return run_id
        except IntegrityError as exc:  # the document is already in an active processing run
            raise ReadFailure("document_busy", "the document is being processed elsewhere") from exc

    def _close_run(
        self,
        run_id: UUID,
        document_id: UUID,
        spent: Decimal,
        done: int,
        window: int,
        ok: bool,
        failure: ReadFailure | None,
    ) -> None:
        with session_scope(self._factory) as s:
            s.execute(
                update(prd)
                .where(prd.c.run_id == run_id, prd.c.document_id == document_id)
                .values(
                    state="processed" if ok else "failed",
                    pages_done=window if ok else min(done, window),
                    actual_usd=quantize(spent),
                    failure_code=None if ok else (failure.code if failure else "cancelled")[:40],
                    retryable=not ok,
                    finished_at=func.now(),
                )
            )
            s.execute(
                update(pr)
                .where(pr.c.run_id == run_id)
                .values(
                    status="succeeded" if ok else ("failed" if failure else "cancelled"),
                    actual_usd=quantize(spent),
                    error_code=None if ok else (failure.code if failure else "cancelled")[:40],
                    finished_at=func.now(),
                )
            )

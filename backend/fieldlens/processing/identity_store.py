"""Persistence of the document-identity model step: cache lookup, one-transaction store, read model.

* The cache key is (project, document, page window, prompt version, schema version): a document
  is immutable content, so the document id *is* its revision; the window is part of the input.
* A result and all of its identity proposals are written in ONE transaction after validation, so a
  failed call never leaves partial rows.
* Proposals link to an existing wellbore only on exact equality of the normalized key with
  ``wellbore.wellbore_key``; the link is resolved when read, so it can never go stale.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fieldlens.contracts.imports import DocumentCategory
from fieldlens.contracts.processing import (
    MODEL_REPLY_MAX_BYTES,
    DocumentIdentityProposal,
    DocumentModelOutcome,
    DocumentModelRead,
    IdentityResolution,
    IdentitySubjectKind,
    ModelReadWarning,
    ModelReplyRaw,
    ModelRunEntry,
    ProcessingDocumentState,
    ProcessingFailureCode,
    ProcessingPageRange,
    ProcessingProvider,
)
from fieldlens.persistence import models as m
from fieldlens.processing import tables as t
from fieldlens.processing.identity_read import (
    FALLBACK_CATEGORY,
    PROMPT_VERSION,
    SCHEMA_VERSION,
    UNCLASSIFIED_TAG,
    ModelOutcome,
)
from fieldlens.processing.steps import STUB_NOTICE

dmr, dip = t.document_model_result, t.document_identity_proposal
CLASSIFICATION_METHOD = "model_classification"
MAX_TAGS_PER_DOCUMENT = 20


@dataclass(frozen=True)
class CachedResult:
    result_id: UUID
    pages_read: int


def find_cached(
    session: Session, project_id: UUID, document_id: UUID, page_start: int, page_end: int
) -> CachedResult | None:
    row = session.execute(
        select(dmr.c.result_id, dmr.c.pages_read)
        .where(
            dmr.c.project_id == project_id,
            dmr.c.document_id == document_id,
            dmr.c.page_start == page_start,
            dmr.c.page_end == page_end,
            dmr.c.prompt_version == PROMPT_VERSION,
            dmr.c.schema_version == SCHEMA_VERSION,
        )
        .order_by(dmr.c.created_at.desc(), dmr.c.result_id.desc())
        .limit(1)
    ).first()
    return CachedResult(row.result_id, row.pages_read) if row else None


def bound_reply(text: str | None) -> tuple[str | None, bool]:
    """Raw reply as stored: NULs removed (PostgreSQL text cannot hold them), at most
    ``MODEL_REPLY_MAX_BYTES`` of UTF-8 cut on a character boundary. -> (text, truncated)."""
    if text is None:
        return None, False
    clean = text.replace("\x00", "")
    data = clean.encode("utf-8")
    if len(data) <= MODEL_REPLY_MAX_BYTES:
        return clean, False
    return data[:MODEL_REPLY_MAX_BYTES].decode("utf-8", errors="ignore"), True


def store_result(
    session: Session,
    *,
    project_id: UUID,
    document_id: UUID,
    source_revision_id: UUID,
    run_id: UUID,
    page_start: int,
    page_end: int,
    provider: str,
    model_revision: str,
    outcome: ModelOutcome,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: Decimal,
    raw_reply: str | None = None,
) -> None:
    """Insert a NEW result + proposals and update the suggested classification. Earlier results of
    the document stay as history; the latest by time is the current read. (A document sits in at
    most one active run, so two writers of the same key cannot race.)"""
    window = page_end - page_start + 1
    reply, truncated = bound_reply(raw_reply)
    result_id: UUID = session.execute(
        pg_insert(dmr)
        .values(
            project_id=project_id,
            document_id=document_id,
            source_revision_id=source_revision_id,
            run_id=run_id,
            page_start=page_start,
            page_end=page_end,
            pages_read=window,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            extraction_method=CLASSIFICATION_METHOD,
            provider=provider,
            model_revision=model_revision,
            category=outcome.category,
            unclassified=outcome.unclassified,
            tags=outcome.tags,
            warnings=outcome.warnings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            raw_reply=reply,
            raw_reply_truncated=truncated,
        )
        .returning(dmr.c.result_id)
    ).scalar_one()
    for ordinal, ident in enumerate(outcome.identities):
        session.execute(
            pg_insert(dip).values(
                project_id=project_id,
                result_id=result_id,
                document_id=document_id,
                run_id=run_id,
                ordinal=ordinal,
                subject_kind=ident.subject_kind,
                name_as_written=ident.name_as_written,
                normalized_key=ident.normalized_key,
                page=ident.page,
                quote=ident.quote,
                extraction_method=CLASSIFICATION_METHOD,
                provider=provider,
                model_revision=model_revision,
                prompt_version=PROMPT_VERSION,
                schema_version=SCHEMA_VERSION,
            )
        )
    _suggest_classification(session, project_id, document_id, outcome, result_id)


def _suggest_classification(
    session: Session,
    project_id: UUID,
    document_id: UUID,
    outcome: ModelOutcome,
    result_id: UUID,
) -> None:
    """Model category -> ``suggested_categories`` and tags. ``user_categories`` and its origin are
    never touched, so a user's label always wins; no classification event is written."""
    dc = m.document_classification
    existing = session.execute(
        select(dc.c.tags, dc.c.suggested_categories, dc.c.user_categories)
        .where(dc.c.project_id == project_id, dc.c.document_id == document_id)
        .with_for_update()
    ).one_or_none()
    if existing is None:
        return
    tags_now, suggested_now, user_now = (list(x or []) for x in existing)
    has_category = bool(user_now or [c for c in suggested_now if c != FALLBACK_CATEGORY])
    suggestions = list(suggested_now)
    if not outcome.unclassified:
        # replace what earlier model results of this document suggested (readable from the
        # stored results); native/user-origin suggestions stay
        earlier = set(
            session.execute(
                select(dmr.c.category).where(
                    dmr.c.project_id == project_id,
                    dmr.c.document_id == document_id,
                    dmr.c.result_id != result_id,
                )
            )
            .scalars()
            .all()
        )
        suggestions = [c for c in suggestions if c not in earlier]
        if outcome.category not in suggestions:
            suggestions.append(outcome.category)
    elif not has_category and outcome.category not in suggestions:
        suggestions.append(outcome.category)
    merged = list(tags_now)
    if not outcome.unclassified or has_category:
        # a category exists (now or from before): a stale fallback tag goes, none is added
        merged = [t for t in merged if t != UNCLASSIFIED_TAG]
    for tag in outcome.tags:
        if tag == UNCLASSIFIED_TAG and has_category:
            continue
        if tag not in merged and len(merged) < MAX_TAGS_PER_DOCUMENT:
            merged.append(tag)
    session.execute(
        update(dc)
        .where(dc.c.project_id == project_id, dc.c.document_id == document_id)
        .values(
            suggested_categories=suggestions,
            tags=merged,
            classification_method=CLASSIFICATION_METHOD,
            classification_version=PROMPT_VERSION,
            updated_at=func.clock_timestamp(),
        )
    )


def load_model_reads(
    session: Session, project_id: UUID, document_ids: Sequence[UUID]
) -> dict[UUID, DocumentModelRead]:
    """Latest stored model result per document, with proposals linked at read time."""
    if not document_ids:
        return {}
    rows = session.execute(
        select(dmr)
        .where(dmr.c.project_id == project_id, dmr.c.document_id.in_(list(document_ids)))
        .order_by(dmr.c.created_at.asc(), dmr.c.result_id.asc())
    ).all()
    latest: dict[UUID, Any] = {r.document_id: r for r in rows}  # newest wins
    if not latest:
        return {}
    result_ids = [r.result_id for r in latest.values()]
    wb = m.wellbore
    proposals = session.execute(
        select(dip, wb.c.wellbore_id.label("linked_id"), wb.c.wellbore_key.label("linked_key"))
        .select_from(
            dip.outerjoin(
                wb,
                (wb.c.project_id == dip.c.project_id) & (wb.c.wellbore_key == dip.c.normalized_key),
            )
        )
        .where(dip.c.project_id == project_id, dip.c.result_id.in_(result_ids))
        .order_by(dip.c.result_id, dip.c.ordinal)
    ).all()
    by_result: dict[UUID, list[DocumentIdentityProposal]] = {}
    for p in proposals:
        linked = p.linked_id is not None and p.normalized_key is not None
        by_result.setdefault(p.result_id, []).append(
            DocumentIdentityProposal(
                proposal_id=p.proposal_id,
                subject_kind=IdentitySubjectKind(p.subject_kind),
                name_as_written=p.name_as_written,
                normalized_key=p.normalized_key,
                page=p.page,
                quote=p.quote,
                resolution=IdentityResolution.LINKED if linked else IdentityResolution.UNRESOLVED,
                wellbore_id=p.linked_id if linked else None,
                wellbore_key=p.linked_key if linked else None,
            )
        )
    return {
        doc_id: DocumentModelRead(
            document_id=doc_id,
            run_id=r.run_id,
            category=DocumentCategory(r.category),
            unclassified=r.unclassified,
            tags=list(r.tags),
            identities=by_result.get(r.result_id, []),
            warnings=[ModelReadWarning(**w) for w in r.warnings],
            pages=ProcessingPageRange(page_start=r.page_start, page_end=r.page_end),
            pages_read=r.pages_read,
            provider=ProcessingProvider(r.provider),
            model_revision=r.model_revision,
            prompt_version=r.prompt_version,
            schema_version=r.schema_version,
            created_at=r.created_at,
        )
        for doc_id, r in latest.items()
    }


OUTCOME_RUN_LIMIT = 50


def load_outcome(session: Session, project_id: UUID, document_id: UUID) -> DocumentModelOutcome:
    """Run history (newest first) and the current stored read of one document, project-scoped.
    Failure messages and the raw reply are stored data; nothing here interprets them."""
    pr, prd = t.processing_run, t.processing_run_document
    rows = session.execute(
        select(
            prd,
            pr.c.provider,
            pr.c.model,
            pr.c.force_refresh,
            pr.c.created_at,
            pr.c.started_at,
            dmr.c.input_tokens,
            dmr.c.output_tokens,
            dmr.c.warnings.label("result_warnings"),
        )
        .select_from(
            prd.join(
                pr, (pr.c.project_id == prd.c.project_id) & (pr.c.run_id == prd.c.run_id)
            ).outerjoin(
                dmr,
                (dmr.c.project_id == prd.c.project_id)
                & (dmr.c.run_id == prd.c.run_id)
                & (dmr.c.document_id == prd.c.document_id),
            )
        )
        .where(
            prd.c.project_id == project_id,
            prd.c.document_id == document_id,
            prd.c.state != "estimated",  # an estimate nobody confirmed is not a run
            ~((prd.c.state == "cancelled") & pr.c.started_at.is_(None)),  # never started
        )
        .order_by(pr.c.created_at.desc(), pr.c.run_id.desc())
        .limit(OUTCOME_RUN_LIMIT)
    ).all()
    runs = [
        ModelRunEntry(
            run_id=r.run_id,
            state=ProcessingDocumentState(r.state),
            provider=ProcessingProvider(r.provider),
            model=r.model,
            forced=r.force_refresh,
            created_at=r.created_at,
            started_at=r.started_at,
            finished_at=r.finished_at,
            pages=ProcessingPageRange(page_start=r.page_start, page_end=r.page_end),
            pages_read=r.pages_done,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            usd_actual=r.actual_usd,
            cache_hit=r.cache_hit,
            failure_code=ProcessingFailureCode(r.failure_code) if r.failure_code else None,
            failure_message=r.failure_message,
            warnings=[ModelReadWarning(**w) for w in (r.result_warnings or [])],
            message=STUB_NOTICE if r.provider == ProcessingProvider.STUB.value else None,
        )
        for r in rows
    ]
    current = load_model_reads(session, project_id, [document_id]).get(document_id)
    raw: ModelReplyRaw | None = None
    if current is not None:
        latest = session.execute(
            select(dmr.c.raw_reply, dmr.c.raw_reply_truncated)
            .where(dmr.c.project_id == project_id, dmr.c.document_id == document_id)
            .order_by(dmr.c.created_at.desc(), dmr.c.result_id.desc())
            .limit(1)
        ).one()
        if latest.raw_reply is not None:
            raw = ModelReplyRaw(text=latest.raw_reply, truncated=latest.raw_reply_truncated)
    return DocumentModelOutcome(document_id=document_id, runs=runs, current=current, raw_reply=raw)

"""Source-inspection extraction routes (read report/records; idempotent re-queue)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.context import PageParams
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.extraction import (
    ExtractedRecordPage,
    ExtractionReport,
    ExtractionRequeue,
    RequeueOutcome,
)
from fieldlens.contracts.imports import StorageRetryResult, StorageState
from fieldlens.evidence.integrity import (
    REUPLOAD_MESSAGE,
    RootMismatch,
    reverify_document,
    root_mismatch_error,
)
from fieldlens.evidence.root_guard import StorageRootGuard
from fieldlens.evidence.storage import BlobStore, VerifyOutcome
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from . import views
from .heal import queue_extraction_after_restore
from .runner import requeue_document


class RecordQuery(PageParams):
    kind: str | None = Field(default=None, max_length=48)


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _db(request: Request, fn: Any) -> Any:
    factory = request.app.state.session_factory
    if factory is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    try:
        with session_scope(factory) as session:
            return fn(session)
    except OperationalError as exc:
        raise ContractError(
            ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503
        ) from exc


def build_extraction_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/documents/{document_id}/extraction",
        tags=["extraction"],
        responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
        dependencies=[Depends(_no_store)],
    )

    @router.get("", response_model=ExtractionReport)
    def get_report(project_id: UUID, document_id: UUID, request: Request) -> ExtractionReport:
        out: ExtractionReport = _db(request, lambda s: views.report(s, project_id, document_id))
        return out

    @router.get("/records", response_model=ExtractedRecordPage)
    def get_records(
        project_id: UUID,
        document_id: UUID,
        request: Request,
        params: Annotated[RecordQuery, Query()],
    ) -> ExtractedRecordPage:
        page: ExtractedRecordPage = _db(
            request,
            lambda s: views.records(
                s, project_id, document_id, params.kind, params.limit, params.cursor
            ),
        )
        return page

    @router.post(
        "",
        response_model=ExtractionRequeue,
        dependencies=[Depends(_guard_mutation)],
    )
    def requeue(
        project_id: UUID,
        document_id: UUID,
        request: Request,
        retry: Annotated[
            bool, Query(description="Explicit retry of a failed/unsupported run")
        ] = False,
    ) -> ExtractionRequeue:
        store: BlobStore = request.app.state.blob_store
        guard: StorageRootGuard = _guard(request)
        unreadable: list[str] = []

        def work(session: Any) -> ExtractionRequeue:
            views.require_document(session, project_id, document_id)
            if retry or _storage_state(session, project_id, document_id) != "stored":
                reason = _reverify_original(session, store, guard, project_id, document_id)
                if reason is not None:
                    unreadable.append(reason)
                    return ExtractionRequeue(
                        outcome=RequeueOutcome.UNCHANGED,
                        report=views.report(session, project_id, document_id),
                    )
            queued = requeue_document(session, project_id, document_id, retry=retry)
            session.flush()
            return ExtractionRequeue(
                outcome=RequeueOutcome.QUEUED if queued else RequeueOutcome.UNCHANGED,
                report=views.report(session, project_id, document_id),
            )

        out: ExtractionRequeue = _db(request, work)  # commits the corrected storage state
        if unreadable:
            raise ContractError(
                ErrorCode.CONFLICT,
                "The stored original of this file is not readable "
                f"({unreadable[0]}); re-upload this file to extract it again.",
                409,
                {"reason": "source_unreadable", "check": unreadable[0], "recovery": "re-upload"},
            )
        return out

    return router


def _storage_state(session: Any, project_id: UUID, document_id: UUID) -> str | None:
    state = session.execute(
        select(m.document_processing.c.storage_state).where(
            m.document_processing.c.project_id == project_id,
            m.document_processing.c.document_id == document_id,
        )
    ).scalar_one_or_none()
    return None if state is None else str(state)


def _guard(request: Request) -> StorageRootGuard:
    guard: StorageRootGuard | None = request.app.state.root_guard
    if guard is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    return guard


def _reverify_original(
    session: Any, store: BlobStore, guard: StorageRootGuard, project_id: UUID, document_id: UUID
) -> str | None:
    """Re-read the stored original (under the verified storage root only) and make the storage
    state match reality: restore ``stored`` when the bytes verify again, otherwise record
    ``failed``. Returns the failed check (e.g. ``missing``) or None when the bytes verify."""
    try:
        result = reverify_document(session, store, guard, project_id, document_id)
    except RootMismatch as exc:
        raise root_mismatch_error() from exc
    return None if result.outcome is VerifyOutcome.OK else result.outcome.value


def build_storage_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/documents/{document_id}/storage",
        tags=["storage"],
        responses={
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        dependencies=[Depends(_no_store)],
    )

    @router.post(
        "/retry", response_model=StorageRetryResult, dependencies=[Depends(_guard_mutation)]
    )
    def retry_storage(project_id: UUID, document_id: UUID, request: Request) -> StorageRetryResult:
        """Retry a Failed (or re-check a Stored) document: re-verify its bytes; when they verify
        the document is Stored and extraction is queued, otherwise 409 says to re-upload."""
        store: BlobStore = request.app.state.blob_store
        guard = _guard(request)
        unreadable: list[str] = []

        def work(session: Any) -> StorageRetryResult | None:
            views.require_document(session, project_id, document_id)
            before = _storage_state(session, project_id, document_id)
            if before == "pending_verification":
                raise ContractError(
                    ErrorCode.CONFLICT,
                    "This file is still being verified; try again in a moment.",
                    409,
                    {"reason": "verification_pending"},
                )
            try:
                result = reverify_document(
                    session,
                    store,
                    guard,
                    project_id,
                    document_id,
                    write_failure=before != "failed",
                )
            except RootMismatch as exc:
                raise root_mismatch_error() from exc
            if result.outcome is not VerifyOutcome.OK:
                unreadable.append(result.outcome.value)
                return None
            queued = queue_extraction_after_restore(session, project_id, document_id)
            return StorageRetryResult(
                document_id=document_id,
                outcome="restored" if before == "failed" else "already_stored",
                storage_state=StorageState.STORED,
                extraction_queued=queued,
                message="Stored: the stored copy verified."
                + (" Extraction is queued." if queued else ""),
            )

        out: StorageRetryResult | None = _db(request, work)
        if out is None:
            raise ContractError(
                ErrorCode.CONFLICT,
                REUPLOAD_MESSAGE,
                409,
                {
                    "reason": "stored_copy_unreadable",
                    "check": unreadable[0],
                    "recovery": "re-upload",
                },
            )
        return out

    return router

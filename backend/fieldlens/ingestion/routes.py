"""Project-scoped import, source-list and classification routes."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError

from fieldlens import security
from fieldlens.contracts.context import PageParams
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.contracts.imports import (
    ClassificationUpdate,
    DocumentPage,
    ImportAccepted,
    SourceDocumentItem,
    SourceRevisionPage,
)
from fieldlens.evidence.storage import BlobStore, blob_key
from fieldlens.persistence.session import session_scope

from . import repository
from .upload import UploadLimits, check_content_length, receive_upload

_ERRORS: dict[int | str, dict[str, Any]] = {
    403: {"model": ErrorEnvelope},
    404: {"model": ErrorEnvelope},
    409: {"model": ErrorEnvelope},
    413: {"model": ErrorEnvelope},
    415: {"model": ErrorEnvelope},
    422: {"model": ErrorEnvelope},
    503: {"model": ErrorEnvelope},
}

_MULTIPART_BODY: dict[str, Any] = {
    "required": True,
    "content": {
        "multipart/form-data": {
            "schema": {
                "type": "object",
                "required": ["metadata", "files"],
                "properties": {
                    "metadata": {
                        "$ref": "#/components/schemas/ImportMetadata",
                        "description": "JSON; must be the first part.",
                    },
                    "files": {
                        "type": "array",
                        "items": {"type": "string", "format": "binary"},
                        "description": "n-th file aligns with metadata.files[n].",
                    },
                },
            }
        }
    },
}


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _unavailable() -> ContractError:
    return ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)


def _factory(request: Request) -> Any:
    factory = request.app.state.session_factory
    if factory is None:
        raise _unavailable()
    return factory


def _limits(request: Request) -> UploadLimits:
    s = request.app.state.settings
    return UploadLimits(
        s.upload_max_file_bytes,
        s.upload_max_batch_bytes,
        s.upload_max_files,
        s.upload_max_overhead_bytes,
    )


def _db(request: Request, fn: Any) -> Any:
    factory = _factory(request)
    try:
        with session_scope(factory) as session:
            return fn(session)
    except OperationalError as exc:
        raise _unavailable() from exc


def build_ingestion_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}",
        tags=["imports"],
        responses=_ERRORS,
        dependencies=[Depends(_no_store)],
    )

    @router.post(
        "/imports",
        status_code=202,
        response_model=ImportAccepted,
        dependencies=[Depends(_guard_mutation)],
        openapi_extra={"requestBody": _MULTIPART_BODY},
    )
    async def create_import(project_id: UUID, request: Request) -> Response:
        await run_in_threadpool(_db, request, lambda s: repository.project_latest(s, project_id))
        limits = _limits(request)
        check_content_length(request.headers.get("content-length"), limits)
        store: BlobStore = request.app.state.blob_store
        staging = await run_in_threadpool(store.new_staging_dir, uuid4())
        try:
            received = await receive_upload(
                request.stream(), request.headers.get("content-type"), staging, limits
            )

            def commit() -> ImportAccepted:
                for staged in received.files:  # immutable originals first; DB decides visibility
                    store.publish(staged.path, blob_key(project_id, staged.sha256))
                factory = _factory(request)
                try:
                    with session_scope(factory) as session:
                        return repository.publish_import(
                            session, project_id, received.metadata, received
                        )
                except OperationalError as exc:
                    raise _unavailable() from exc

            accepted: ImportAccepted = await run_in_threadpool(commit)
        finally:
            await run_in_threadpool(store.remove_staging, staging)
        new = accepted.job_id is not None and not accepted.replayed
        return JSONResponse(
            accepted.model_dump(mode="json"),
            status_code=202 if new else 200,
            headers={"Cache-Control": "no-store"},
        )

    @router.get("/source-revisions", response_model=SourceRevisionPage)
    def list_revisions(
        project_id: UUID, request: Request, params: Annotated[PageParams, Query()]
    ) -> SourceRevisionPage:
        page: SourceRevisionPage = _db(
            request,
            lambda s: repository.list_revisions(s, project_id, params.limit, params.cursor),
        )
        return page

    @router.get("/documents", response_model=DocumentPage)
    def list_documents(
        project_id: UUID,
        request: Request,
        params: Annotated[PageParams, Query()],
        source_revision_id: UUID | None = None,
    ) -> DocumentPage:
        page: DocumentPage = _db(
            request,
            lambda s: repository.list_documents(
                s, project_id, source_revision_id, params.limit, params.cursor
            ),
        )
        return page

    @router.patch(
        "/documents/{document_id}/classification",
        response_model=SourceDocumentItem,
        dependencies=[Depends(_guard_mutation)],
    )
    def update_classification(
        project_id: UUID, document_id: UUID, body: ClassificationUpdate, request: Request
    ) -> SourceDocumentItem:
        def work(session: Any) -> SourceDocumentItem:
            repository.update_classification(session, project_id, document_id, body)
            return repository.get_document_in_project(session, project_id, document_id, None)

        item: SourceDocumentItem = _db(request, work)
        return item

    return router

"""Original PDF bytes for an in-app viewer (EXPLORE_POLISH B-1).

``GET /api/v1/projects/{p}/documents/{d}/content`` serves the stored original of a PDF document of
that project. The client never supplies a path: the document row (looked up by project and id)
gives the server-generated storage key, and the stored SHA-256 and size are verified against the
blob (streamed in 1 MiB chunks; the result is remembered per file identity so a viewer's many
range requests do not re-hash a large file). The body is streamed from disk (single ``Range``
supported); nothing is loaded into memory.
"""

from __future__ import annotations

import re
import threading
from collections import OrderedDict
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.responses import FileResponse

from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope
from fieldlens.evidence.integrity import REUPLOAD_MESSAGE, require_root
from fieldlens.evidence.storage import BlobStore, VerifyOutcome
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

# The browser's built-in PDF viewer needs a document it may render; ``sandbox`` is deliberately not
# used (Chromium refuses to show a PDF under a sandboxed response) and ``frame-ancestors`` is not
# set so the same-origin viewer frame works through the dev proxy and the packaged app.
CSP = "default-src 'none'"
CACHE_CONTROL = "private, max-age=300"
_UNSAFE = re.compile(r"[^A-Za-z0-9._ -]")
_VERIFIED_MAX = 256


class _SingleRangeFile(FileResponse):
    max_ranges = 1  # a viewer asks for one range at a time; refuse multipart amplification


class _Verified:
    """Remember blobs whose bytes verified, keyed by file identity (path, inode, size, mtime)."""

    def __init__(self) -> None:
        self._seen: OrderedDict[tuple[Any, ...], None] = OrderedDict()
        self._lock = threading.Lock()

    def has(self, key: tuple[Any, ...]) -> bool:
        with self._lock:
            if key in self._seen:
                self._seen.move_to_end(key)
                return True
            return False

    def add(self, key: tuple[Any, ...]) -> None:
        with self._lock:
            self._seen[key] = None
            while len(self._seen) > _VERIFIED_MAX:
                self._seen.popitem(last=False)


_verified = _Verified()


def safe_filename(name: str) -> str:
    """Display name safe for a header: no path parts, controls, quotes or non-ASCII fallbacks."""
    base = re.split(r"[\\/]", name)[-1].strip() or "document.pdf"
    ascii_name = _UNSAFE.sub("_", base).strip(" .") or "document.pdf"
    return ascii_name[:120]


def content_disposition(name: str) -> str:
    from urllib.parse import quote

    base = re.split(r"[\\/]", name)[-1].strip() or "document.pdf"
    cleaned = "".join(ch for ch in base if ch.isprintable() and ch not in '"\\')[:200]
    return f"inline; filename=\"{safe_filename(name)}\"; filename*=UTF-8''{quote(cleaned)}"


def _error(reason: str, status: int = 409) -> ContractError:
    return ContractError(ErrorCode.CONFLICT, REUPLOAD_MESSAGE, status, {"reason": reason})


def build_document_content_router() -> APIRouter:
    # No router-wide ``no-store``: the original is immutable (keyed by its SHA-256) and private.
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}",
        tags=["imports"],
        responses={
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            415: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
    )

    @router.get(
        "/documents/{document_id}/content",
        response_class=Response,
        responses={
            200: {"content": {"application/pdf": {}}, "description": "Original PDF bytes."},
            206: {"content": {"application/pdf": {}}, "description": "Requested byte range."},
            304: {"description": "Not modified."},
            416: {"description": "Range not satisfiable."},
        },
    )
    def document_content(project_id: UUID, document_id: UUID, request: Request) -> Response:
        factory = request.app.state.session_factory
        if factory is None:
            raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable", 503)
        try:
            with session_scope(factory) as session:
                row = session.execute(
                    select(
                        m.source_document.c.storage_key,
                        m.source_document.c.sha256,
                        m.source_document.c.size_bytes,
                        m.source_document.c.original_filename,
                        m.source_document.c.format_family,
                    ).where(
                        m.source_document.c.project_id == project_id,
                        m.source_document.c.document_id == document_id,
                    )
                ).first()
        except OperationalError as exc:
            raise ContractError(
                ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable", 503
            ) from exc
        if row is None:
            raise ContractError(ErrorCode.NOT_FOUND, "document not found", 404)
        if row.format_family != "pdf":
            raise ContractError(
                ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                "only PDF documents can be opened in the viewer",
                415,
                {"format_family": row.format_family},
            )
        require_root(request)
        store: BlobStore = request.app.state.blob_store
        try:
            path = store.path_for(row.storage_key)
            stat = path.stat()
        except (FileNotFoundError, NotADirectoryError):
            raise _error(VerifyOutcome.MISSING.value) from None
        except ValueError:
            raise _error("invalid_storage_key") from None
        identity = (str(path), stat.st_ino, stat.st_size, stat.st_mtime_ns, row.sha256)
        if not _verified.has(identity):
            result = store.verify(row.storage_key, row.sha256, row.size_bytes)
            if result.outcome is not VerifyOutcome.OK:
                raise _error(result.outcome.value)
            _verified.add(identity)
        etag = f'"{row.sha256}"'
        headers = {
            "Content-Disposition": content_disposition(row.original_filename),
            "Content-Security-Policy": CSP,
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": CACHE_CONTROL,
            "ETag": etag,
            "Accept-Ranges": "bytes",
        }
        if _etag_matches(request.headers.get("if-none-match"), etag):
            return Response(status_code=304, headers=headers)
        return _SingleRangeFile(
            path, media_type="application/pdf", headers=headers, stat_result=stat
        )

    return router


def _etag_matches(header: str | None, etag: str) -> bool:
    if not header:
        return False
    return header.strip() == "*" or etag in [
        t.strip().removeprefix("W/") for t in header.split(",")
    ]

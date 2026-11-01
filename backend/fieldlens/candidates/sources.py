"""Scoped, bounded read access to stored documents for the tools and the validators.

Every call is qualified by project and source revision: a document that is not part of the unit's
revision does not exist as far as callers can tell. Spans are bounded, text is never returned
beyond the bounds and nothing here exposes a filesystem path."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.evidence.storage import BlobStore
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .pages import PageError, PageRenderer, PageText

MAX_SPAN_LINES = 200
MAX_SPAN_CHARS = 8000
MAX_LINE_BYTES = 4096  # per line read; the rest of a longer line is skipped, never held
MAX_LINE_SCAN = 5_000_000
SNIFF_BYTES = 8192

DocKind = Literal["pdf", "text", "unsupported"]


class SourceError(Exception):
    """A read that cannot be served; ``code`` is stable and safe to show to a model."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DocInfo:
    project_id: UUID
    source_revision_id: UUID
    document_id: UUID
    sha256: str
    storage_key: str
    kind: DocKind


@dataclass(frozen=True)
class LineSpan:
    text: str
    line_start: int
    line_end: int
    truncated: bool


class SourceReader:
    def __init__(
        self, factory: sessionmaker[Session], store: BlobStore, renderer: PageRenderer
    ) -> None:
        self._factory = factory
        self._store = store
        self.renderer = renderer

    # -- documents --------------------------------------------------------------------------
    def document(self, project_id: UUID, revision_id: UUID, document_id: UUID) -> DocInfo | None:
        with session_scope(self._factory) as s:
            return self.document_in(s, project_id, revision_id, document_id)

    def document_in(
        self, s: Session, project_id: UUID, revision_id: UUID, document_id: UUID
    ) -> DocInfo | None:
        sd, srd = m.source_document, m.source_revision_document
        row = s.execute(
            select(sd.c.sha256, sd.c.storage_key)
            .join(
                srd,
                (srd.c.project_id == sd.c.project_id) & (srd.c.document_id == sd.c.document_id),
            )
            .where(
                sd.c.project_id == project_id,
                sd.c.document_id == document_id,
                srd.c.source_revision_id == revision_id,
            )
        ).first()
        if row is None:
            return None
        kind = self._sniff(row.storage_key)
        return DocInfo(project_id, revision_id, document_id, row.sha256, row.storage_key, kind)

    def _sniff(self, storage_key: str) -> DocKind:
        try:
            path = self._store.path_for(storage_key)
            with path.open("rb") as handle:
                head = handle.read(SNIFF_BYTES)
        except (ValueError, OSError):
            return "unsupported"
        if head.startswith(b"%PDF-"):
            return "pdf"
        if head.startswith(b"PK\x03\x04") or b"\x00" in head:
            return "unsupported"
        return "text"

    def require(self, project_id: UUID, revision_id: UUID, document_id: UUID) -> DocInfo:
        doc = self.document(project_id, revision_id, document_id)
        if doc is None:
            raise SourceError("document_not_found", "document is not part of this project revision")
        return doc

    # -- text lines -------------------------------------------------------------------------
    def read_lines(self, doc: DocInfo, line_start: int, line_end: int) -> LineSpan:
        if doc.kind != "text":
            raise SourceError("unsupported_format", "line spans need a text document")
        if line_start < 1 or line_end < line_start:
            raise SourceError("bad_range", "line range must satisfy 1 <= start <= end")
        if line_end - line_start + 1 > MAX_SPAN_LINES:
            raise SourceError("range_too_large", f"at most {MAX_SPAN_LINES} lines per read")
        try:
            path = self._store.path_for(doc.storage_key)
            handle = path.open("rb")
        except (ValueError, OSError) as exc:
            raise SourceError("document_unavailable", "document content is unavailable") from exc
        lines: list[str] = []
        cut = False
        with handle:
            number = 0
            while number < min(line_end, MAX_LINE_SCAN):
                chunk = handle.readline(MAX_LINE_BYTES + 1)
                if not chunk:
                    break
                number += 1
                was_long = long_line = len(chunk) > MAX_LINE_BYTES and not chunk.endswith(b"\n")
                while long_line:  # skip the remainder of an over-long line in bounded pieces
                    rest = handle.readline(MAX_LINE_BYTES)
                    long_line = bool(rest) and not rest.endswith(b"\n")
                if was_long and number >= line_start:
                    cut = True
                    chunk = chunk[:MAX_LINE_BYTES]
                if number >= line_start:
                    lines.append(chunk.decode("utf-8", "replace").rstrip("\r\n"))
        if not lines:
            raise SourceError("range_not_found", "the line range is beyond the end of the document")
        text = "\n".join(lines)
        truncated = cut or len(text) > MAX_SPAN_CHARS
        return LineSpan(text[:MAX_SPAN_CHARS], line_start, line_start + len(lines) - 1, truncated)

    def full_text(self, doc: DocInfo, max_bytes: int = 2_000_000, max_pages: int = 500) -> str:
        """Bounded whole-document text for server-side quote checks (never sent to a model as is).
        Text documents are read up to ``max_bytes``; PDFs through the page renderer up to
        ``max_pages`` pages. A document that cannot be read raises ``SourceError``."""
        if doc.kind == "pdf":
            return "\n".join(self.page_texts(doc, max_pages=max_pages))[:max_bytes]
        if doc.kind != "text":
            raise SourceError("unsupported_format", "text search needs a text or PDF document")
        try:
            with self._store.path_for(doc.storage_key).open("rb") as handle:
                raw = handle.read(max_bytes)
        except (ValueError, OSError) as exc:
            raise SourceError("document_unavailable", "document content is unavailable") from exc
        return raw.decode("utf-8", "replace")

    # -- pdf pages --------------------------------------------------------------------------
    def read_page(self, doc: DocInfo, page: int) -> PageText:
        if doc.kind != "pdf":
            raise SourceError("unsupported_format", "page reads need a PDF document")
        try:
            out = self.renderer.page_text(doc.storage_key, page)
        except PageError as exc:
            raise SourceError(exc.code, str(exc)) from exc
        return PageText(
            out.text[:MAX_SPAN_CHARS],
            out.page,
            out.page_count,
            out.has_text_layer,
            out.truncated or len(out.text) > MAX_SPAN_CHARS,
        )

    def page_texts(self, doc: DocInfo, max_pages: int = 5000) -> list[str]:
        if doc.kind != "pdf":
            raise SourceError("unsupported_format", "triage needs a PDF document")
        try:
            return self.renderer.all_page_texts(doc.storage_key, max_pages=max_pages)
        except PageError as exc:
            raise SourceError(exc.code, str(exc)) from exc


def args_hash(value: object) -> str:
    import json

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()

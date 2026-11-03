"""Server-side source text access for quote verification and prompt snippets.

``SourceText`` is the only way proposals touch source content. It is project scoped, bounded and
read-only; document text is data, never instructions, and is not logged."""

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.candidates.sources import SourceError, SourceReader
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .designator import normalize_text

logger = logging.getLogger(__name__)

MAX_CACHED_DOCUMENTS = 24
MAX_SCAN_LINES = 200_000
SNIPPET_CHARS = 240


class SourceText(Protocol):
    def content_sha(self, project_id: UUID, document_id: UUID) -> str | None:
        """SHA-256 of the stored document, None when it is not part of the project."""
        ...

    def contains(self, project_id: UUID, document_id: UUID, quote: str) -> bool | None:
        """Whether the normalized quote occurs in the normalized document text; None when the
        document text is unavailable (unknown document, unsupported or unreadable format)."""
        ...

    def snippets(
        self, project_id: UUID, document_id: UUID, pattern: re.Pattern[str], limit: int
    ) -> list[tuple[int, str]]:
        """Up to ``limit`` (line number, trimmed line) pairs whose line matches ``pattern``."""
        ...


class ReaderSourceText:
    """``SourceText`` over the stored documents through the extraction ``SourceReader``."""

    def __init__(self, factory: sessionmaker[Session], reader: SourceReader) -> None:
        self._factory = factory
        self._reader = reader
        self._raw: OrderedDict[tuple[UUID, UUID], str | None] = OrderedDict()
        self._norm: dict[tuple[UUID, UUID], str | None] = {}

    def content_sha(self, project_id: UUID, document_id: UUID) -> str | None:
        with session_scope(self._factory) as s:
            row = s.execute(
                select(m.source_document.c.sha256).where(
                    m.source_document.c.project_id == project_id,
                    m.source_document.c.document_id == document_id,
                )
            ).first()
        return None if row is None else str(row.sha256)

    def _text(self, project_id: UUID, document_id: UUID) -> str | None:
        key = (project_id, document_id)
        if key in self._raw:
            self._raw.move_to_end(key)
            return self._raw[key]
        text_: str | None = None
        with session_scope(self._factory) as s:
            revision = s.execute(
                select(m.extraction_run.c.source_revision_id)
                .where(
                    m.extraction_run.c.project_id == project_id,
                    m.extraction_run.c.document_id == document_id,
                    m.extraction_run.c.superseded.is_(False),
                )
                .limit(1)
            ).scalar()
            if revision is None:  # a PDF read only by the model has no extraction run (TASK-076)
                revision = s.execute(
                    select(m.source_revision_document.c.source_revision_id)
                    .join(
                        m.source_revision,
                        m.source_revision.c.source_revision_id
                        == m.source_revision_document.c.source_revision_id,
                    )
                    .where(
                        m.source_revision_document.c.project_id == project_id,
                        m.source_revision_document.c.document_id == document_id,
                    )
                    .order_by(m.source_revision.c.created_at.desc())
                    .limit(1)
                ).scalar()
            doc = (
                self._reader.document_in(s, project_id, revision, document_id)
                if revision is not None
                else None
            )
        if doc is not None:
            try:
                text_ = self._reader.full_text(doc)
            except SourceError as exc:
                logger.info("source text unavailable (%s)", exc.code)
        self._raw[key] = text_
        self._norm.pop(key, None)
        while len(self._raw) > MAX_CACHED_DOCUMENTS:
            old, _ = self._raw.popitem(last=False)
            self._norm.pop(old, None)
        return text_

    def contains(self, project_id: UUID, document_id: UUID, quote: str) -> bool | None:
        raw = self._text(project_id, document_id)
        if raw is None:
            return None
        key = (project_id, document_id)
        if self._norm.get(key) is None:
            self._norm[key] = normalize_text(raw)
        return normalize_text(quote) in (self._norm[key] or "")

    def snippets(
        self, project_id: UUID, document_id: UUID, pattern: re.Pattern[str], limit: int
    ) -> list[tuple[int, str]]:
        raw = self._text(project_id, document_id)
        out: list[tuple[int, str]] = []
        if raw is None:
            return out
        for number, line in enumerate(raw.splitlines()[:MAX_SCAN_LINES], start=1):
            if pattern.search(line):
                out.append((number, line.strip()[:SNIPPET_CHARS]))
                if len(out) >= limit:
                    break
        return out

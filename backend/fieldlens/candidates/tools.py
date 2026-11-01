"""The read-only tool allowlist for extraction units (AX-9, AX-12).

Four tools, all project- and revision-scoped, argument-validated, bounded, and returning only
source content with its locator: ``read_span``, ``read_table``, ``search_project`` and
``get_page_image``. Nothing mutates, nothing executes model text, no path or URL is ever
accepted or returned. A refused call returns a fixed error and is recorded by the harness."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.messages import ToolCallPart, ToolSpec
from fieldlens.contracts.errors import ContractError
from fieldlens.contracts.evidence import EvidenceLink
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope
from fieldlens.retrieval.search import RetrievalService

from .pages import PageError, RenderedPage
from .sources import DocInfo, SourceError, SourceReader

MAX_TABLE_ROWS = 25
MAX_SEARCH_HITS = 5
HIT_TEXT_CHARS = 500
ALLOWED_TOOLS = ("read_span", "read_table", "search_project", "get_page_image")


def _spec(
    name: str, description: str, props: dict[str, JsonValue], required: list[str]
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        parameters={"type": "object", "properties": props, "required": list(required)},
    )


TOOL_SPECS: tuple[ToolSpec, ...] = (
    _spec(
        "read_span",
        "Read a bounded text span: lines of a text document, or the text layer of one PDF page.",
        {
            "document_id": {"type": "string"},
            "line_start": {"type": "integer"},
            "line_end": {"type": "integer"},
            "page": {"type": "integer"},
        },
        ["document_id"],
    ),
    _spec(
        "read_table",
        "Read parsed table records of a document by record ordinal (original values and units).",
        {
            "document_id": {"type": "string"},
            "start": {"type": "integer"},
            "count": {"type": "integer"},
        },
        ["document_id", "start", "count"],
    ),
    _spec(
        "search_project",
        "Search the project's source observations (bounded; returns passages with locators).",
        {"query": {"type": "string"}, "limit": {"type": "integer"}},
        ["query"],
    ),
    _spec(
        "get_page_image",
        "Get the upright image of one PDF page (1-based). The image is attached to the "
        "conversation. rotation (0, 90, 180, 270 clockwise) overrides the orientation check.",
        {
            "document_id": {"type": "string"},
            "page": {"type": "integer"},
            "rotation": {"type": "integer"},
        },
        ["document_id", "page"],
    ),
)


@dataclass
class ToolOutcome:
    content: str
    outcome: str  # ok | refused | error
    reason: str | None = None
    summary: str = ""
    evidence: list[EvidenceLink] = field(default_factory=list)
    image: RenderedPage | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class _Refused(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _doc_id(value: object) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise _Refused("bad_argument", "document_id must be a UUID") from exc


class Toolbox:
    def __init__(
        self,
        *,
        factory: sessionmaker[Session],
        reader: SourceReader,
        retrieval: RetrievalService | None,
        project_id: UUID,
        revision_id: UUID,
        long_side: int,
    ) -> None:
        self._factory = factory
        self._reader = reader
        self._retrieval = retrieval
        self._project = project_id
        self._revision = revision_id
        self._long_side = long_side

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return TOOL_SPECS

    # -- dispatch ---------------------------------------------------------------------------
    def execute(self, call: ToolCallPart) -> ToolOutcome:
        args = call.arguments
        try:
            if call.name == "read_span":
                return self._read_span(args)
            if call.name == "read_table":
                return self._read_table(args)
            if call.name == "search_project":
                return self._search(args)
            if call.name == "get_page_image":
                return self.page_image(
                    _doc_id(args.get("document_id")), args.get("page"), args.get("rotation")
                )
        except _Refused as exc:
            return self._refused(exc.code, str(exc))
        except SourceError as exc:
            return self._refused(exc.code, str(exc))
        except PageError as exc:
            return self._refused(exc.code, str(exc))
        return self._refused("tool_not_allowed", "tool is not on the allowlist")

    @staticmethod
    def _refused(code: str, message: str) -> ToolOutcome:
        return ToolOutcome(
            json.dumps({"error": code, "message": message}),
            "refused",
            code,
            f"refused: {code}",
            detail={"reason": code},
        )

    def _doc(self, document_id: UUID) -> DocInfo:
        return self._reader.require(self._project, self._revision, document_id)

    # -- read_span --------------------------------------------------------------------------
    def _read_span(self, args: dict[str, JsonValue]) -> ToolOutcome:
        doc = self._doc(_doc_id(args.get("document_id")))
        base = {"document_id": str(doc.document_id), "source_revision_id": str(self._revision)}
        if doc.kind == "pdf":
            page = args.get("page")
            if not isinstance(page, int) or isinstance(page, bool):
                raise _Refused("bad_argument", "a PDF read needs an integer page")
            out = self._reader.read_page(doc, page)
            locator = {"kind": "pdf", "page": page, **base}
            body = {
                "locator": locator,
                "has_text_layer": out.has_text_layer,
                "truncated": out.truncated,
                "text": out.text,
            }
            summary = f"page {page} text layer, {len(out.text)} chars"
        elif doc.kind == "text":
            start, end = args.get("line_start"), args.get("line_end")
            if not isinstance(start, int) or isinstance(start, bool):
                raise _Refused("bad_argument", "a text read needs integer line_start and line_end")
            end = start if end is None else end
            if not isinstance(end, int) or isinstance(end, bool):
                raise _Refused("bad_argument", "line_end must be an integer")
            span = self._reader.read_lines(doc, start, end)
            locator = {
                "kind": "text",
                "line_start": span.line_start,
                "line_end": span.line_end,
                **base,
            }
            body = {"locator": locator, "truncated": span.truncated, "text": span.text}
            summary = f"lines {span.line_start}-{span.line_end}"
        else:
            raise _Refused("unsupported_format", "this document format has no span reader")
        link = EvidenceLink.model_validate(
            {
                "document_id": doc.document_id,
                "source_revision_id": self._revision,
                "locator": locator,
            }
        )
        return ToolOutcome(
            json.dumps(body), "ok", None, summary, [link], detail=_loc_detail(locator)
        )

    # -- read_table -------------------------------------------------------------------------
    def _read_table(self, args: dict[str, JsonValue]) -> ToolOutcome:
        doc = self._doc(_doc_id(args.get("document_id")))
        start, count = args.get("start"), args.get("count")
        if not isinstance(start, int) or isinstance(start, bool) or start < 0:
            raise _Refused("bad_argument", "start must be a record ordinal >= 0")
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 1 <= count <= MAX_TABLE_ROWS
        ):
            raise _Refused("range_too_large", f"count must be 1..{MAX_TABLE_ROWS}")
        er, run = m.extracted_record, m.extraction_run
        with session_scope(self._factory) as s:
            rows = s.execute(
                select(er.c.ordinal, er.c.kind, er.c.subject, er.c.locator, er.c.attributes)
                .join(run, run.c.run_id == er.c.run_id)
                .where(
                    er.c.project_id == self._project,
                    er.c.document_id == doc.document_id,
                    run.c.superseded.is_(False),
                    run.c.status.in_(("succeeded", "partial")),
                    er.c.ordinal >= start,
                    er.c.ordinal < start + count,
                )
                .order_by(er.c.ordinal)
            ).all()
        records: list[dict[str, Any]] = []
        links: list[EvidenceLink] = []
        for row in rows:
            records.append(
                {
                    "ordinal": row.ordinal,
                    "kind": row.kind,
                    "subject": row.subject,
                    "locator": row.locator,
                    "attributes": [
                        {
                            "key": a.get("key"),
                            "original_text": a.get("original_text"),
                            "unit": a.get("unit"),
                            "unit_status": a.get("unit_status"),
                            "number": a.get("number"),
                        }
                        for a in row.attributes[:20]
                    ],
                }
            )
            link = _unit_link(row.locator, doc.document_id, self._revision)
            if link is not None and len(links) < 8:
                links.append(link)
        body = {"document_id": str(doc.document_id), "records": records}
        return ToolOutcome(
            json.dumps(body, default=str)[:12000],
            "ok",
            None,
            f"{len(records)} record(s) from ordinal {start}",
            links,
            detail={"records": len(records), "start": start},
        )

    # -- search_project ---------------------------------------------------------------------
    def _search(self, args: dict[str, JsonValue]) -> ToolOutcome:
        query = args.get("query")
        if not isinstance(query, str) or not query.strip() or len(query) > 300:
            raise _Refused("bad_argument", "query must be 1..300 characters")
        limit = args.get("limit", MAX_SEARCH_HITS)
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
            raise _Refused("bad_argument", "limit must be a positive integer")
        if self._retrieval is None:
            raise _Refused("search_unavailable", "project search is not available")
        try:
            result = self._retrieval.search_evidence(
                self._project,
                query.strip(),
                source_revision_id=self._revision,
                limit=min(limit, MAX_SEARCH_HITS),
            )
        except ContractError as exc:
            raise _Refused("search_failed", exc.message) from exc
        hits = []
        links: list[EvidenceLink] = []
        for hit in result.hits[:MAX_SEARCH_HITS]:
            hits.append(
                {
                    "document_id": str(hit.document_id),
                    "kind": hit.kind,
                    "label": hit.label,
                    "text": hit.text[:HIT_TEXT_CHARS],
                    "locators": [e.locator.root.model_dump(mode="json") for e in hit.evidence[:2]],
                }
            )
            for ev in hit.evidence[:1]:
                link = _unit_link(
                    ev.locator.root.model_dump(mode="json"), hit.document_id, self._revision
                )
                if link is not None and len(links) < 5:
                    links.append(link)
        body = {"status": result.status.value, "hits": hits}
        return ToolOutcome(
            json.dumps(body, default=str),
            "ok",
            None,
            f"{len(hits)} hit(s), status {result.status.value}",
            links,
            detail={"hits": len(hits), "status": result.status.value},
        )

    # -- get_page_image ---------------------------------------------------------------------
    def page_image(self, document_id: UUID, page: object, rotation: object = None) -> ToolOutcome:
        doc = self._doc(document_id)
        if doc.kind != "pdf":
            raise _Refused("unsupported_format", "page images need a PDF document")
        if not isinstance(page, int) or isinstance(page, bool):
            raise _Refused("bad_argument", "page must be an integer (1-based)")
        if rotation is not None and (not isinstance(rotation, int) or isinstance(rotation, bool)):
            raise _Refused("bad_argument", "rotation must be 0, 90, 180 or 270")
        image = self._reader.renderer.render(
            doc.sha256, doc.storage_key, page, long_side=self._long_side, rotation=rotation
        )
        locator = {
            "kind": "pdf",
            "page": page,
            "document_id": str(doc.document_id),
            "source_revision_id": str(self._revision),
        }
        link = EvidenceLink.model_validate(
            {
                "document_id": doc.document_id,
                "source_revision_id": self._revision,
                "locator": locator,
            }
        )
        body = {
            "locator": locator,
            "image": image.meta(),
            "note": "image attached to the conversation",
        }
        detail = {**_loc_detail(locator), **image.meta()}
        return ToolOutcome(
            json.dumps(body),
            "ok",
            None,
            f"page {page} image {image.width}x{image.height}"
            + (" (cached)" if image.cache_hit else ""),
            [link],
            image,
            detail,
        )


def _loc_detail(locator: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in locator.items() if k in ("kind", "page", "line_start", "line_end")}


def _unit_link(locator: object, document_id: UUID, revision_id: UUID) -> EvidenceLink | None:
    """Evidence link for a stored locator, re-pointed at the unit's revision (documents carry
    over between revisions); None when the locator cannot be represented."""
    if not isinstance(locator, dict) or "kind" not in locator:
        return None
    fixed = {**locator}
    if fixed.get("kind") != "derivation":
        fixed["document_id"] = str(document_id)
        fixed["source_revision_id"] = str(revision_id)
    try:
        return EvidenceLink.model_validate(
            {"document_id": document_id, "source_revision_id": revision_id, "locator": fixed}
        )
    except ValueError:
        return None

"""Per-turn registry of what this turn's tool results established.

Every answer block is validated against this registry: a document, page, wellbore, series, citation
or number the tools did not return in *this* turn cannot appear in an answer, whatever the model or
any document text says. The registry holds only server-produced data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from uuid import UUID

from fieldlens.contracts.chat import Citation
from fieldlens.contracts.evidence import EvidenceLink

MAX_CITATIONS_PER_TURN = 99
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


class ContextClass(StrEnum):
    """Where a tool result comes from: never blur source facts with drafts."""

    SOURCE = "source"
    """Extracted from uploaded documents (validated records, chunks, series)."""
    PUBLISHED = "published"
    """The project's published identity/model (for example the wellbore list)."""
    DRAFT = "draft"
    """Unpublished proposals; shown labeled as draft and never as fact."""


@dataclass
class ToolRecord:
    call_id: UUID
    name: str
    ok: bool
    context_class: ContextClass
    result: dict[str, Any]


@dataclass
class SeriesRef:
    series_id: UUID
    call_id: UUID
    index_encoding: str = "numeric"


@dataclass
class Citable:
    marker: str
    call_id: UUID
    evidence: EvidenceLink | None = None
    record_id: UUID | None = None
    claim_id: UUID | None = None
    label: str | None = None
    draft: bool = False

    def to_citation(self) -> Citation:
        return Citation(
            marker=self.marker,
            tool_call_id=self.call_id,
            evidence=self.evidence,
            record_id=self.record_id,
            claim_id=self.claim_id,
            label=self.label,
            draft=self.draft,
        )


def numbers_in(value: Any, out: set[float]) -> None:
    """Every number a tool result states (leaves, and digits inside its strings)."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int | float):
        out.add(float(value))
    elif isinstance(value, str):
        for match in _NUMBER.findall(value):
            try:
                out.add(float(match))
            except ValueError:
                continue
    elif isinstance(value, dict):
        for item in value.values():
            numbers_in(item, out)
    elif isinstance(value, list | tuple):
        out.add(float(len(value)))
        for item in value:
            numbers_in(item, out)


@dataclass
class TurnEvidence:
    calls: dict[UUID, ToolRecord] = field(default_factory=dict)
    documents: set[UUID] = field(default_factory=set)
    pages: dict[UUID, set[int]] = field(default_factory=dict)
    locators: dict[UUID, list[dict[str, Any]]] = field(default_factory=dict)
    wellbores: set[UUID] = field(default_factory=set)
    elements: set[UUID] = field(default_factory=set)
    series: dict[UUID, SeriesRef] = field(default_factory=dict)
    citables: dict[str, Citable] = field(default_factory=dict)
    numbers: set[float] = field(default_factory=set)

    # -- registration (called by tools with server-produced data) -----------------------------
    def add_call(self, record: ToolRecord) -> None:
        self.calls[record.call_id] = record
        numbers_in(record.result, self.numbers)

    def add_evidence(self, evidence: EvidenceLink) -> None:
        if evidence.document_id is None:
            return
        self.documents.add(evidence.document_id)
        root = evidence.locator.root
        data = root.model_dump(mode="json")
        self.locators.setdefault(evidence.document_id, []).append(data)
        page = getattr(root, "page", None)
        if isinstance(page, int):
            self.pages.setdefault(evidence.document_id, set()).add(page)

    def add_citable(
        self,
        call_id: UUID,
        *,
        evidence: EvidenceLink | None = None,
        record_id: UUID | None = None,
        claim_id: UUID | None = None,
        label: str | None = None,
        draft: bool = False,
    ) -> str | None:
        """Returns the ``[n]`` marker, or None when the per-turn citation bound is reached."""
        if len(self.citables) >= MAX_CITATIONS_PER_TURN:
            return None
        marker = f"[{len(self.citables) + 1}]"
        self.citables[marker] = Citable(
            marker, call_id, evidence, record_id, claim_id, (label or "")[:200] or None, draft
        )
        if evidence is not None:
            self.add_evidence(evidence)
        return marker

    # -- lookups used by the answer validator -------------------------------------------------
    def has_locator(self, document_id: UUID, locator: dict[str, Any]) -> bool:
        return any(locator == known for known in self.locators.get(document_id, []))

    def number_known(self, text: str) -> bool:
        """A written number matches a tool number within the precision it was written with."""
        try:
            written = float(text)
        except ValueError:
            return False
        decimals = len(text.split(".", 1)[1].split("e")[0].split("E")[0]) if "." in text else 0
        tolerance = 0.5 * 10 ** (-decimals) + 1e-9
        return any(abs(written - known) <= tolerance for known in self.numbers)

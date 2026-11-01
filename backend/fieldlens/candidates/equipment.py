"""Equipment extraction runs (EQ-10): which pages to read, which documents to leave alone.

Page selection is versioned configuration plus fallbacks, never an identity decision:

1. a configured per-document page list (with a rotation where a page is known to be sideways),
   matched by content hash (a filename match is only a fallback for a name that is unique);
2. text-layer triage (keyword scoring, no model call) when no list matches;
3. an explicit, opt-in blind sample for an image-only document with no list.

An image-only document with no list and no opt-in selects nothing and says so (the run is
``failed: no_pages_selected``, never a quiet success).

A document is excluded (recorded, no model call) when the caller names it explicitly, or when its
text layer prints well labels and none of them is the subject the caller expects (the wrong-folder
case: completion reports in an F-12 folder that print F-11 wells). A scanned document has no text
layer to check; that is reported as unchecked, not as a pass."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select

from fieldlens.identity.labels import parse_bore_label
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .equipment_prompt import EQUIPMENT_QUESTION
from .harness import ExtractionHarness, RunSummary
from .sources import DocInfo, SourceError
from .triage import _has_layer, triage
from .validators import _label_in_text

PLAN_VERSION = "eq-pages-1"
SCOPE_SCAN_PAGES = 3
_WELL_NAME = re.compile(
    r"(?<![\w/])\d{1,2}/\d{1,2}-[A-Za-z]-?\d{1,3}(?:\s(?:[A-Za-z]\d{0,2}|T\d{1,2}|ST\d{1,2})\b)?"
)


@dataclass(frozen=True)
class PagePlan:
    """Pages of one known document (TASK-042 evidence), as reading plan only."""

    label: str
    sha256: str | None
    filename: str | None  # used only when sha256 does not match and the name is unique
    pages: tuple[int, ...]
    rotations: tuple[tuple[int, int], ...] = ()  # (page, clockwise degrees)
    controls: tuple[int, ...] = ()  # pages known to hold no equipment (opt-in checks)
    note: str = ""


# F-14 completion FWR (scanned, 842x595 with /Rotate 270): completion narrative and schematic
# pages; the schematic p.36 is sideways inside the scan (rotate 90 clockwise, TASK-042).
# F-5 COMPLETION_REPORT_1 (scanned): casing schematic p.48 and the as-installed table p.49.
DEFAULT_PLANS: tuple[PagePlan, ...] = (
    PagePlan(
        "F-14 FWR completion (PV-17)",
        "07206e97cba67eedd0ba2f6e67a20e7be654bfae2fd91159912f2f2595f7f334",
        "FWR_Completion_F14.pdf",
        (4, 29, 30, 35, 36),
        ((36, 90),),
        note="scanned, no text layer; p.36 schematic is sideways",
    ),
    PagePlan(
        "F-14 completion log (PV-18)",
        "266c1eff4eb04cb82534bdfcadf45a2fff86c8ed8bfed9ebf7b5edf5227b00c3",
        None,
        (),
        controls=(1,),
        note="geological summary cover; control only",
    ),
    PagePlan(
        "F-5 completion report (PV-21)",
        "4a7ad3a66d79d41037b9e1d85e9db457359c7131607e7146f35af548182d04e2",
        None,  # the name COMPLETION_REPORT_1.PDF also exists in the F-12 folder: hash only
        (48, 49),
        controls=(13, 50),
        note="scanned; as-installed completion table p.49",
    ),
)


@dataclass
class PageSelection:
    pages: list[int]
    rotations: dict[int, int]
    strategy: str  # configured | triage | blind_sample | none
    plan_version: str = PLAN_VERSION
    plan_label: str | None = None
    notes: list[str] = field(default_factory=list)


def find_plan(
    doc: DocInfo, filename: str | None, plans: tuple[PagePlan, ...] = DEFAULT_PLANS
) -> PagePlan | None:
    for plan in plans:
        if plan.sha256 and plan.sha256 == doc.sha256:
            return plan
    if filename:
        named = [p for p in plans if p.filename and p.filename.casefold() == filename.casefold()]
        if len(named) == 1 and named[0].pages:
            return named[0]
    return None


@dataclass
class ScopeCheck:
    excluded: bool
    code: str | None
    detail: str
    printed: list[str] = field(default_factory=list)
    checked: bool = False


def check_document_scope(
    harness: ExtractionHarness, doc: DocInfo, expected_label: str | None
) -> ScopeCheck:
    """Wrong-folder guard from the document's own text layer (never from a path or filename)."""
    bore = parse_bore_label(expected_label) if expected_label else None
    if bore is None or expected_label is None:
        return ScopeCheck(False, None, "no expected subject given; scope not checked")
    if doc.kind != "pdf":
        return ScopeCheck(False, None, "not a PDF; scope not checked")
    printed: list[str] = []
    try:
        for page in range(1, SCOPE_SCAN_PAGES + 1):
            text = harness.reader.read_page(doc, page).text
            printed += [mt.group(0) for mt in _WELL_NAME.finditer(text)]
    except SourceError:
        pass  # fewer pages than the scan window
    printed = list(dict.fromkeys(printed))
    if not printed:
        return ScopeCheck(False, None, "no well label in the text layer; scope unchecked")
    if any(_label_in_text(expected_label, bore, item) for item in printed):
        return ScopeCheck(False, None, "the document names the expected well", printed, True)
    return ScopeCheck(
        True,
        "document_excluded_wrong_subject",
        f"the document prints {', '.join(printed[:5])}, not {expected_label}",
        printed,
        True,
    )


@dataclass
class EquipmentRunResult:
    document_id: UUID
    excluded: bool
    exclusion_code: str | None
    scope: ScopeCheck | None
    selection: PageSelection | None
    summary: RunSummary | None
    notes: list[str] = field(default_factory=list)


class EquipmentExtractor:
    """Equipment candidates for one document at a time over the TASK-036 harness."""

    def __init__(
        self,
        harness: ExtractionHarness,
        *,
        plans: tuple[PagePlan, ...] = DEFAULT_PLANS,
        excluded_documents: Mapping[UUID, str] | None = None,
    ) -> None:
        self._harness = harness
        self._plans = plans
        self._excluded = dict(excluded_documents or {})

    def _filename(self, project_id: UUID, document_id: UUID) -> str | None:
        with session_scope(self._harness.factory) as s:
            row = s.execute(
                select(m.source_document.c.original_filename).where(
                    m.source_document.c.project_id == project_id,
                    m.source_document.c.document_id == document_id,
                )
            ).first()
        return row.original_filename if row else None

    def select_pages(
        self,
        project_id: UUID,
        revision_id: UUID,
        document_id: UUID,
        *,
        include_controls: bool = False,
        blind_sample: bool = False,
        max_pages: int | None = None,
        only_pages: Sequence[int] | None = None,
    ) -> PageSelection:
        """``only_pages`` narrows the selection to a subset (a retry of failed pages); a page that
        is not in the configured selection is never added."""
        sel = self._select_pages(
            project_id,
            revision_id,
            document_id,
            include_controls=include_controls,
            blind_sample=blind_sample,
            max_pages=max_pages,
        )
        if only_pages is not None:
            keep = set(only_pages)
            sel.pages = [p for p in sel.pages if p in keep]
            sel.rotations = {p: r for p, r in sel.rotations.items() if p in keep}
            sel.notes.append(f"restricted to pages {sorted(keep)}")
        return sel

    def _select_pages(
        self,
        project_id: UUID,
        revision_id: UUID,
        document_id: UUID,
        *,
        include_controls: bool,
        blind_sample: bool,
        max_pages: int | None,
    ) -> PageSelection:
        harness = self._harness
        doc = harness.reader.require(project_id, revision_id, document_id)
        limit = max_pages or harness.config.max_pages
        plan = find_plan(doc, self._filename(project_id, document_id), self._plans)
        if plan is not None:
            pages = [*plan.pages, *(plan.controls if include_controls else ())]
            if pages:
                return PageSelection(
                    list(dict.fromkeys(pages))[:limit],
                    dict(plan.rotations),
                    "configured",
                    plan_label=plan.label,
                    notes=[plan.note] if plan.note else [],
                )
        if doc.kind != "pdf":
            return PageSelection([], {}, "none", notes=["not a PDF; no pages to select"])
        texts = harness.reader.page_texts(doc)
        result = triage(texts, max_pages=limit, blind_sample=blind_sample)
        pages = list(result.selected)
        strategy = "blind_sample" if result.strategy == "blind_sample" else "triage"
        notes = [f"triage {result.strategy}", *result.notes[:3]]
        if blind_sample and result.strategy != "blind_sample" and result.unscored_pages:
            # opt-in: pages with no text layer cannot be scored; sample some of them evenly
            unscored = [i + 1 for i, t in enumerate(texts) if not _has_layer(t)]
            room = limit - len(pages)
            if room > 0:
                step = max(1, len(unscored) // room)
                extra = [p for p in unscored[::step] if p not in pages][:room]
                pages += extra
                strategy = "triage+blind_sample"
                notes.append(f"blind sample added {len(extra)} unscored page(s)")
        return PageSelection(pages, {}, strategy, notes=notes)

    def run_document(
        self,
        project_id: UUID,
        revision_id: UUID,
        document_id: UUID,
        *,
        subject_label: str | None = None,
        include_controls: bool = False,
        blind_sample: bool = False,
        max_pages: int | None = None,
        concurrency: int | None = None,
        only_pages: Sequence[int] | None = None,
    ) -> EquipmentRunResult:
        harness = self._harness
        doc = harness.reader.require(project_id, revision_id, document_id)
        reason = self._excluded.get(document_id)
        scope: ScopeCheck | None = None
        if reason is None:
            scope = check_document_scope(harness, doc, subject_label)
            if scope.excluded:
                reason = f"{scope.code}: {scope.detail}"
        if reason is not None:
            code = (
                scope.code if scope is not None and scope.excluded and scope.code else None
            ) or "document_excluded"
            harness.record_exclusion(
                project_id, revision_id, document_id, EQUIPMENT_QUESTION, code, reason
            )
            return EquipmentRunResult(document_id, True, code, scope, None, None, [reason])
        selection = self.select_pages(
            project_id,
            revision_id,
            document_id,
            include_controls=include_controls,
            blind_sample=blind_sample,
            max_pages=max_pages,
            only_pages=only_pages,
        )
        notes: list[str] = []
        if scope is not None and not scope.checked:
            notes.append(scope.detail)
        summary = harness.run_document(
            project_id,
            revision_id,
            document_id,
            EQUIPMENT_QUESTION,
            kind="equipment",
            pages=selection.pages,
            rotations=selection.rotations,
            concurrency=concurrency,
            document_subject=subject_label,
        )
        return EquipmentRunResult(document_id, False, None, scope, selection, summary, notes)


__all__ = [
    "DEFAULT_PLANS",
    "PLAN_VERSION",
    "EquipmentExtractor",
    "EquipmentRunResult",
    "PagePlan",
    "PageSelection",
    "ScopeCheck",
    "check_document_scope",
    "find_plan",
]

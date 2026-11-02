"""Deterministic candidate validators (AX-2/3/5/11/13). Code only, never a second model call.

A candidate ends ``rejected`` when a validator fails, ``flagged`` when something needs attention
(unresolved subject, disagreement with a parsed value, missing CRS), ``candidate`` when it is a
model-read item (never decidable) and ``accepted`` only when every validator passes and no
parsed value disagrees. LLM confidence is not an input. Warnings (a defaulted unit) are recorded
as a passed result with a reason and never block."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.contracts.candidates import (
    CandidateState,
    EquipmentAttributes,
    ExtractionMethod,
    MeasurementAttributes,
    PageReadAttributes,
    ReasonCode,
    RejectedItemAttributes,
    ValidatorName,
    ValidatorOutcome,
    ValidatorResult,
)
from fieldlens.contracts.evidence import ValidationState
from fieldlens.identity.labels import BoreLabel, aliases, norm_identifier, parse_bore_label
from fieldlens.identity.tables import record_wellbore_link as lk
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .schema import WireLocator, WireMeasurement, WirePageItem
from .sources import DocInfo, SourceError, SourceReader
from .textmatch import (
    SIZE_AMBIGUOUS,
    context_units,
    parse_quantity,
    supported_in,
    unit_after,
    unit_words,
)
from .units import (
    BASE_UNIT,
    Parsed,
    attribute_spec,
    is_coordinate,
    is_trajectory_type,
    parse_unit,
)

PARSED_TOLERANCE = 0.01  # base units (m); a parsed value this close is an agreement
LABEL_MODEL_READ = "model-read, unverified"
LABEL_ACCEPTED = "model-proposed, rule-validated"
LABEL_OPEN = "model-proposed, not accepted"
_SUBJECT_KEYS = ("wellbore_label", "wellbore_name", "well_name")
_MD = re.compile(r"\bmd\b|measured depth", re.IGNORECASE)
_TVD = re.compile(r"\btvd(?:ss)?\b|true vertical", re.IGNORECASE)
_PAIR = re.compile(r"\d+(?:\.\d+)?\s*/\s*\d+(?:\.\d+)?")


def norm_text(value: str) -> str:
    """Case, spacing and Unicode-form insensitive form used for quote matching."""
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


@dataclass
class Decision:
    state: CandidateState
    validation_state: ValidationState
    method: ExtractionMethod
    reasons: list[ReasonCode]
    results: list[ValidatorResult]
    wellbore_id: UUID | None
    subject: dict[str, str | None]
    attributes: (
        MeasurementAttributes | PageReadAttributes | EquipmentAttributes | RejectedItemAttributes
    )
    quote: str | None
    locator: dict[str, Any] | None  # evidence locator (pdf/text) when it resolved
    document_id: UUID
    label: str
    conflicts_with_record_id: UUID | None = None
    warnings: list[ReasonCode] = field(default_factory=list)


@dataclass
class ValidationContext:
    project_id: UUID
    revision_id: UUID
    document_id: UUID  # the document the unit is about
    reader: SourceReader
    factory: sessionmaker[Session]
    document_subject: str | None = None  # caller-bound identity (never from the model)


def _result(
    name: ValidatorName,
    outcome: ValidatorOutcome,
    reason: ReasonCode | None = None,
    detail: str | None = None,
) -> ValidatorResult:
    return ValidatorResult(
        validator=name, outcome=outcome, reason=reason, detail=detail[:300] if detail else None
    )


# -- locator + span -----------------------------------------------------------------------------


@dataclass
class _Span:
    doc: DocInfo
    text: str
    has_layer: bool
    locator: dict[str, Any]


def _locate(ctx: ValidationContext, loc: WireLocator) -> tuple[_Span | None, ValidatorResult]:
    doc = ctx.reader.document(ctx.project_id, ctx.revision_id, loc.document_id)
    name = ValidatorName.LOCATOR
    if doc is None:
        return None, _result(
            name, ValidatorOutcome.FAILED, ReasonCode.LOCATOR_NOT_FOUND, "document"
        )
    base = {"document_id": str(doc.document_id), "source_revision_id": str(ctx.revision_id)}
    try:
        if doc.kind == "pdf":
            if loc.page is None:
                return None, _result(
                    name,
                    ValidatorOutcome.FAILED,
                    ReasonCode.LOCATOR_UNSUPPORTED,
                    "pdf needs a page",
                )
            page = ctx.reader.read_page(doc, loc.page)
            return (
                _Span(
                    doc, page.text, page.has_text_layer, {"kind": "pdf", "page": loc.page, **base}
                ),
                _result(name, ValidatorOutcome.PASSED),
            )
        if doc.kind == "text":
            if loc.line_start is None:
                return None, _result(
                    name,
                    ValidatorOutcome.FAILED,
                    ReasonCode.LOCATOR_UNSUPPORTED,
                    "text needs a line range",
                )
            span = ctx.reader.read_lines(doc, loc.line_start, loc.line_end or loc.line_start)
            return (
                _Span(
                    doc,
                    span.text,
                    True,
                    {
                        "kind": "text",
                        "line_start": span.line_start,
                        "line_end": span.line_end,
                        **base,
                    },
                ),
                _result(name, ValidatorOutcome.PASSED),
            )
    except SourceError as exc:
        return None, _result(name, ValidatorOutcome.FAILED, ReasonCode.LOCATOR_NOT_FOUND, exc.code)
    return None, _result(
        name, ValidatorOutcome.FAILED, ReasonCode.LOCATOR_UNSUPPORTED, "format has no locator kind"
    )


# -- subject identity ---------------------------------------------------------------------------


def _subject_label(subject: dict[str, str]) -> tuple[str | None, BoreLabel | None]:
    for key in _SUBJECT_KEYS:
        value = subject.get(key)
        if isinstance(value, str) and value.strip():
            return value, parse_bore_label(value)
    return None, None


def resolve_wellbore(
    session: Session, project_id: UUID, bore: BoreLabel
) -> tuple[UUID | None, str | None]:
    """Project wellbore for a parsed label: exact canonical key, or a unique unqualified alias.
    Returns (wellbore_id, problem)."""
    wb = m.wellbore
    if bore.block:
        found = session.execute(
            select(wb.c.wellbore_id).where(
                wb.c.project_id == project_id, wb.c.wellbore_key == bore.wellbore_name
            )
        ).first()
        return (found.wellbore_id, None) if found else (None, "no such wellbore in the project")
    suffix = f" {bore.suffix}" if bore.suffix else ""
    exact = session.execute(
        select(wb.c.wellbore_id).where(
            wb.c.project_id == project_id, wb.c.wellbore_key == bore.wellbore_name
        )
    ).first()
    if exact is not None:  # D9: a block-less wellbore named exactly as written wins
        return exact.wellbore_id, None
    rows = session.execute(
        select(wb.c.wellbore_id, wb.c.wellbore_key).where(wb.c.project_id == project_id)
    ).all()
    wanted = f"-{bore.well_slot}{suffix}"
    hits = [r for r in rows if r.wellbore_key and r.wellbore_key.endswith(wanted)]
    if len(hits) == 1:
        return hits[0].wellbore_id, None
    return None, "ambiguous alias" if hits else "no such wellbore in the project"


def _document_wellbores(session: Session, project_id: UUID, document_id: UUID) -> set[UUID]:
    er = m.extracted_record
    rows = session.execute(
        select(lk.c.wellbore_id)
        .join(er, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
        .where(lk.c.project_id == project_id, er.c.document_id == document_id)
        .distinct()
    ).all()
    return {r.wellbore_id for r in rows}


def _wellbore_names(session: Session, project_id: UUID, ids: set[UUID]) -> str:
    rows = session.execute(
        select(m.wellbore.c.name).where(
            m.wellbore.c.project_id == project_id, m.wellbore.c.wellbore_id.in_(ids)
        )
    ).all()
    return ", ".join(sorted(r.name for r in rows))[:120]


# -- parsed value conflict ----------------------------------------------------------------------


def _record_value(attributes: list[dict[str, Any]], key: str) -> float | None:
    for a in attributes:
        if a.get("key") == key:
            v = a.get("normalized_number")
            return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None
    return None


def _parsed_conflict(
    session: Session,
    project_id: UUID,
    wellbore_id: UUID,
    key: str,
    normalized: float | None,
    span: _Span,
    effective_time_text: str | None,
) -> tuple[ValidatorResult, UUID | None]:
    """Compare with the deterministic records of the same wellbore and attribute. Records at the
    cited source lines decide first; otherwise the candidate must agree with ANY parsed value of
    that attribute (never skipped when parsed values exist). Records with another effective time
    are not comparable. The parsed record is read-only and always stays authoritative."""
    er, run = m.extracted_record, m.extraction_run
    rows = session.execute(
        select(er.c.record_id, er.c.document_id, er.c.locator, er.c.attributes, er.c.effective_time)
        .join(lk, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
        .join(run, run.c.run_id == er.c.run_id)
        .where(
            lk.c.project_id == project_id,
            lk.c.wellbore_id == wellbore_id,
            run.c.superseded.is_(False),
            run.c.status.in_(("succeeded", "partial")),
            er.c.attributes.contains([{"key": key}]),
        )
        .limit(2000)
    ).all()
    name = ValidatorName.PARSED_CONFLICT
    if normalized is None:
        return _result(name, ValidatorOutcome.SKIPPED, None, "no comparable proposed value"), None
    cand_time = norm_text(effective_time_text) if effective_time_text else None
    same_lines: list[tuple[UUID, float]] = []
    pool: list[tuple[UUID, float]] = []
    other_time = 0
    for row in rows:
        value = _record_value(row.attributes, key)
        if value is None:
            continue
        literal = (row.effective_time or {}).get("literal") if row.effective_time else None
        if cand_time and literal and norm_text(str(literal)) != cand_time:
            other_time += 1
            continue
        pool.append((row.record_id, value))
        loc = row.locator or {}
        if (
            row.document_id == span.doc.document_id
            and span.locator["kind"] == "text"
            and loc.get("kind") == "text"
            and loc.get("line_start") is not None
            and not (
                loc["line_end"] < span.locator["line_start"]
                or loc["line_start"] > span.locator["line_end"]
            )
        ):
            same_lines.append((row.record_id, value))
    if not pool:
        note = "no parsed value at the same effective time" if other_time else "no parsed value"
        return _result(name, ValidatorOutcome.SKIPPED, None, note), None
    if same_lines:
        if any(abs(v - normalized) <= PARSED_TOLERANCE for _, v in same_lines):
            return _result(
                name, ValidatorOutcome.PASSED, None, "agrees with the parsed value"
            ), None
        record_id, parsed = same_lines[0]
        return (
            _result(
                name,
                ValidatorOutcome.FLAGGED,
                ReasonCode.PARSED_CONFLICT,
                f"parsed value {parsed:g} at this location differs from proposed {normalized:g}; "
                "parsed stays",
            ),
            record_id,
        )
    if any(abs(v - normalized) <= PARSED_TOLERANCE for _, v in pool):
        return _result(name, ValidatorOutcome.PASSED, None, "agrees with a parsed value"), None
    nearest = sorted(pool, key=lambda rv: abs(rv[1] - normalized))[:3]
    listed = ", ".join(f"{v:g}" for _, v in nearest)
    return (
        _result(
            name,
            ValidatorOutcome.FLAGGED,
            ReasonCode.PARSED_CONFLICT,
            f"proposed {normalized:g} matches none of {len(pool)} parsed value(s); nearest {listed}",
        ),
        nearest[0][0],
    )


# -- the pipeline -------------------------------------------------------------------------------


def _decide(
    results: list[ValidatorResult], method: ExtractionMethod
) -> tuple[CandidateState, ValidationState, list[ReasonCode]]:
    failed = [r for r in results if r.outcome is ValidatorOutcome.FAILED]
    flagged = [r for r in results if r.outcome is ValidatorOutcome.FLAGGED]
    reasons: list[ReasonCode] = []

    def add(rs: list[ValidatorResult]) -> None:
        for r in rs:
            if r.reason is not None and r.reason not in reasons:
                reasons.append(r.reason)

    if failed:
        add(failed)
        # a rejected model-read value is still unverified evidence, never "invalid source"
        vstate = (
            ValidationState.UNVERIFIED
            if method is ExtractionMethod.MODEL_READ
            else ValidationState.INVALID
        )
        return CandidateState.REJECTED, vstate, reasons
    if method is ExtractionMethod.MODEL_READ:
        add(flagged)
        if ReasonCode.MODEL_READ_UNVERIFIED not in reasons:
            reasons.append(ReasonCode.MODEL_READ_UNVERIFIED)
        state = CandidateState.FLAGGED if flagged else CandidateState.CANDIDATE
        return state, ValidationState.UNVERIFIED, reasons
    if flagged:
        add(flagged)
        conflict = any(r.reason is ReasonCode.PARSED_CONFLICT for r in flagged)
        return (
            CandidateState.FLAGGED,
            ValidationState.CONFLICTING if conflict else ValidationState.UNREVIEWED,
            reasons,
        )
    return CandidateState.ACCEPTED, ValidationState.VALID, reasons


def _label_in_text(label: str, bore: BoreLabel, text: str) -> bool:
    """The well/wellbore label as the source writes it (normalized through the identity rule).
    A base label never matches a suffixed sidetrack, and a block-qualified claim never matches
    another block's well."""
    hay = norm_identifier(text)
    forms = aliases(label)
    if bore.block:
        forms = forms[:2]
    for form in forms:
        pattern = (
            rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])"
            r"(?!\s(?:[a-z]\d{0,2}|t\d{1,2}|st\d{1,2})\b)"
        )
        if bore.suffix is not None:
            pattern = rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])"
        if re.search(pattern, hay):
            return True
    return False


def validate(ctx: ValidationContext, wire: WireMeasurement | WirePageItem) -> Decision:
    results: list[ValidatorResult] = []
    warnings: list[ReasonCode] = []
    span, located = _locate(ctx, wire.locator)
    results.append(located)
    subject: dict[str, str | None] = dict(wire.subject)
    quote = wire.quote.strip() if wire.quote and wire.quote.strip() else None

    attrs: MeasurementAttributes | PageReadAttributes
    if isinstance(wire, WireMeasurement):
        attrs = MeasurementAttributes(
            attribute_key=_safe_key(wire.attribute_key),
            value_text=wire.value_text,
            unit_as_written=None,
            depth_reference=wire.depth_reference,
            crs_text=wire.crs_text,
            effective_time_text=wire.effective_time_text,
        )
    else:
        attrs = PageReadAttributes(
            item_type=wire.item_type,
            name=wire.name,
            sizes_text=list(wire.sizes_text),
            depth_text=wire.depth_text,
            notes=wire.notes,
        )

    image_only = span is not None and not span.has_layer
    method = ExtractionMethod.MODEL_READ if image_only else ExtractionMethod.MODEL_PROPOSAL
    if span is None:
        state, vstate, reasons = _decide(results, ExtractionMethod.MODEL_PROPOSAL)
        return Decision(
            state,
            vstate,
            ExtractionMethod.MODEL_PROPOSAL,
            reasons,
            results,
            None,
            subject,
            attrs,
            quote,
            None,
            wire.locator.document_id,
            LABEL_OPEN,
        )

    # quote-in-span: skipped ONLY for image-only evidence, never for text-layer evidence
    if image_only:
        results.append(
            _result(
                ValidatorName.QUOTE,
                ValidatorOutcome.SKIPPED,
                ReasonCode.MODEL_READ_UNVERIFIED,
                "image-only page: no text layer to check a quote against",
            )
        )
    elif quote is None:
        results.append(
            _result(ValidatorName.QUOTE, ValidatorOutcome.FAILED, ReasonCode.QUOTE_MISSING)
        )
    elif norm_text(quote) not in norm_text(span.text):
        results.append(
            _result(ValidatorName.QUOTE, ValidatorOutcome.FAILED, ReasonCode.QUOTE_NOT_IN_SPAN)
        )
    else:
        # in the span; the claimed value must be a WHOLE token of the quote (D1)
        claimed = wire.value_text if isinstance(wire, WireMeasurement) else (wire.name or "")
        if claimed and not supported_in(claimed, quote):
            results.append(
                _result(
                    ValidatorName.QUOTE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.VALUE_NOT_IN_QUOTE,
                    "the quote does not contain the claimed value as a whole token",
                )
            )
        else:
            results.append(_result(ValidatorName.QUOTE, ValidatorOutcome.PASSED))

    normalized: float | None = None
    if isinstance(wire, WireMeasurement):
        assert isinstance(attrs, MeasurementAttributes)
        normalized = _measurement_checks(
            wire, attrs, None if image_only else quote, span, results, warnings
        )
    else:
        assert isinstance(attrs, PageReadAttributes)
        if image_only:
            results.append(
                _result(ValidatorName.ATTRIBUTE, ValidatorOutcome.SKIPPED, None, "page item")
            )
        else:
            _verify_page_fields(wire, attrs, span, results)

    if isinstance(wire, WireMeasurement) and wire.effective_time_text and not image_only:
        if not supported_in(wire.effective_time_text, quote or ""):
            results.append(
                _result(
                    ValidatorName.PROVENANCE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.DATE_NOT_IN_SOURCE,
                    "the date text is not in the quote",
                )
            )

    # subject identity (never taken from filename/folder/category hints)
    wellbore_id: UUID | None = None
    label_text, bore = _subject_label(wire.subject)
    conflict_id: UUID | None = None
    with session_scope(ctx.factory) as session:
        if bore is None or label_text is None:
            results.append(
                _result(
                    ValidatorName.SUBJECT,
                    ValidatorOutcome.FLAGGED,
                    ReasonCode.SUBJECT_UNRESOLVED,
                    "no parseable well/wellbore label; stays unattached",
                )
            )
        else:
            wellbore_id, problem = resolve_wellbore(session, ctx.project_id, bore)
            if wellbore_id is None:
                results.append(
                    _result(
                        ValidatorName.SUBJECT,
                        ValidatorOutcome.FLAGGED,
                        ReasonCode.SUBJECT_UNRESOLVED,
                        problem,
                    )
                )
            else:
                doc_bores = _document_wellbores(session, ctx.project_id, span.doc.document_id)
                if doc_bores and wellbore_id not in doc_bores:
                    # keep the document's actual subject; never attach to the model's claim
                    names = _wellbore_names(session, ctx.project_id, doc_bores)
                    wellbore_id = None
                    results.append(
                        _result(
                            ValidatorName.SUBJECT,
                            ValidatorOutcome.FLAGGED,
                            ReasonCode.SUBJECT_DOCUMENT_MISMATCH,
                            f"the document's own records name {names}; stays unattached",
                        )
                    )
                elif not doc_bores and not _source_names(ctx, span, label_text, bore):
                    wellbore_id = None
                    other = other_wells_named(span.text, label_text, bore)
                    results.append(
                        _result(
                            ValidatorName.SUBJECT,
                            ValidatorOutcome.FLAGGED,
                            ReasonCode.SUBJECT_PAGE_NAMES_OTHER_WELL
                            if other
                            else ReasonCode.SUBJECT_UNRESOLVED,
                            f"the cited page names {', '.join(other[:3])}, not this well; "
                            "stays unattached"
                            if other
                            else "the cited text does not name this well/wellbore; "
                            "stays unattached",
                        )
                    )
                else:
                    results.append(_result(ValidatorName.SUBJECT, ValidatorOutcome.PASSED))
        if (
            wellbore_id is not None
            and isinstance(wire, WireMeasurement)
            and isinstance(attrs, MeasurementAttributes)
        ):
            outcome, conflict_id = _parsed_conflict(
                session,
                ctx.project_id,
                wellbore_id,
                attrs.attribute_key,
                normalized,
                span,
                wire.effective_time_text,
            )
            results.append(outcome)

    state, vstate, reasons = _decide(results, method)
    if method is ExtractionMethod.MODEL_READ:
        label = LABEL_MODEL_READ
    else:
        label = LABEL_ACCEPTED if state is CandidateState.ACCEPTED else LABEL_OPEN
    return Decision(
        state,
        vstate,
        method,
        reasons,
        results,
        wellbore_id,
        subject,
        attrs,
        quote,
        span.locator,
        span.doc.document_id,
        label,
        conflict_id,
        warnings,
    )


_BLOCK_LABEL = re.compile(
    r"(?<![\w/])\d{1,2}/\d{1,2}-[A-Za-z]-?\d{1,3}(?:\s(?:[A-Za-z]\d{0,2}|T\d{1,2}|ST\d{1,2})\b)?"
)
_WELL_WORD_LABEL = re.compile(
    r"\bwell(?:bore)?\s+(?:no\.?\s*)?([A-Za-z]-?\d{1,3}(?:\s(?:[A-Z]\d{0,2}|T\d{1,2}|ST\d{1,2})\b)?)"
)


def other_wells_named(text: str, label: str, bore: BoreLabel) -> list[str]:
    """Well labels the text writes explicitly (block-qualified, or after the word ``well``) that
    are not the claimed one."""
    found = [m.group(0) for m in _BLOCK_LABEL.finditer(text)]
    found += [m.group(1) for m in _WELL_WORD_LABEL.finditer(text)]
    out = []
    for item in dict.fromkeys(found):
        parsed = parse_bore_label(item)
        if parsed is None:
            continue
        if not _label_in_text(label, bore, item):
            out.append(item)
    return out


def _source_names(ctx: ValidationContext, span: _Span, label: str, bore: BoreLabel) -> bool:
    """Image-only evidence cannot be checked (the page stays unverified); text evidence must
    name the label in the cited span, or on page 1 of a PDF (cover/header). A cited page that
    explicitly names a different well overrides the cover rule (it is about that other well)."""
    if not span.has_layer:
        return True
    if _label_in_text(label, bore, span.text):
        return True
    if other_wells_named(span.text, label, bore):
        return False
    if span.doc.kind == "pdf" and span.locator.get("page") != 1:
        try:
            first = ctx.reader.read_page(span.doc, 1)
        except SourceError:
            return False
        return _label_in_text(label, bore, first.text)
    return False


def _verify_page_fields(
    wire: WirePageItem,
    attrs: PageReadAttributes,
    span: _Span,
    results: list[ValidatorResult],
) -> None:
    """D5: every field shown to the user must itself be in the text layer; unsupported fields
    are dropped and the candidate is flagged (never shown as accepted with an unchecked field).
    A field must also sit on the same line as the item's label (a depth that belongs to another
    item on the page does not validate for this one)."""
    dropped: list[str] = []
    unassociated: list[str] = []
    scope = association_text(span.text, wire.name)
    if wire.depth_text and not supported_in(wire.depth_text, span.text):
        attrs.depth_text = None
        dropped.append("depth_text")
    elif wire.depth_text and not supported_in(wire.depth_text, scope):
        attrs.depth_text = None
        unassociated.append("depth_text")
    kept = []
    for size in wire.sizes_text:
        if not supported_in(size, span.text):
            continue
        if supported_in(size, scope):
            kept.append(size)
    if len(kept) != len(wire.sizes_text):
        lost = [s for s in wire.sizes_text if s not in kept]
        if any(not supported_in(s, span.text) for s in lost):
            dropped.append("sizes_text")
        if any(supported_in(s, span.text) for s in lost):
            unassociated.append("sizes_text")
    attrs.sizes_text = kept
    if wire.notes and not supported_in(wire.notes, span.text):
        attrs.notes = None
        dropped.append("notes")
    attrs.dropped_fields = [*dropped, *unassociated]
    if dropped:
        results.append(
            _result(
                ValidatorName.ATTRIBUTE,
                ValidatorOutcome.FLAGGED,
                ReasonCode.FIELD_UNVERIFIED,
                "not in the text layer, removed: " + ", ".join(dropped),
            )
        )
    if unassociated:
        results.append(
            _result(
                ValidatorName.ATTRIBUTE,
                ValidatorOutcome.FLAGGED,
                ReasonCode.FIELD_NOT_ASSOCIATED,
                "not on the item's label line, removed: " + ", ".join(unassociated),
            )
        )
    if not dropped and not unassociated:
        results.append(_result(ValidatorName.ATTRIBUTE, ValidatorOutcome.PASSED))


def association_text(text: str, label: str | None) -> str:
    """The text a field of the item labelled ``label`` may come from: the lines that carry the
    label. No label given: the whole span. A label found on no single line (glued or split layer)
    gives an empty scope, so nothing can be associated with it."""
    if not label or not label.strip():
        return text
    return "\n".join(line for line in text.splitlines() if supported_in(label, line))


def _safe_key(key: str) -> str:
    """Keep the DTO constructible for a malformed key; the attribute validator then rejects it."""
    return key if re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", key) else "invalid.key"


def _away_unit(
    quote: str | None, claimed: Parsed | None, claimed_text: str | None
) -> ValidatorResult | str | None:
    """The quote has no unit next to the value, but writes a unit word elsewhere (``Set 3000 MD
    ft``): that is not an unambiguous association. Flag unless the quote names exactly one unit
    and the claim agrees with it (then the word is returned)."""
    if not quote:
        return None
    words = unit_words(quote)
    parsed = [(w, parse_unit(w)) for w in words]
    distinct = {(p.dimension, p.factor) for _, p in parsed if p is not None}
    if not distinct:
        return None
    if claimed is not None and distinct == {(claimed.dimension, claimed.factor)}:
        return words[0]  # one unit in the quote, equal to the claim: accepted as written
    return _result(
        ValidatorName.UNIT,
        ValidatorOutcome.FLAGGED,
        ReasonCode.UNIT_AWAY_FROM_VALUE,
        f"the quote writes {', '.join(sorted(set(words)))} away from the value; "
        f"claimed {claimed_text or 'none'}; no unambiguous association",
    )


def _same_unit(a: Parsed, b: Parsed) -> bool:
    return a.dimension == b.dimension and abs(a.factor - b.factor) < 1e-12


def _measurement_checks(
    wire: WireMeasurement,
    attrs: MeasurementAttributes,
    quote: str | None,
    span: _Span,
    results: list[ValidatorResult],
    warnings: list[ReasonCode],
) -> float | None:
    key = wire.attribute_key
    spec = attribute_spec(key) if attrs.attribute_key == key else None
    if is_trajectory_type(key):
        # AX-11 is not built: coordinates and survey values have no accept path
        results.append(
            _result(
                ValidatorName.PROVENANCE,
                ValidatorOutcome.FLAGGED,
                ReasonCode.COORDINATE_FALLBACK_UNSUPPORTED,
                "coordinate/trajectory values are not accepted from a model (AX-11 not built)",
            )
        )
        if is_coordinate(key):
            haystack = norm_text(f"{quote or ''}{span.text}")
            if not wire.crs_text or norm_text(wire.crs_text) not in haystack:
                results.append(
                    _result(
                        ValidatorName.PROVENANCE,
                        ValidatorOutcome.FLAGGED,
                        ReasonCode.CRS_NOT_STATED,
                        "no horizontal CRS stated in the source; never assumed",
                    )
                )
    if spec is None:
        if not is_trajectory_type(key):
            results.append(
                _result(
                    ValidatorName.ATTRIBUTE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.ATTRIBUTE_UNKNOWN,
                    key[:80],
                )
            )
        return None
    results.append(_result(ValidatorName.ATTRIBUTE, ValidatorOutcome.PASSED))

    context = f"{quote or ''} {wire.value_text}"
    if spec.reference is not None and "/" in wire.value_text:
        # an MD/TVD pair is not one value (TASK-042 failure mode 2)
        reason = (
            ReasonCode.COMPOUND_DEPTH_PAIR
            if _MD.search(context) and _TVD.search(context)
            else ReasonCode.NUMBER_UNPARSEABLE
        )
        results.append(
            _result(
                ValidatorName.DEPTH_REFERENCE,
                ValidatorOutcome.FAILED
                if reason is ReasonCode.COMPOUND_DEPTH_PAIR
                else ValidatorOutcome.FLAGGED,
                reason,
                "a pair of depths must be split into two values",
            )
        )
        return None
    parsed = parse_quantity(wire.value_text, allow_fraction=spec.allow_fraction)
    if parsed.value is None:
        results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.FLAGGED,
                ReasonCode.SIZE_AMBIGUOUS
                if parsed.problem == SIZE_AMBIGUOUS
                else ReasonCode.NUMBER_UNPARSEABLE,
                f"{parsed.problem}; not guessed",
            )
        )
        return None
    number = parsed.value

    claimed = parse_unit(wire.unit)
    if wire.unit is not None and claimed is None:
        results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.FAILED,
                ReasonCode.UNIT_UNPARSEABLE,
                wire.unit[:32],
            )
        )
        return None
    if claimed is not None and claimed.dimension != spec.dimension:
        results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.FAILED,
                ReasonCode.UNIT_DIMENSION_MISMATCH,
                f"{wire.unit} is {claimed.dimension}, attribute needs {spec.dimension}",
            )
        )
        return None
    word = unit_after(wire.value_text, quote) if quote else None
    quoted = parse_unit(word)
    states = context_units(span.text) if span.has_layer else set()
    unit: Parsed | None
    if quoted is not None and word is not None:
        if claimed is not None and not _same_unit(claimed, quoted):
            results.append(
                _result(
                    ValidatorName.UNIT,
                    ValidatorOutcome.FAILED,
                    ReasonCode.UNIT_CONFLICTS_WITH_QUOTE,
                    f"claimed {wire.unit}, the quote says {word}",
                )
            )
            return None
        unit = quoted
        attrs.unit_as_written, attrs.unit_source = word, "quote"
        results.append(_result(ValidatorName.UNIT, ValidatorOutcome.PASSED))
    elif (away := _away_unit(quote, claimed, wire.unit)) is not None and not isinstance(away, str):
        results.append(away)  # a unit written away from its value is never defaulted or assumed
        return None
    elif isinstance(away, str):
        unit = claimed  # the quote names exactly this one unit (not next to the value)
        attrs.unit_as_written, attrs.unit_source = away, "quote"
        results.append(_result(ValidatorName.UNIT, ValidatorOutcome.PASSED))
    else:
        stated = {parse_unit(s) for s in states}
        contradicts = bool(stated) and not any(
            u is not None and (claimed is None or _same_unit(u, claimed)) for u in stated
        )
        if not span.has_layer and claimed is not None:
            unit = claimed  # image-read: nothing to check against; stays unverified
            attrs.unit_as_written, attrs.unit_source = wire.unit, "claimed"
            results.append(_result(ValidatorName.UNIT, ValidatorOutcome.PASSED))
        elif claimed is None and len(states) == 1:
            only = next(iter(states))  # the cited context states exactly one unit: use it
            unit = parse_unit(only)
            attrs.unit_as_written, attrs.unit_source = only, "context"
            results.append(_result(ValidatorName.UNIT, ValidatorOutcome.PASSED))
        elif claimed is None and len(states) > 1:
            unit = None
            results.append(
                _result(
                    ValidatorName.UNIT,
                    ValidatorOutcome.FLAGGED,
                    ReasonCode.UNIT_NOT_IN_SOURCE,
                    f"the context states several units ({', '.join(sorted(states))})",
                )
            )
        elif contradicts:
            unit = None
            results.append(
                _result(
                    ValidatorName.UNIT,
                    ValidatorOutcome.FLAGGED,
                    ReasonCode.UNIT_NOT_IN_SOURCE,
                    f"the context states {', '.join(sorted(states))}, not the claimed unit",
                )
            )
        elif claimed is not None and not (
            claimed.dimension == "length" and abs(claimed.factor - 1.0) < 1e-12
        ):
            if stated and any(u is not None and _same_unit(u, claimed) for u in stated):
                unit = claimed
                attrs.unit_as_written, attrs.unit_source = wire.unit, "claimed"
                results.append(_result(ValidatorName.UNIT, ValidatorOutcome.PASSED))
            else:
                unit = None
                results.append(
                    _result(
                        ValidatorName.UNIT,
                        ValidatorOutcome.FLAGGED,
                        ReasonCode.UNIT_NOT_IN_SOURCE,
                        f"{wire.unit} is not stated by the quote or the context",
                    )
                )
        elif spec.dimension == "length":
            # the cited context states no unit: meters by default (a warning, never a block)
            unit = parse_unit("m")
            attrs.unit_defaulted, attrs.unit_source = True, "default"
            warnings.append(ReasonCode.UNIT_DEFAULTED_METERS)
            results.append(
                _result(
                    ValidatorName.UNIT,
                    ValidatorOutcome.PASSED,
                    ReasonCode.UNIT_DEFAULTED_METERS,
                    "no unit stated; meters assumed (warning)",
                )
            )
        else:
            unit = None
            results.append(
                _result(
                    ValidatorName.UNIT,
                    ValidatorOutcome.FAILED,
                    ReasonCode.UNIT_UNPARSEABLE,
                    "unit missing",
                )
            )
    if unit is None:
        return None
    if unit.dimension != spec.dimension:
        results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.FAILED,
                ReasonCode.UNIT_DIMENSION_MISMATCH,
                f"{unit.dimension} unit for a {spec.dimension} attribute",
            )
        )
        return None
    normalized = number * unit.factor
    attrs.number = number
    attrs.normalized_number = round(normalized, 6)
    attrs.normalized_unit = BASE_UNIT[spec.dimension]
    if not spec.low <= normalized <= spec.high:
        results.append(
            _result(
                ValidatorName.RANGE,
                ValidatorOutcome.FAILED,
                ReasonCode.OUT_OF_RANGE,
                f"{normalized:g} {attrs.normalized_unit} is outside {spec.low:g}..{spec.high:g}",
            )
        )
    else:
        results.append(_result(ValidatorName.RANGE, ValidatorOutcome.PASSED))

    if spec.reference is not None:
        if wire.depth_reference is not None and wire.depth_reference != spec.reference:
            results.append(
                _result(
                    ValidatorName.DEPTH_REFERENCE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.MD_TVD_CONFUSION,
                    f"key is {spec.reference}, reference says {wire.depth_reference}",
                )
            )
        elif spec.reference == "MD" and _TVD.search(quote or "") and not _MD.search(quote or ""):
            results.append(
                _result(
                    ValidatorName.DEPTH_REFERENCE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.MD_TVD_CONFUSION,
                    "the quote says TVD for an MD attribute",
                )
            )
        else:
            results.append(_result(ValidatorName.DEPTH_REFERENCE, ValidatorOutcome.PASSED))
        attrs.depth_reference = wire.depth_reference or spec.reference  # type: ignore[assignment]
    return normalized


__all__ = ["Decision", "ValidationContext", "validate", "norm_text"]

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
    ExtractionMethod,
    MeasurementAttributes,
    PageReadAttributes,
    ReasonCode,
    ValidatorName,
    ValidatorOutcome,
    ValidatorResult,
)
from fieldlens.contracts.evidence import ValidationState
from fieldlens.identity.labels import BoreLabel, parse_bore_label
from fieldlens.identity.tables import record_wellbore_link as lk
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .schema import WireLocator, WireMeasurement, WirePageItem
from .sources import DocInfo, SourceError, SourceReader
from .units import BASE_UNIT, attribute_spec, is_coordinate, parse_number, parse_unit

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
    attributes: MeasurementAttributes | PageReadAttributes
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


# -- parsed value conflict ----------------------------------------------------------------------


def _parsed_conflict(
    session: Session,
    project_id: UUID,
    wellbore_id: UUID,
    key: str,
    normalized: float | None,
    span: _Span,
) -> tuple[ValidatorResult, UUID | None]:
    """Compare with the deterministic record at the same source location (or the only parsed
    value for the attribute). The parsed record is read-only here and always stays authoritative."""
    er, run = m.extracted_record, m.extraction_run
    rows = session.execute(
        select(er.c.record_id, er.c.document_id, er.c.locator, er.c.attributes)
        .join(lk, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
        .join(run, run.c.run_id == er.c.run_id)
        .where(
            lk.c.project_id == project_id,
            lk.c.wellbore_id == wellbore_id,
            run.c.superseded.is_(False),
            run.c.status.in_(("succeeded", "partial")),
            er.c.attributes.contains([{"key": key}]),
        )
        .limit(500)
    ).all()
    name = ValidatorName.PARSED_CONFLICT
    comparable: list[tuple[UUID, float]] = []
    for row in rows:
        values = [
            a.get("normalized_number", a.get("number"))
            for a in row.attributes
            if a.get("key") == key
            and isinstance(a.get("normalized_number", a.get("number")), int | float)
        ]
        if not values:
            continue
        loc = row.locator or {}
        overlaps = (
            row.document_id == span.doc.document_id
            and span.locator["kind"] == "text"
            and loc.get("kind") == "text"
            and loc.get("line_start") is not None
            and not (
                loc["line_end"] < span.locator["line_start"]
                or loc["line_start"] > span.locator["line_end"]
            )
        )
        if overlaps:
            comparable.append((row.record_id, float(values[0])))
    if not comparable and len(rows) == 1:
        only = rows[0]
        vals = [
            a.get("normalized_number", a.get("number"))
            for a in only.attributes
            if a.get("key") == key
        ]
        if vals and isinstance(vals[0], int | float):
            comparable.append((only.record_id, float(vals[0])))
    if not comparable or normalized is None:
        return _result(name, ValidatorOutcome.SKIPPED, None, "no comparable parsed value"), None
    for record_id, parsed in comparable:
        if abs(parsed - normalized) > PARSED_TOLERANCE:
            return (
                _result(
                    name,
                    ValidatorOutcome.FLAGGED,
                    ReasonCode.PARSED_CONFLICT,
                    f"parsed value {parsed:g} differs from proposed {normalized:g}; parsed stays",
                ),
                record_id,
            )
    return _result(name, ValidatorOutcome.PASSED, None, "agrees with the parsed value"), None


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
        return CandidateState.REJECTED, ValidationState.INVALID, reasons
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


def validate(ctx: ValidationContext, wire: WireMeasurement | WirePageItem) -> Decision:
    results: list[ValidatorResult] = []
    warnings: list[ReasonCode] = []
    span, located = _locate(ctx, wire.locator)
    results.append(located)
    subject: dict[str, str | None] = dict(wire.subject)
    quote = wire.quote.strip() if wire.quote and wire.quote.strip() else None

    # Provisional attributes (fully built below once units are known).
    attrs: MeasurementAttributes | PageReadAttributes
    if isinstance(wire, WireMeasurement):
        attrs = MeasurementAttributes(
            attribute_key=_safe_key(wire.attribute_key),
            value_text=wire.value_text,
            unit_as_written=wire.unit,
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
        method = ExtractionMethod.MODEL_PROPOSAL
        state, vstate, reasons = _decide(results, method)
        return Decision(
            state,
            vstate,
            method,
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
        # the quote is in the span; the claimed value must be in the quote ("necessary, not sufficient")
        claimed = wire.value_text if isinstance(wire, WireMeasurement) else (wire.name or "")
        if claimed and norm_text(claimed) not in norm_text(quote):
            results.append(
                _result(
                    ValidatorName.QUOTE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.VALUE_NOT_IN_QUOTE,
                    "the quote does not contain the claimed value",
                )
            )
        else:
            results.append(_result(ValidatorName.QUOTE, ValidatorOutcome.PASSED))

    normalized: float | None = None
    if isinstance(wire, WireMeasurement):
        assert isinstance(attrs, MeasurementAttributes)
        normalized = _measurement_checks(wire, attrs, quote, span, results, warnings)
    else:
        results.append(
            _result(ValidatorName.ATTRIBUTE, ValidatorOutcome.SKIPPED, None, "page item")
        )

    if wire.__class__ is WireMeasurement and wire.effective_time_text:
        haystack = norm_text(quote or "") if quote else ""
        if not image_only and norm_text(wire.effective_time_text) not in haystack:
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
        if bore is None:
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
                    results.append(
                        _result(
                            ValidatorName.SUBJECT,
                            ValidatorOutcome.FLAGGED,
                            ReasonCode.SUBJECT_DOCUMENT_MISMATCH,
                            "the document's own records name a different wellbore",
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
                session, ctx.project_id, wellbore_id, attrs.attribute_key, normalized, span
            )
            results.append(outcome)
    del label_text

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


def _safe_key(key: str) -> str:
    """Keep the DTO constructible for a malformed key; the attribute validator then rejects it."""
    return key if re.fullmatch(r"[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+", key) else "invalid.key"


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
    if spec is None:
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

    number = parse_number(wire.value_text)
    unit = parse_unit(wire.unit)
    if wire.unit is not None and unit is None:
        results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.FAILED,
                ReasonCode.UNIT_UNPARSEABLE,
                wire.unit[:32],
            )
        )
        return None
    if number is None:
        results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.FAILED,
                ReasonCode.VALUE_NOT_IN_QUOTE,
                "no number",
            )
        )
        return None
    if unit is None:
        if spec.dimension == "length":
            unit = parse_unit("m")
            attrs.unit_defaulted = True
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
            results.append(
                _result(
                    ValidatorName.UNIT,
                    ValidatorOutcome.FAILED,
                    ReasonCode.UNIT_UNPARSEABLE,
                    "unit missing",
                )
            )
            return None
    elif unit.dimension != spec.dimension:
        results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.FAILED,
                ReasonCode.UNIT_DIMENSION_MISMATCH,
                f"{wire.unit} is {unit.dimension}, attribute needs {spec.dimension}",
            )
        )
        return None
    else:
        results.append(_result(ValidatorName.UNIT, ValidatorOutcome.PASSED))
    assert unit is not None
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

    # MD is never TVD, and a compound "MD/TVD" pair is not one value
    context = f"{quote or ''} {wire.value_text}"
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
        elif _PAIR.search(wire.value_text) and _MD.search(context) and _TVD.search(context):
            results.append(
                _result(
                    ValidatorName.DEPTH_REFERENCE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.COMPOUND_DEPTH_PAIR,
                    "an MD/TVD pair must be split into two values",
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

    if is_coordinate(key):
        crs = wire.crs_text
        haystack = norm_text(f"{quote or ''}{span.text}")
        if not crs or norm_text(crs) not in haystack:
            results.append(
                _result(
                    ValidatorName.PROVENANCE,
                    ValidatorOutcome.FLAGGED,
                    ReasonCode.CRS_NOT_STATED,
                    "no horizontal CRS stated in the source; never assumed",
                )
            )
    return normalized


__all__ = ["Decision", "ValidationContext", "validate", "norm_text"]

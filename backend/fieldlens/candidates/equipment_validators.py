"""Validators for visual-level equipment candidates (EQ-8..EQ-10, AX-13).

Every equipment candidate is ``model_read``: unverified by construction, never ``accepted``, never a
calculation input and never compared with (or able to change) a parsed value. A value outside the
plausible range, a unit that is not printed, a depth pair that is out of order and the like are
stored FLAGGED with the reason, not dropped. Only a structural failure (locator that does not
resolve, a document other than the unit's, an item that cannot be on the page) rejects.

The wellbore comes from the document's identity (TASK-046 record links), or from a caller-bound
subject that must resolve through the same identity rule and be consistent with the page text; the
model's own text never decides it."""

from __future__ import annotations

import re
from uuid import UUID

from fieldlens.contracts.candidates import (
    CandidateState,
    EquipmentAttributes,
    EquipmentQuantity,
    ExtractionMethod,
    ReasonCode,
    RejectedItemAttributes,
    ValidatorName,
    ValidatorOutcome,
    ValidatorResult,
)
from fieldlens.identity.labels import parse_bore_label
from fieldlens.identity.resolver import known_md_max
from fieldlens.persistence.session import session_scope

from .schema import InvalidItem, WireEquipment, WireQuantity
from .textmatch import parse_printed_quantity, supported_in
from .triage import keyword_score
from .units import parse_unit
from .validators import (
    LABEL_MODEL_READ,
    Decision,
    ValidationContext,
    _decide,
    _document_wellbores,
    _locate,
    _result,
    _source_names,
    _Span,
    _wellbore_names,
    association_text,
    other_wells_named,
    resolve_wellbore,
)

EQUIPMENT_VALIDATORS_VERSION = "equipment-1"
IN_TO_M = 0.0254
OD_MIN_IN, OD_MAX_IN = 0.5, 40.0  # EQ-9 plausible nominal size
MAX_LENGTH_M = 15_000.0
DEPTH_TOLERANCE = 1.05  # DC-3: the same 5% tolerance as identity resolution
_SIZE_FIELDS = ("od", "id")
_DEPTH_FIELDS = ("top_depth", "bottom_depth")
_FIELDS = ("od", "id", "length", "top_depth", "bottom_depth")


def _depth_reference(text: str | None) -> tuple[str | None, bool]:
    """(reference, compound): the printed reference text reduced to MD/TVD/TVDSS, never guessed."""
    if not text:
        return None, False
    t = text.casefold()
    has_md = "md" in t.replace("tvd", "")
    has_tvdss = "tvdss" in t
    has_tvd = "tvd" in t.replace("tvdss", "")
    kinds = [k for k, on in (("MD", has_md), ("TVD", has_tvd), ("TVDSS", has_tvdss)) if on]
    if len(kinds) > 1:
        return None, True
    return (kinds[0] if kinds else None), False


class _Flags:
    """Collects validator results for one candidate."""

    def __init__(self) -> None:
        self.results: list[ValidatorResult] = []
        self.warnings: list[ReasonCode] = []

    def flag(self, name: ValidatorName, reason: ReasonCode, detail: str) -> None:
        self.results.append(_result(name, ValidatorOutcome.FLAGGED, reason, detail))

    def ok(self, name: ValidatorName, detail: str | None = None) -> None:
        self.results.append(_result(name, ValidatorOutcome.PASSED, None, detail))


def _quantity(
    field: str,
    q: WireQuantity,
    flags: _Flags,
    *,
    md_max_m: float | None,
) -> EquipmentQuantity:
    out = EquipmentQuantity(
        value_text=q.value_text,
        unit_as_written=q.unit,
        depth_reference_text=q.reference_text,
    )
    size = field in _SIZE_FIELDS
    depth = field in _DEPTH_FIELDS

    def issue(reason: ReasonCode, name: ValidatorName, detail: str) -> EquipmentQuantity:
        out.issue = f"{field}: {detail}"[:120]
        flags.flag(name, reason, f"{field}: {detail}")
        return out

    reference, compound = _depth_reference(q.reference_text)
    if depth and (compound or re.search(r"\d\s*/\s*\d", q.value_text)):
        return issue(
            ReasonCode.COMPOUND_DEPTH_PAIR,
            ValidatorName.DEPTH_REFERENCE,
            "an MD/TVD pair is not one value; kept as printed",
        )
    out.depth_reference = reference  # type: ignore[assignment]
    printed = parse_printed_quantity(q.value_text, size=size)
    if printed.number is None:
        return issue(
            ReasonCode.SIZE_AMBIGUOUS if printed.size_ambiguous else ReasonCode.NUMBER_UNPARSEABLE,
            ValidatorName.ATTRIBUTE,
            f"{printed.problem}; not guessed",
        )
    out.number = printed.number
    if out.depth_reference is None and printed.reference_text:
        out.depth_reference_text = out.depth_reference_text or printed.reference_text
        out.depth_reference, compound = _depth_reference(printed.reference_text)  # type: ignore[assignment]
        if compound:
            return issue(
                ReasonCode.COMPOUND_DEPTH_PAIR,
                ValidatorName.DEPTH_REFERENCE,
                "an MD/TVD pair is not one value; kept as printed",
            )
    claimed = parse_unit(q.unit)
    if q.unit is not None and claimed is None:
        return issue(ReasonCode.UNIT_UNPARSEABLE, ValidatorName.UNIT, f"unit {q.unit[:16]!r}")
    written = parse_unit(printed.unit_word)
    if (
        written is not None
        and claimed is not None
        and (written.dimension, written.factor) != (claimed.dimension, claimed.factor)
    ):
        return issue(
            ReasonCode.UNIT_CONFLICTS_WITH_QUOTE,
            ValidatorName.UNIT,
            f"claimed {q.unit}, the value is printed with {printed.unit_word}",
        )
    unit = written or claimed
    if written is not None and q.unit is None:
        out.unit_as_written = printed.unit_word  # the unit as written in the value itself
    if unit is not None and unit.dimension != "length":
        return issue(
            ReasonCode.UNIT_DIMENSION_MISMATCH,
            ValidatorName.UNIT,
            f"{q.unit} is {unit.dimension}, a length is needed",
        )
    if unit is None:
        if size:
            return issue(
                ReasonCode.UNIT_NOT_IN_SOURCE,
                ValidatorName.UNIT,
                "no unit printed with the size; not assumed",
            )
        # owner decision, October 31: an unprinted depth/length unit is meters (a warning)
        unit = parse_unit("m")
        assert unit is not None
        out.unit_defaulted = True
        flags.warnings.append(ReasonCode.UNIT_DEFAULTED_METERS)
        flags.results.append(
            _result(
                ValidatorName.UNIT,
                ValidatorOutcome.PASSED,
                ReasonCode.UNIT_DEFAULTED_METERS,
                f"{field}: no unit printed; meters assumed (warning)",
            )
        )
    meters = printed.number * unit.factor
    out.normalized_number = round(meters, 6)
    out.normalized_unit = "m"
    if size:
        if not OD_MIN_IN * IN_TO_M <= meters <= OD_MAX_IN * IN_TO_M:
            return issue(
                ReasonCode.OUT_OF_RANGE,
                ValidatorName.RANGE,
                f"{meters / IN_TO_M:g} in is outside {OD_MIN_IN:g}..{OD_MAX_IN:g} in",
            )
    elif field == "length":
        if not 0 < meters <= MAX_LENGTH_M:
            return issue(
                ReasonCode.OUT_OF_RANGE, ValidatorName.RANGE, f"{meters:g} m is not a valid length"
            )
    else:
        if meters < 0 or meters > MAX_LENGTH_M:
            return issue(
                ReasonCode.OUT_OF_RANGE, ValidatorName.RANGE, f"{meters:g} m is not a valid depth"
            )
        if (
            reference in (None, "MD")
            and md_max_m is not None
            and meters > md_max_m * DEPTH_TOLERANCE
        ):
            return issue(
                ReasonCode.OUT_OF_RANGE,
                ValidatorName.RANGE,
                f"{meters:g} m MD is beyond the wellbore's known {md_max_m:g} m (+5%)",
            )
    flags.ok(ValidatorName.RANGE, field)
    return out


def _attach(ctx: ValidationContext, span: _Span, flags: _Flags) -> UUID | None:
    """EQ-10. Returns the wellbore id or None (unattached, with a finding)."""
    with session_scope(ctx.factory) as session:
        bores = _document_wellbores(session, ctx.project_id, span.doc.document_id)
        if len(bores) == 1:
            flags.ok(ValidatorName.SUBJECT, "document identity link (TASK-046)")
            return next(iter(bores))
        if len(bores) > 1:
            flags.flag(
                ValidatorName.SUBJECT,
                ReasonCode.SUBJECT_UNRESOLVED,
                f"the document links several wellbores ({_wellbore_names(session, ctx.project_id, bores)}); stays unattached",
            )
            return None
        if not ctx.document_subject:
            flags.flag(
                ValidatorName.SUBJECT,
                ReasonCode.SUBJECT_UNRESOLVED,
                "the document has no wellbore identity link; stays unattached",
            )
            return None
        bore = parse_bore_label(ctx.document_subject)
        if bore is None:
            flags.flag(
                ValidatorName.SUBJECT,
                ReasonCode.SUBJECT_UNRESOLVED,
                "the bound subject is not a well/wellbore label; stays unattached",
            )
            return None
        wellbore_id, problem = resolve_wellbore(session, ctx.project_id, bore)
        if wellbore_id is None:
            flags.flag(ValidatorName.SUBJECT, ReasonCode.SUBJECT_UNRESOLVED, problem or "unknown")
            return None
        if span.has_layer and not _source_names(ctx, span, ctx.document_subject, bore):
            other = other_wells_named(span.text, ctx.document_subject, bore)
            flags.flag(
                ValidatorName.SUBJECT,
                ReasonCode.SUBJECT_PAGE_NAMES_OTHER_WELL
                if other
                else ReasonCode.SUBJECT_UNRESOLVED,
                f"the page names {', '.join(other[:3])}, not the bound well; stays unattached"
                if other
                else "the text layer does not name the bound well; stays unattached",
            )
            return None
        flags.ok(
            ValidatorName.SUBJECT,
            "caller-bound subject resolved through the identity rule"
            + ("" if span.has_layer else "; not checkable on an image-only page"),
        )
        return wellbore_id


def validate_equipment(ctx: ValidationContext, wire: WireEquipment) -> Decision:
    flags = _Flags()
    span, located = _locate(ctx, wire.locator)
    flags.results.append(located)
    attrs = EquipmentAttributes(
        category=wire.category,
        material=wire.material,
        label_text=wire.label_text,
        description=wire.description,
        region=wire.region,
    )
    if span is not None and span.doc.document_id != ctx.document_id:
        flags.results[-1] = _result(
            ValidatorName.LOCATOR,
            ValidatorOutcome.FAILED,
            ReasonCode.LOCATOR_NOT_FOUND,
            "the locator names a document other than the unit's",
        )
        span = None
    if span is None:
        state, vstate, reasons = _decide(flags.results, ExtractionMethod.MODEL_READ)
        return Decision(
            state,
            vstate,
            ExtractionMethod.MODEL_READ,
            reasons,
            flags.results,
            None,
            {},
            attrs,
            None,
            None,
            wire.locator.document_id,
            LABEL_MODEL_READ,
        )

    # the quote check does not apply: this is a visual read, never a text claim
    flags.results.append(
        _result(
            ValidatorName.QUOTE,
            ValidatorOutcome.SKIPPED,
            ReasonCode.MODEL_READ_UNVERIFIED,
            "visual-level read: no quote to check",
        )
    )

    # equipment that cannot be on the page: a text-layer page with no equipment vocabulary at all
    # and no printed label found in it (a fabricated item on a cover/log/narrative page)
    if span.has_layer:
        in_layer = supported_in(wire.label_text, span.text) if wire.label_text else None
        attrs.label_in_text_layer = in_layer
        if in_layer is False:
            flags.flag(
                ValidatorName.PROVENANCE,
                ReasonCode.LABEL_NOT_IN_TEXT_LAYER,
                "the printed label is not in the page text layer (raster labels are possible)",
            )
        if in_layer is not True and keyword_score(span.text)[0] == 0:
            flags.results.append(
                _result(
                    ValidatorName.PROVENANCE,
                    ValidatorOutcome.FAILED,
                    ReasonCode.EQUIPMENT_NOT_ON_PAGE,
                    "the text layer has no production/completion equipment vocabulary",
                )
            )
    else:
        flags.results.append(
            _result(
                ValidatorName.PROVENANCE,
                ValidatorOutcome.SKIPPED,
                ReasonCode.MODEL_READ_UNVERIFIED,
                "image-only page: nothing to check the label against",
            )
        )

    wellbore_id = _attach(ctx, span, flags)
    md_max: float | None = None
    if wellbore_id is not None:
        with session_scope(ctx.factory) as session:
            md_max = known_md_max(session, ctx.project_id, wellbore_id)

    quantities: dict[str, EquipmentQuantity] = {}
    for field in _FIELDS:
        q: WireQuantity | None = getattr(wire, field)
        if q is not None:
            quantities[field] = _quantity(field, q, flags, md_max_m=md_max)
            setattr(attrs, field, quantities[field])
    if wellbore_id is not None and any(f in quantities for f in _DEPTH_FIELDS):
        if md_max is None:
            flags.results.append(
                _result(
                    ValidatorName.RANGE,
                    ValidatorOutcome.SKIPPED,
                    None,
                    "the wellbore has no known MD range to check depths against",
                )
            )
    _order_checks(quantities, flags)
    if span.has_layer:
        _association_checks(wire, span.text, quantities, flags)

    state, vstate, reasons = _decide(flags.results, ExtractionMethod.MODEL_READ)
    assert state is not CandidateState.ACCEPTED
    return Decision(
        state,
        vstate,
        ExtractionMethod.MODEL_READ,
        reasons,
        flags.results,
        wellbore_id,
        {},
        attrs,
        None,
        span.locator,
        span.doc.document_id,
        LABEL_MODEL_READ,
        None,
        flags.warnings,
    )


def _association_checks(
    wire: WireEquipment, text: str, q: dict[str, EquipmentQuantity], flags: _Flags
) -> None:
    """A size/depth that the text layer prints only on OTHER lines than the item's label belongs
    to another item (items mixing depths): flagged, the printed value is kept for the reader."""
    if not wire.label_text:
        return
    scope = association_text(text, wire.label_text)
    if not scope:  # label on no single line (glued or raster): nothing to associate with
        return
    for field, quantity in q.items():
        value = quantity.value_text
        if field not in _DEPTH_FIELDS:  # short sizes ("7") recur on many lines: depths only
            continue
        if supported_in(value, text) and not supported_in(value, scope):
            quantity.issue = f"{field}: printed on another line than the label"
            flags.flag(
                ValidatorName.ATTRIBUTE,
                ReasonCode.FIELD_NOT_ASSOCIATED,
                f"{field} {value} is not on the label's line (it belongs to another item)",
            )


def _order_checks(q: dict[str, EquipmentQuantity], flags: _Flags) -> None:
    od, idq = q.get("od"), q.get("id")
    if (
        od is not None
        and idq is not None
        and od.normalized_number is not None
        and idq.normalized_number is not None
        and idq.normalized_number > od.normalized_number
    ):
        idq.issue = "id: larger than the od"
        flags.flag(ValidatorName.RANGE, ReasonCode.ID_EXCEEDS_OD, "the id is larger than the od")
    top, bottom = q.get("top_depth"), q.get("bottom_depth")
    if (
        top is not None
        and bottom is not None
        and top.normalized_number is not None
        and bottom.normalized_number is not None
        and top.depth_reference == bottom.depth_reference
        and top.normalized_number > bottom.normalized_number
    ):
        bottom.issue = "bottom_depth: above the top depth"
        flags.flag(
            ValidatorName.RANGE, ReasonCode.DEPTH_ORDER_INVALID, "the top depth is below the bottom"
        )


def invalid_item_decision(
    ctx: ValidationContext,
    item: InvalidItem,
    page: int | None,
    line_range: tuple[int, int] | None,
) -> Decision:
    """An item that failed the closed item schema: stored REJECTED (model-read, unverified) with
    the bounded printed text, never as a valid candidate, never attached to a wellbore."""
    doc = ctx.reader.require(ctx.project_id, ctx.revision_id, ctx.document_id)
    base: dict[str, object] = {
        "document_id": str(doc.document_id),
        "source_revision_id": str(ctx.revision_id),
    }
    locator: dict[str, object]
    if doc.kind == "pdf":
        locator = {"kind": "pdf", "page": item.locator_page or page or 1, **base}
    else:
        start, end = line_range or (1, 1)
        locator = {"kind": "text", "line_start": start, "line_end": end, **base}
    detail = "; ".join(item.problems)[:300] or "invalid item"
    results = [
        _result(
            ValidatorName.ATTRIBUTE, ValidatorOutcome.FAILED, ReasonCode.SCHEMA_INVALID_ITEM, detail
        )
    ]
    state, vstate, reasons = _decide(results, ExtractionMethod.MODEL_READ)
    return Decision(
        state,
        vstate,
        ExtractionMethod.MODEL_READ,
        reasons,
        results,
        None,
        {},
        RejectedItemAttributes(raw_text=item.raw_text[:400], problems=list(item.problems)[:6]),
        None,
        locator,
        doc.document_id,
        LABEL_MODEL_READ,
    )


__all__ = ["validate_equipment", "invalid_item_decision", "EQUIPMENT_VALIDATORS_VERSION"]

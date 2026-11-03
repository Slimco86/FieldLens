"""Server-side validation of a ``VisualAssetSpec`` (WELLBORE_ASSET_GENERATION section 5).

The input is untrusted JSON (model output or a client). The header must be valid as a whole; each
component is validated on its own and a rejected one is DROPPED with a structured finding. Nothing
is repaired, defaulted or guessed. URLs are only checked as strings; nothing is fetched.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from fieldlens.contracts.asset_spec import (
    MAX_COMPONENTS,
    AssetComponent,
    ComponentKind,
    ComponentParams,
    FindingCode,
    LengthUnit,
    Located,
    SizeQuantity,
    SizeUnit,
    SpecFinding,
    VisualAssetSpec,
)

MAX_SPEC_BYTES = 256 * 1024
_TO_M = {SizeUnit.M: 1.0, SizeUnit.MM: 0.001, SizeUnit.IN: 0.0254, SizeUnit.FT: 0.3048}
OD_RANGE_M = (0.0127, 3.048)  # 0.5 in .. 120 in
ID_MIN_M = 0.005
LENGTH_RANGE_M = (0.01, 15_000.0)

_FULL = frozenset({"od", "id", "length"})
_SOLID = frozenset({"od", "length"})
ALLOWED_PARAMS: dict[ComponentKind, frozenset[str]] = {
    ComponentKind.CASING: _FULL,
    ComponentKind.LINER: _FULL,
    ComponentKind.TUBING: _FULL,
    ComponentKind.PACKER: _FULL,
    ComponentKind.BEARING: _FULL,
    ComponentKind.NIPPLE: _FULL,
    ComponentKind.MANDREL: _FULL,
    ComponentKind.PUMP_ESP: _SOLID,
    ComponentKind.PLUG: _SOLID,
    ComponentKind.VALVE: _SOLID,
    ComponentKind.WELLHEAD: _SOLID,
    ComponentKind.CHRISTMAS_TREE: _SOLID,
    ComponentKind.GENERIC_BLOCK: _SOLID,
    ComponentKind.SEPARATOR: _SOLID,
    ComponentKind.CHOKE: _SOLID,
    ComponentKind.MANIFOLD: _SOLID,
    ComponentKind.TANK: _SOLID,
    ComponentKind.FLOWLINE: _SOLID,
    ComponentKind.PUMP_SURFACE: _SOLID,
    ComponentKind.PERFORATION_INTERVAL: frozenset(),
}
_HEADER_DROP = ("components", "findings")


@dataclass(frozen=True)
class ValidationOutcome:
    """``spec`` is None only when the document itself is unusable (see ``findings``)."""

    spec: VisualAssetSpec | None
    findings: list[SpecFinding]


def to_metres(q: SizeQuantity) -> float:
    return q.value * _TO_M[q.unit]


def _finding(
    code: FindingCode, message: str, *, index: int | None = None, cid: str | None = None
) -> SpecFinding:
    return SpecFinding(code=code, component_id=cid, index=index, message=message[:240])


def _classify(exc: ValidationError) -> tuple[FindingCode, str]:
    text = "; ".join(str(e["msg"]) for e in exc.errors())
    if "needs evidence" in text:
        return FindingCode.MISSING_EVIDENCE, "source_dimensioned needs evidence"
    if "placement not allowed" in text:
        return FindingCode.PLACEMENT_NOT_ALLOWED, text
    if "label is blank" in text:
        return FindingCode.LABEL_EMPTY, "label is blank"
    if "never source_dimensioned" in text or "carries no numbers" in text:
        return FindingCode.GENERIC_DIMENSIONED, text
    locs = ["/".join(str(p) for p in e["loc"]) for e in exc.errors()][:3]
    return FindingCode.SCHEMA_INVALID, f"invalid at {', '.join(locs)}"


def _param_problem(kind: ComponentKind, params: ComponentParams | None) -> SpecFinding | None:
    if params is None:
        return None
    present = {n for n in ("od", "id", "length") if getattr(params, n) is not None}
    extra = present - ALLOWED_PARAMS[kind]
    if extra:
        return _finding(
            FindingCode.PARAM_NOT_ALLOWED, f"{kind.value} does not take {sorted(extra)}"
        )
    bounds = {"od": OD_RANGE_M, "id": (ID_MIN_M, OD_RANGE_M[1]), "length": LENGTH_RANGE_M}
    for name in sorted(present):
        value = to_metres(getattr(params, name))
        lo, hi = bounds[name]
        if not lo <= value <= hi:
            return _finding(FindingCode.PARAM_OUT_OF_BOUNDS, f"{name} is outside {lo}..{hi} m")
    if (
        params.od is not None
        and params.id is not None
        and to_metres(params.id) >= to_metres(params.od)
    ):
        return _finding(FindingCode.PARAM_OUT_OF_BOUNDS, "id must be below od")
    return None


def _range_problem(
    comp: AssetComponent, md_range_m: tuple[float, float] | None
) -> SpecFinding | None:
    placement = comp.placement
    if md_range_m is None or not isinstance(placement, Located):
        return None
    f = 0.3048 if placement.unit == LengthUnit.FT else 1.0
    lo, hi = md_range_m
    if placement.md_top * f < lo or placement.md_bottom * f > hi:
        return _finding(
            FindingCode.OUT_OF_MD_RANGE, f"outside the trajectory MD range {lo}..{hi} m"
        )
    return None


def validate_spec(
    raw: Mapping[str, Any] | str | bytes,
    *,
    md_range_m: tuple[float, float] | None = None,
    max_bytes: int = MAX_SPEC_BYTES,
) -> ValidationOutcome:
    """Validate an untrusted spec; invalid components are dropped with findings."""
    if isinstance(raw, str | bytes):
        if len(raw) > max_bytes:
            return ValidationOutcome(
                None, [_finding(FindingCode.SPEC_TOO_LARGE, f"larger than {max_bytes} bytes")]
            )
        try:
            doc: Any = json.loads(raw)
        except ValueError:
            return ValidationOutcome(None, [_finding(FindingCode.HEADER_INVALID, "not JSON")])
    else:
        doc = raw
        try:
            size = len(json.dumps(doc, default=str))
        except (TypeError, ValueError):
            return ValidationOutcome(None, [_finding(FindingCode.HEADER_INVALID, "not JSON")])
        if size > max_bytes:
            return ValidationOutcome(
                None, [_finding(FindingCode.SPEC_TOO_LARGE, f"larger than {max_bytes} bytes")]
            )
    if not isinstance(doc, dict):
        return ValidationOutcome(None, [_finding(FindingCode.HEADER_INVALID, "not an object")])

    header = {k: v for k, v in doc.items() if k not in _HEADER_DROP}
    try:
        base = VisualAssetSpec.model_validate({**header, "components": [], "findings": []})
    except ValidationError as exc:
        _, msg = _classify(exc)
        return ValidationOutcome(None, [_finding(FindingCode.HEADER_INVALID, msg)])

    items = doc.get("components", [])
    findings: list[SpecFinding] = []
    if not isinstance(items, list):
        return ValidationOutcome(
            None, [_finding(FindingCode.HEADER_INVALID, "components is not a list")]
        )
    if len(items) > MAX_COMPONENTS:
        findings.append(
            _finding(
                FindingCode.TOO_MANY_COMPONENTS,
                f"only the first {MAX_COMPONENTS} of {len(items)} components were considered",
            )
        )
        items = items[:MAX_COMPONENTS]

    kept: list[AssetComponent] = []
    seen: set[str] = set()
    for index, item in enumerate(items):
        cid = item.get("id") if isinstance(item, dict) and isinstance(item.get("id"), str) else None
        cid = cid[:64] if cid else None
        kind = item.get("kind") if isinstance(item, dict) else None
        if kind not in {k.value for k in ComponentKind}:
            findings.append(
                _finding(FindingCode.UNKNOWN_KIND, "unknown kind", index=index, cid=cid)
            )
            continue
        try:
            comp = AssetComponent.model_validate(item)
        except ValidationError as exc:
            code, msg = _classify(exc)
            findings.append(_finding(code, msg, index=index, cid=cid))
            continue
        if comp.id in seen:
            findings.append(
                _finding(FindingCode.DUPLICATE_ID, "duplicate component id", index=index, cid=cid)
            )
            continue
        problem = _param_problem(comp.kind, comp.params) or _range_problem(comp, md_range_m)
        if problem is not None:
            findings.append(
                problem.model_copy(update={"index": index, "component_id": comp.id[:64]})
            )
            continue
        seen.add(comp.id)
        kept.append(comp)
    spec = base.model_copy(update={"components": kept, "findings": findings[:200]})
    return ValidationOutcome(spec, findings)

"""Deterministic components from natively parsed (structured) records (WELLBORE_ASSET_GENERATION F2).

No model call. The wellbore's equipment-like ``extracted_record`` rows (linked through
``record_wellbore_link``, current runs only) become raw ``VisualAssetSpec`` components:

* dimensions only from printed numbers whose unit the parser could normalise to metres, and only
  from attributes and records the parser did not flag as conflicting/invalid/unsupported;
* ``located`` only with a complete printed MD interval (an MD point - a casing shoe - is drawn as a
  short, labelled marker, never a string length); everything else is ``unlocated``. The MD datum
  (KB/RKB/...) is stated in the note when printed and never assumed;
* ``source_dimensioned`` only when printed dimensions exist, otherwise ``generic_illustrative``
  with a "Missing: ..." comment; every component is labelled and carries evidence (document, page
  when the locator has one, and the record id/locator/extraction method in the quote);
* perforation intervals are visual markers only and never feed a perforated-length calculation.

Container records (a tubular assembly or wellbore geometry whose parts are present) add nothing of
their own; a lone container becomes one unlocated generic component.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from fieldlens.contracts.asset_spec import ComponentKind
from fieldlens.identity.tables import record_wellbore_link
from fieldlens.persistence import models as m

from .validator import ID_MIN_M, LENGTH_RANGE_M, OD_RANGE_M

MAX_STRUCTURED = 150
OD_TOL_M = 0.002
SHOE_COVER_M = 1.0
MAX_EVIDENCE = 8
_INSTALLED = ("installed", "permanent", "left in hole", "left in the hole")
_INTERVENTION = ("running tool", "spear", "fishing", "retrieving tool", "setting tool")
SHOE_MARKER_M = 1.0
KINDS = (
    "casing_point",
    "tubular_assembly",
    "tubular_component",
    "wb_geometry",
    "wb_geometry_section",
    "bha_run",
    "perforation_interval",
)
_BAD = frozenset({"conflicting", "invalid", "unsupported"})
_TUBULAR_KIND = {
    "tubing": ComponentKind.TUBING,
    "completion string": ComponentKind.TUBING,
    "casing": ComponentKind.CASING,
    "liner": ComponentKind.LINER,
    "packer": ComponentKind.PACKER,
    "nipple": ComponentKind.NIPPLE,
    "safety valve": ComponentKind.VALVE,
}
_NO_ID = frozenset({ComponentKind.VALVE})
_PIPES = frozenset(
    {ComponentKind.CASING, ComponentKind.LINER, ComponentKind.TUBING, ComponentKind.NIPPLE}
)


@dataclass
class StructuredResult:
    components: list[dict[str, Any]] = field(default_factory=list)
    containers_skipped: int = 0
    truncated: int = 0
    record_count: int = 0
    merged: int = 0  # parts folded into another structured part (shoe into its string, duplicates)
    conflicts: int = 0  # structured parts that print different ODs for the same place
    intervention_skipped: int = 0  # running tools / BHA runs: not permanent equipment
    intervention_names: list[str] = field(default_factory=list)


def _attr(attrs: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for a in attrs:
        if a.get("key") == key:
            return a
    return None


def _text(attrs: list[dict[str, Any]], key: str) -> str:
    a = _attr(attrs, key)
    if not a or a.get("validation_state") in _BAD:
        return ""
    value = a.get("text") or a.get("original_text") or ""
    return " ".join(str(value).split())[:80]


def _metres(attrs: list[dict[str, Any]], key: str) -> float | None:
    a = _attr(attrs, key)
    if not a or a.get("validation_state") in _BAD or a.get("normalized_unit") != "m":
        return None
    v = a.get("normalized_number")
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and v > 0 else None


def _depth(attrs: list[dict[str, Any]], key: str) -> float | None:
    """A printed depth in metres (zero allowed: the top of a string may be at 0)."""
    a = _attr(attrs, key)
    if not a or a.get("validation_state") in _BAD or a.get("normalized_unit") != "m":
        return None
    v = a.get("normalized_number")
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and v >= 0 else None


def _printed(attrs: list[dict[str, Any]], key: str) -> str:
    """The value as printed, with its unit (for labels)."""
    a = _attr(attrs, key)
    if not a or not a.get("original_text"):
        return ""
    unit = a.get("unit") or ""
    return f"{str(a['original_text']).strip()} {unit}".strip()


def _datum_note(attrs: list[dict[str, Any]], *keys: str) -> str:
    for key in keys:
        a = _attr(attrs, key)
        ref = str(a.get("reference") or "").strip() if a else ""
        if ref:
            return f"MD reference as printed: {ref[:40]}"
    return "MD datum not stated in the source"


def _locator_text(loc: dict[str, Any]) -> str:
    parts = []
    for key in ("page", "table_id", "cell_id", "sheet", "line", "row", "column", "element_path"):
        if loc.get(key) not in (None, ""):
            value = str(loc[key])
            parts.append(f"{key}={value[-100:]}")
    return "; ".join(parts) or json.dumps(loc, sort_keys=True, default=str)[:100]


def _dims(
    kind: ComponentKind, od: float | None, idv: float | None, length: float | None
) -> tuple[dict[str, Any], list[str]]:
    """Printed dimensions that the validator will accept; anything else is left out and named."""
    params: dict[str, Any] = {}
    missing: list[str] = []
    if od is None:
        return params, ["no printed outside diameter"]
    if not OD_RANGE_M[0] <= od <= OD_RANGE_M[1]:
        return params, ["printed outside diameter is outside the accepted range"]
    params["od"] = {"value": od, "unit": "m"}
    if kind in _PIPES or kind == ComponentKind.PACKER:
        if idv is not None and kind not in _NO_ID:
            if ID_MIN_M <= idv < od:
                params["id"] = {"value": idv, "unit": "m"}
            else:
                missing.append("printed inside diameter conflicts with the outside diameter")
    if length is not None:
        if LENGTH_RANGE_M[0] <= length <= LENGTH_RANGE_M[1]:
            params["length"] = {"value": length, "unit": "m"}
        else:
            missing.append("printed length is outside the accepted range")
    return params, missing


def _note(missing: list[str], *extra: str) -> str:
    parts = [p for p in extra if p]
    if missing:
        parts.append("Missing: " + "; ".join(missing))
    return " | ".join(parts)[:300]


@dataclass
class _Rec:
    record_id: UUID
    run_id: UUID
    document_id: UUID
    ordinal: int
    kind: str
    locator: dict[str, Any]
    validation_state: str
    attrs: list[dict[str, Any]]
    method: str

    @property
    def flagged(self) -> bool:
        return self.validation_state in _BAD

    @property
    def uids(self) -> list[str]:
        raw = self.locator.get("source_uids")
        return [str(u) for u in raw] if isinstance(raw, list) else []

    def evidence(self) -> dict[str, Any]:
        quote = (
            f"extracted_record {self.record_id} ({self.kind} #{self.ordinal}); "
            f"{self.method}; {_locator_text(self.locator)}"
        )
        ev: dict[str, Any] = {"document_id": str(self.document_id), "quote": quote[:400]}
        page = self.locator.get("page")
        if isinstance(page, int) and not isinstance(page, bool) and page >= 1:
            ev["page"] = page
        return ev


def load_records(session: Session, project_id: UUID, wellbore_id: UUID) -> list[_Rec]:
    er, ru, lk = m.extracted_record, m.extraction_run, record_wellbore_link
    order = case(*[(er.c.kind == k, i) for i, k in enumerate(KINDS)], else_=len(KINDS))
    rows = session.execute(
        select(
            er.c.record_id,
            er.c.run_id,
            er.c.document_id,
            er.c.ordinal,
            er.c.kind,
            er.c.locator,
            er.c.validation_state,
            er.c.attributes,
            ru.c.profile_name,
            ru.c.profile_version,
            ru.c.method,
        )
        .join(lk, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
        .join(ru, ru.c.run_id == er.c.run_id)
        .where(
            lk.c.project_id == project_id,
            lk.c.wellbore_id == wellbore_id,
            ru.c.superseded.is_(False),
            er.c.kind.in_(KINDS),
        )
        .order_by(order, er.c.document_id, er.c.run_id, er.c.ordinal)
        .limit(MAX_STRUCTURED * 4)
    ).all()
    return [
        _Rec(
            r.record_id,
            r.run_id,
            r.document_id,
            r.ordinal,
            r.kind,
            r.locator if isinstance(r.locator, dict) else {},
            r.validation_state,
            [a for a in (r.attributes or []) if isinstance(a, dict)],
            f"{r.profile_name or 'native'} {r.profile_version or ''} ({r.method or 'native'})".replace(
                "  ", " "
            ),
        )
        for r in rows
    ]


def has_structured(session: Session, project_id: UUID, wellbore_id: UUID) -> bool:
    er, ru, lk = m.extracted_record, m.extraction_run, record_wellbore_link
    return (
        session.execute(
            select(er.c.record_id)
            .join(lk, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
            .join(ru, ru.c.run_id == er.c.run_id)
            .where(
                lk.c.project_id == project_id,
                lk.c.wellbore_id == wellbore_id,
                ru.c.superseded.is_(False),
                er.c.kind.in_(KINDS),
            )
            .limit(1)
        ).first()
        is not None
    )


def wellbores_with_structured(session: Session, project_id: UUID) -> list[UUID]:
    er, ru, lk = m.extracted_record, m.extraction_run, record_wellbore_link
    return list(
        session.execute(
            select(lk.c.wellbore_id)
            .join(er, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
            .join(ru, ru.c.run_id == er.c.run_id)
            .where(lk.c.project_id == project_id, ru.c.superseded.is_(False), er.c.kind.in_(KINDS))
            .distinct()
        ).scalars()
    )


def _component(
    rec: _Rec,
    kind: ComponentKind,
    label: str,
    placement: dict[str, Any],
    params: dict[str, Any],
    note: str,
) -> dict[str, Any]:
    comp: dict[str, Any] = {
        "id": f"rec-{rec.record_id.hex[:12]}",
        "kind": kind.value,
        "label": " ".join(label.split())[:120] or kind.value.replace("_", " ").capitalize(),
        "placement": placement,
        "evidence": [rec.evidence()],
        "confidence_note": note,
    }
    if params and kind != ComponentKind.GENERIC_BLOCK:
        comp["representation"] = "source_dimensioned"
        comp["params"] = params
    else:
        comp["representation"] = "generic_illustrative"
    return comp


def _unlocated(reason: str) -> dict[str, Any]:
    return {"state": "unlocated", "reason": reason[:200]}


def _located(top: float | None, bottom: float | None) -> dict[str, Any] | None:
    if top is None or bottom is None or not top < bottom or bottom > 100_000:
        return None
    return {
        "state": "located",
        "md_top": top,
        "md_bottom": bottom,
        "unit": "m",
        "depth_reference": "MD",
    }


def _casing_point(rec: _Rec) -> dict[str, Any]:
    a = rec.attrs
    name = _text(a, "casing_point.name")
    md = None if rec.flagged else _depth(a, "casing_point.md")
    printed_md = _printed(a, "casing_point.md")
    label = f"{name} - shoe at {printed_md} MD" if name and printed_md else name
    label = label or (f"Casing shoe at {printed_md} MD" if printed_md else "Casing shoe")
    missing: list[str] = []
    placement = None
    if md is not None:
        placement = _located(md - SHOE_MARKER_M, md) if md >= SHOE_MARKER_M else None
    if placement is None:
        missing.append("no usable printed MD for the shoe")
        placement = _unlocated("No printed MD point for the casing shoe")
    dia = None if rec.flagged else _metres(a, "casing_point.casing_diameter")
    params, more = _dims(ComponentKind.CASING, dia, None, None)
    missing += more
    hole = _printed(a, "casing_point.hole_diameter")
    shoe = "Shoe depth printed; drawn as a short marker, not a string length"
    return _component(
        rec,
        ComponentKind.CASING,
        label,
        placement,
        params,
        _note(missing, shoe, f"hole diameter {hole}" if hole else "",
              _datum_note(a, "casing_point.md")),
    )  # fmt: skip


def _tubular_kind(type_text: str, description: str) -> ComponentKind:
    from .designer import _kind

    key = type_text.casefold().strip()
    if key in _TUBULAR_KIND:
        return _TUBULAR_KIND[key]
    return _kind("", f"{type_text} {description}")


def _tubular_component(rec: _Rec, assembly: str) -> dict[str, Any]:
    a = rec.attrs
    type_text = _text(a, "tubular_component.type_tubular_comp")
    desc = _text(a, "tubular_component.description")
    kind = _tubular_kind(type_text, desc)
    base = desc or type_text or "Tubular component"
    label = f"{base} ({assembly})" if assembly else base
    od = None if rec.flagged else _metres(a, "tubular_component.od")
    idv = None if rec.flagged else _metres(a, "tubular_component.id")
    ln = None if rec.flagged else _metres(a, "tubular_component.len")
    params, missing = _dims(kind, od, idv, ln)
    if kind == ComponentKind.GENERIC_BLOCK:
        missing.append("no matching render kind for this component type")
    top = None if rec.flagged else _depth(a, "tubular_component.md_top")
    bottom = None if rec.flagged else _depth(a, "tubular_component.md_bottom")
    placement = _located(top, bottom)
    if placement is None:
        missing.append("no complete MD interval")
        placement = _unlocated("No complete printed MD interval in the source")
    return _component(rec, kind, label, placement, params, _note(missing, "Native tubular record"))


def _tubular_assembly(rec: _Rec) -> dict[str, Any]:
    a = rec.attrs
    name = _text(a, "tubular_assembly.name") or "Tubular assembly"
    kind_text = _text(a, "tubular_assembly.type_tubular_assy")
    label = f"{name} ({kind_text})" if kind_text else name
    return _component(
        rec,
        ComponentKind.GENERIC_BLOCK,
        label,
        _unlocated("No components or MD interval printed for the assembly"),
        {},
        _note(["no component dimensions", "no MD interval"], "Native tubular record"),
    )


def _section(rec: _Rec) -> dict[str, Any]:
    a = rec.attrs
    type_text = _text(a, "wb_geometry_section.type_hole_casing")
    low = type_text.casefold()
    kind = (
        ComponentKind.LINER
        if "liner" in low
        else ComponentKind.CASING
        if "casing" in low
        else ComponentKind.GENERIC_BLOCK
    )
    top = None if rec.flagged else _depth(a, "wb_geometry_section.md_top")
    bottom = None if rec.flagged else _depth(a, "wb_geometry_section.md_bottom")
    placement = _located(top, bottom)
    p_top, p_bot = (
        _printed(a, "wb_geometry_section.md_top"),
        _printed(a, "wb_geometry_section.md_bottom"),
    )
    span = f" {p_top} - {p_bot} MD" if p_top and p_bot else ""
    name = type_text.capitalize() if kind != ComponentKind.GENERIC_BLOCK else "Hole section"
    if kind == ComponentKind.GENERIC_BLOCK and type_text:
        name = f"Hole section ({type_text})"
    missing: list[str] = []
    if placement is None:
        missing.append("no complete MD interval")
        placement = _unlocated("No complete printed MD interval in the source")
    od = None if rec.flagged else _metres(a, "wb_geometry_section.od_section")
    idv = None if rec.flagged else _metres(a, "wb_geometry_section.id_section")
    extra = ""
    if kind == ComponentKind.GENERIC_BLOCK:
        params: dict[str, Any] = {}
        printed_id = _printed(a, "wb_geometry_section.id_section")
        extra = f"hole diameter {printed_id} (label only)" if printed_id else ""
        missing.append("hole sections are drawn as a generic labelled block")
    else:
        params, more = _dims(kind, od, idv, None)
        missing += more
    return _component(
        rec,
        kind,
        f"{name}{span}",
        placement,
        params,
        _note(missing, "Native wellbore geometry record", extra,
              _datum_note(a, "wb_geometry_section.md_top", "wb_geometry_section.md_bottom")),
    )  # fmt: skip


def _geometry(rec: _Rec) -> dict[str, Any]:
    a = rec.attrs
    name = _text(a, "wb_geometry.name") or "Wellbore geometry"
    bottom = _printed(a, "wb_geometry.md_bottom")
    return _component(
        rec,
        ComponentKind.GENERIC_BLOCK,
        f"{name} (to {bottom} MD)" if bottom else name,
        _unlocated("No section intervals printed for the geometry"),
        {},
        _note(["no section intervals", "no dimensions"], "Native wellbore geometry record"),
    )


def _bha(rec: _Rec) -> dict[str, Any]:
    a = rec.attrs
    name = _text(a, "bha_run.name") or _text(a, "bha_run.num_string_run")
    label = f"BHA run {name}" if name else "BHA run"
    top = None if rec.flagged else _depth(a, "bha_run.md_start")
    bottom = None if rec.flagged else _depth(a, "bha_run.md_stop")
    placement = _located(top, bottom)
    missing = ["no printed dimensions"]
    if placement is None:
        missing.append("no complete MD interval")
        placement = _unlocated("No complete printed MD interval in the source")
    return _component(
        rec,
        ComponentKind.GENERIC_BLOCK,
        label,
        placement,
        {},
        _note(missing, "Native BHA run record"),
    )


def _perforation(rec: _Rec) -> dict[str, Any]:
    a = rec.attrs
    top = None if rec.flagged else _depth(a, "perforation.top_md")
    bottom = None if rec.flagged else _depth(a, "perforation.base_md")
    placement = _located(top, bottom)
    formation = _text(a, "perforation.formation")
    p_top, p_bot = _printed(a, "perforation.top_md"), _printed(a, "perforation.base_md")
    span = f" {p_top} - {p_bot} MD" if p_top and p_bot else ""
    label = f"Perforation{' ' + formation if formation else ''}{span}"
    missing: list[str] = []
    notes = ["Visual marker only; not used for perforated-length analysis"]
    ref = str((_attr(a, "perforation.top_md") or {}).get("reference") or "")
    if ref.startswith("assumed"):
        notes.append("depth unit not stated in the source; metres assumed by the parser")
    if placement is None:
        missing.append("no complete MD interval")
        placement = _unlocated("No complete printed MD interval in the source")
    comp = _component(rec, ComponentKind.PERFORATION_INTERVAL, label, placement, {}, "")
    comp["representation"] = (
        "source_dimensioned" if placement["state"] == "located" else "generic_illustrative"
    )
    comp["confidence_note"] = _note(missing, *notes)
    return comp


def _intervention(rec: _Rec) -> bool:
    """A BHA run, or a tubular component that is a running/fishing tool, is an intervention tool
    (it was run and pulled), unless a record text marks it installed/permanent."""
    text = " ".join(
        str(a.get("original_text") or "") for a in rec.attrs if isinstance(a, dict)
    ).casefold()
    if any(w in text for w in _INSTALLED):
        return False
    return rec.kind == "bha_run" or any(w in text for w in _INTERVENTION)


def _intervention_name(rec: _Rec) -> str:
    if rec.kind == "bha_run":
        return "BHA run"
    for key in (
        "tubular_component.type",
        "tubular_component.description",
        "tubular_component.name",
    ):
        v = _text(rec.attrs, key)
        if v:
            return v[:40]
    return "intervention tool"


def _od(comp: dict[str, Any]) -> float | None:
    od = (comp.get("params") or {}).get("od")
    return float(od["value"]) if isinstance(od, dict) else None


def _span(comp: dict[str, Any]) -> tuple[float, float] | None:
    p = comp["placement"]
    return (p["md_top"], p["md_bottom"]) if p.get("state") == "located" else None


def _bottom(comp: dict[str, Any], md: float) -> bool:
    span = _span(comp)
    return span is not None and abs(span[1] - md) <= SHOE_COVER_M


def _join(keep: dict[str, Any], other: dict[str, Any]) -> None:
    for ev in other["evidence"]:
        if ev not in keep["evidence"] and len(keep["evidence"]) < MAX_EVIDENCE:
            keep["evidence"].append(ev)


def _flag(comp: dict[str, Any], text: str) -> None:
    comp["confidence_note"] = " | ".join(p for p in (comp["confidence_note"], text) if p)[:300]


_PIPE_VALUES = frozenset({ComponentKind.CASING.value, ComponentKind.LINER.value})


def _fold(pairs: list[tuple[_Rec, dict[str, Any]]], out: StructuredResult) -> list[dict[str, Any]]:
    """One component per string: a casing shoe at a section's bottom is folded into that section
    (label, evidence); an equal-OD duplicate of the same interval joins its evidence; different
    ODs keep both parts and are counted as a conflict. A shoe with no covering section stays."""
    drop: set[int] = set()
    sections = [
        (i, c)
        for i, (r, c) in enumerate(pairs)
        if r.kind == "wb_geometry_section" and c["kind"] in _PIPE_VALUES and _span(c)
    ]
    for i, (rec, comp) in enumerate(pairs):
        if rec.kind != "casing_point" or (span := _span(comp)) is None:
            continue
        md = span[1]
        cover = [(j, c) for j, c in sections if j not in drop and _bottom(c, md)]
        if not cover:
            continue
        shoe_od = _od(comp)
        same = [
            (j, c) for j, c in cover if shoe_od is None or abs((_od(c) or -1) - shoe_od) <= OD_TOL_M
        ]
        if not same:
            out.conflicts += 1
            for _, c in cover:
                _flag(c, "Conflict: the casing shoe record prints a different OD; both are shown")
            _flag(comp, "Conflict: the covering section prints a different OD; both are shown")
            continue
        j, sec = same[0]
        name = _text(rec.attrs, "casing_point.name")
        printed = _printed(rec.attrs, "casing_point.md") or f"{md:g} m"
        base = name or sec["label"].split(" ")[0]
        sec["label"] = f"{base}, shoe {printed}"[:120]
        _join(sec, comp)
        _flag(sec, "Shoe record folded into this string")
        drop.add(i)
        out.merged += 1
    # equal-OD duplicates of one located interval (e.g. a section and a tubular component)
    live = [i for i in range(len(pairs)) if i not in drop]
    for a_idx, i in enumerate(live):
        ci = pairs[i][1]
        if i in drop or ci["kind"] not in _PIPE_VALUES or not _span(ci) or _od(ci) is None:
            continue
        for k in live[a_idx + 1 :]:
            ck = pairs[k][1]
            if k in drop or ck["kind"] != ci["kind"] or not _span(ck) or _od(ck) is None:
                continue
            (t1, b1), (t2, b2) = _span(ci), _span(ck)  # type: ignore[misc]
            if (
                abs(_od(ci) - _od(ck)) <= OD_TOL_M  # type: ignore[operator]
                and abs(t1 - t2) <= SHOE_COVER_M
                and abs(b1 - b2) <= SHOE_COVER_M
            ):
                _join(ci, ck)
                drop.add(k)
                out.merged += 1
    return [c for i, (_, c) in enumerate(pairs) if i not in drop]


def components_from_records(records: list[_Rec]) -> StructuredResult:
    out = StructuredResult(record_count=len(records))
    sections_runs = {r.run_id for r in records if r.kind == "wb_geometry_section"}
    comp_parents = {
        (r.run_id, tuple(r.uids[:-1])) for r in records if r.kind == "tubular_component"
    }
    assemblies = {
        (r.run_id, tuple(r.uids)): _text(r.attrs, "tubular_assembly.name")
        for r in records
        if r.kind == "tubular_assembly"
    }
    pairs: list[tuple[_Rec, dict[str, Any]]] = []
    for rec in records:
        if rec.kind in ("bha_run", "tubular_component") and _intervention(rec):
            out.intervention_skipped += 1
            out.intervention_names.append(_intervention_name(rec))
            continue
        if rec.kind == "casing_point":
            comp = _casing_point(rec)
        elif rec.kind == "tubular_component":
            comp = _tubular_component(rec, assemblies.get((rec.run_id, tuple(rec.uids[:-1])), ""))
        elif rec.kind == "tubular_assembly":
            if (rec.run_id, tuple(rec.uids)) in comp_parents:
                out.containers_skipped += 1
                continue
            comp = _tubular_assembly(rec)
        elif rec.kind == "wb_geometry_section":
            comp = _section(rec)
        elif rec.kind == "wb_geometry":
            if rec.run_id in sections_runs:
                out.containers_skipped += 1
                continue
            comp = _geometry(rec)
        elif rec.kind == "bha_run":
            comp = _bha(rec)
        else:
            comp = _perforation(rec)
        pairs.append((rec, comp))
    folded = _fold(pairs, out)
    for comp in folded:
        if len(out.components) >= MAX_STRUCTURED:
            out.truncated += 1
            continue
        out.components.append(comp)
    return out


def structured_components(
    session: Session, project_id: UUID, wellbore_id: UUID
) -> StructuredResult:
    records = load_records(session, project_id, wellbore_id)
    out = components_from_records(records)
    if len(records) >= MAX_STRUCTURED * 4:  # the read itself was capped: say so, never hide it
        out.truncated += 1
    return out

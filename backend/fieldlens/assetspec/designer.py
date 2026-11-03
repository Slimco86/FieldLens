"""Deterministic stub designer: a raw ``VisualAssetSpec`` dict from a wellbore's equipment candidates.

No model call. Nothing is invented: a candidate becomes a component only with what it states.
Depth is ``located`` only when top and bottom are printed with an explicit MD reference; otherwise
``unlocated``. Dimensions are carried (in metres, from the candidate's normalized numbers) only when
the candidate has an OD, else the component is a labelled ``generic_illustrative`` without numbers.
The candidates stay ``model_read`` evidence; the spec is visual only.

Limitation: only equipment candidates (TASK-041) are used; parsed records are not yet mapped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldlens.contracts.asset_spec import SURFACE_KINDS, ComponentKind
from fieldlens.persistence import models as m

STUB_PROVIDER = "stub"
STUB_MODEL = "stub-designer-1"
MAX_CANDIDATES = 200

_CATEGORY_KIND = {
    "casing": ComponentKind.CASING,
    "liner": ComponentKind.LINER,
    "tubing": ComponentKind.TUBING,
    "packer": ComponentKind.PACKER,
    "pump": ComponentKind.PUMP_ESP,
    "bearing": ComponentKind.BEARING,
    "perforation_interval": ComponentKind.PERFORATION_INTERVAL,
    "isolation": ComponentKind.PLUG,
}
# words in the printed label/description that pick a kind for the loose categories
_KEYWORDS: tuple[tuple[str, ComponentKind], ...] = (
    ("christmas", ComponentKind.CHRISTMAS_TREE),
    ("xmas", ComponentKind.CHRISTMAS_TREE),
    ("wellhead", ComponentKind.WELLHEAD),
    ("separator", ComponentKind.SEPARATOR),
    ("manifold", ComponentKind.MANIFOLD),
    ("choke", ComponentKind.CHOKE),
    ("flowline", ComponentKind.FLOWLINE),
    ("tank", ComponentKind.TANK),
    ("nipple", ComponentKind.NIPPLE),
    ("mandrel", ComponentKind.MANDREL),
    ("valve", ComponentKind.VALVE),
)
_NO_ID = frozenset({ComponentKind.PUMP_ESP, ComponentKind.PLUG, ComponentKind.VALVE})
_SOLID_ONLY = frozenset(
    {
        ComponentKind.PUMP_ESP,
        ComponentKind.PLUG,
        ComponentKind.VALVE,
        ComponentKind.WELLHEAD,
        ComponentKind.CHRISTMAS_TREE,
        ComponentKind.GENERIC_BLOCK,
        *SURFACE_KINDS,
    }
)


def _kind(category: str, text: str) -> ComponentKind:
    if category in _CATEGORY_KIND:
        return _CATEGORY_KIND[category]
    low = text.casefold()
    for word, kind in _KEYWORDS:
        if word in low:
            return kind
    return ComponentKind.GENERIC_BLOCK


def _metres(q: dict[str, Any] | None, *, minimum: float = 0.0) -> float | None:
    if not q or q.get("normalized_unit") != "m":
        return None
    v = q.get("normalized_number")
    return float(v) if isinstance(v, int | float) and v > minimum else None


def _label(attrs: dict[str, Any], row_label: str, kind: ComponentKind) -> str:
    for cand in (attrs.get("label_text"), attrs.get("description"), row_label):
        if isinstance(cand, str) and cand.strip():
            return cand.strip()[:120]
    return kind.value.replace("_", " ").capitalize()


def candidate_text(row: Any) -> str:
    attrs: dict[str, Any] = row["attributes"]
    return f"{attrs.get('label_text') or ''} {attrs.get('description') or ''}".strip()


def component_for(row: Any, kind_override: ComponentKind | None = None) -> dict[str, Any]:
    """Deterministic component for one candidate (kind may be chosen by the live designer)."""
    attrs: dict[str, Any] = row["attributes"]
    text = candidate_text(row)
    kind = kind_override or _kind(str(attrs.get("category")), text)
    cid = f"cand-{row['candidate_id'].hex[:12]}"
    evidence: dict[str, Any] = {
        "candidate_id": str(row["candidate_id"]),
        "document_id": str(row["document_id"]),
    }
    page = (row["locator"] or {}).get("page")
    if isinstance(page, int) and page >= 1:
        evidence["page"] = page
    if row["quote"]:
        evidence["quote"] = str(row["quote"])[:400]

    if kind in SURFACE_KINDS or kind in (ComponentKind.WELLHEAD, ComponentKind.CHRISTMAS_TREE):
        placement: dict[str, Any] = {"state": "surface"}
    else:
        top, bottom = attrs.get("top_depth"), attrs.get("bottom_depth")
        t, b = _metres(top, minimum=-1.0), _metres(bottom)
        md = (
            top
            and bottom
            and top.get("depth_reference") == "MD"
            and bottom.get("depth_reference") == "MD"
        )
        if md and t is not None and b is not None and t < b:
            placement = {
                "state": "located",
                "md_top": t,
                "md_bottom": b,
                "unit": "m",
                "depth_reference": "MD",
            }
        else:
            placement = {"state": "unlocated", "reason": "No complete MD interval in the source"}

    od = _metres(attrs.get("od"))
    params: dict[str, Any] = {}
    if od is not None and kind != ComponentKind.PERFORATION_INTERVAL:
        params["od"] = {"value": od, "unit": "m"}
        idv = _metres(attrs.get("id"))
        if idv is not None and kind not in _SOLID_ONLY and kind not in _NO_ID:
            params["id"] = {"value": idv, "unit": "m"}
        ln = _metres(attrs.get("length"))
        if ln is not None:
            params["length"] = {"value": ln, "unit": "m"}
    comp: dict[str, Any] = {
        "id": cid,
        "kind": kind.value,
        "label": _label(attrs, str(row["label"] or ""), kind),
        "placement": placement,
        "evidence": [evidence],
        "confidence_note": "Read by a model from a page; unverified, visual only.",
    }
    if params or kind == ComponentKind.PERFORATION_INTERVAL and placement["state"] == "located":
        comp["representation"] = "source_dimensioned"
        if params:
            comp["params"] = params
    else:
        comp["representation"] = "generic_illustrative"
    return comp


def _component(row: Any) -> dict[str, Any]:
    return component_for(row)


def header(session: Session, project_id: UUID, wellbore_id: UUID) -> dict[str, Any]:
    proj = session.execute(
        select(m.project.c.latest_source_revision_id, m.project.c.active_model_revision_id).where(
            m.project.c.project_id == project_id
        )
    ).one()
    return {
        "project_id": str(project_id),
        "wellbore_id": str(wellbore_id),
        "source_revision": str(proj[0]) if proj[0] else "none",
        "identity_revision": str(proj[1]) if proj[1] else None,
        "spec_version": "1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "current",
        "visual_only": True,
    }


def candidate_rows(session: Session, project_id: UUID, wellbore_id: UUID) -> list[Any]:
    from fieldlens.candidates.tables import extraction_candidate as c

    return list(
        session.execute(
            select(
                c.c.candidate_id,
                c.c.document_id,
                c.c.attributes,
                c.c.locator,
                c.c.quote,
                c.c.label,
            )
            .where(
                c.c.project_id == project_id,
                c.c.wellbore_id == wellbore_id,
                c.c.state != "rejected",
                c.c.attributes["kind"].astext == "equipment",
            )
            .order_by(c.c.created_at, c.c.candidate_id)
            .limit(MAX_CANDIDATES)
        )
        .mappings()
        .all()
    )


def design(session: Session, project_id: UUID, wellbore_id: UUID) -> dict[str, Any]:
    """Raw (unvalidated) spec for one wellbore; the caller validates and persists it."""
    rows = candidate_rows(session, project_id, wellbore_id)
    return {
        **header(session, project_id, wellbore_id),
        "generator": {"provider": STUB_PROVIDER, "model": STUB_MODEL},
        "components": [component_for(r) for r in rows],
    }

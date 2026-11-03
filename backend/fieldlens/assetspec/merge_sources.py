"""Cross-source reconciliation for S5 (spec §15/§16 F2b): structured records vs model-read items.

When a structured component and a model-read component describe the same place (same kind, MD
intervals that overlap) and print a different value for the same dimension, the sources conflict.
Nothing is chosen or averaged: both parts are shown as labelled generic shapes without dimensions,
the confidence note says which values disagree, and the conflict is counted for the stage message.
Generic values never feed engineering calculations (the spec is visual only)."""

from __future__ import annotations

from typing import Any

REL_TOLERANCE = 0.02  # printed rounding (e.g. 9 5/8 in vs 244.5 mm) is not a conflict
_DIMS = ("od", "id", "length")


def _interval(comp: dict[str, Any]) -> tuple[float, float] | None:
    p = comp.get("placement") or {}
    if p.get("state") != "located":
        return None
    return float(p["md_top"]), float(p["md_bottom"])


def _value(comp: dict[str, Any], name: str) -> float | None:
    q = (comp.get("params") or {}).get(name)
    if not isinstance(q, dict) or q.get("unit") != "m":
        return None
    try:
        return float(q["value"])
    except (KeyError, TypeError, ValueError):
        return None


def _generic(comp: dict[str, Any], note: str) -> dict[str, Any]:
    out = {k: v for k, v in comp.items() if k not in ("params", "visual_reference")}
    out["representation"] = "generic_illustrative"
    out["confidence_note"] = note[:300]
    return out


def _disagreements(a: dict[str, Any], b: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for name in _DIMS:
        va, vb = _value(a, name), _value(b, name)
        if va is None or vb is None:
            continue
        if abs(va - vb) > REL_TOLERANCE * max(va, vb):
            out.append(f"{name} {va:g} m vs {vb:g} m")
    return out


def reconcile(
    structured: list[dict[str, Any]], model_read: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Returns (structured, model_read, conflict_count); conflicted parts are demoted to generic."""
    s_out, m_out = list(structured), list(model_read)
    conflicts = 0
    for i, s in enumerate(s_out):
        si = _interval(s)
        if si is None or not s.get("params"):
            continue
        for j, m in enumerate(m_out):
            mi = _interval(m)
            if mi is None or not m.get("params") or m["kind"] != s["kind"]:
                continue
            if min(si[1], mi[1]) <= max(si[0], mi[0]):
                continue  # intervals do not overlap
            diff = _disagreements(s_out[i], m_out[j])
            if not diff:
                continue
            conflicts += 1
            text = "; ".join(diff)
            s_out[i] = _generic(
                s_out[i],
                f"Missing: agreed dimensions. Sources conflict ({text}; structured record vs "
                "model-read item); none chosen.",
            )
            m_out[j] = _generic(
                m_out[j],
                f"Missing: agreed dimensions. Sources conflict ({text}; model-read item vs "
                "structured record); none chosen.",
            )
            break  # the structured part is generic now; later pairs have nothing to compare
    return s_out, m_out, conflicts

"""Offline scoring of spike runs against the AGENT-READ reference (not human verified)."""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from typing import Any

from spike042_common import SCRATCH
from spike042_gold import CONTROLS, GOLD

TYPES = set(
    "tubing casing liner packer safety_valve gauge mandrel hanger seal_assembly wellhead "
    "xmas_tree pup_joint crossover plug pump bearing motor gas_lift_valve control_line "
    "other_completion".split()
)
KINDS = {
    "completion_schematic",
    "completion_table",
    "completion_narrative",
    "drilling_narrative",
    "bha_list",
    "geological_log",
    "cover_or_toc",
    "chart",
    "other",
}
CAND_KEYS = {"type", "name", "od", "id", "length", "depth", "qty", "ident", "state", "quote"}


def parse_json(text: str) -> tuple[dict[str, Any] | None, str]:
    """Returns (object, how) where how is 'strict', 'fenced' or 'failed'."""
    try:
        obj = json.loads(text)
        return (obj, "strict") if isinstance(obj, dict) else (None, "failed")
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj, "fenced"
        except json.JSONDecodeError:
            pass
    return None, "failed"


def schema_problems(obj: dict[str, Any]) -> list[str]:
    bad: list[str] = []
    if obj.get("page_kind") not in KINDS:
        bad.append("page_kind")
    if not isinstance(obj.get("well_names_printed"), list):
        bad.append("well_names_printed")
    cands = obj.get("candidates")
    if not isinstance(cands, list):
        return [*bad, "candidates"]
    for i, c in enumerate(cands):
        if not isinstance(c, dict):
            bad.append(f"cand{i}:notobject")
            continue
        if c.get("type") not in TYPES:
            bad.append(f"cand{i}:type={c.get('type')}")
        missing = CAND_KEYS - set(c)
        if missing:
            bad.append(f"cand{i}:missing={sorted(missing)}")
        d = c.get("depth")
        if not isinstance(d, dict) or not {"value", "unit", "reference"} <= set(d):
            bad.append(f"cand{i}:depth")
    if not isinstance(obj.get("perforations"), list):
        bad.append("perforations")
    return bad


def norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9.]+", "", str(s).lower().replace(",", "."))


def flat(c: dict[str, Any]) -> str:
    d = c.get("depth") if isinstance(c.get("depth"), dict) else {}
    return norm(
        " ".join(str(v) for v in [*c.values(), *(d or {}).values()] if not isinstance(v, dict))
    )


def num(s: Any) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(s))
    return float(m.group(0).replace(",", ".")) if m else None


def ref_tokens(s: Any) -> set[str]:
    return {t for t in re.split(r"[^a-z]+", str(s).lower()) if t}


def usable_keys(g: dict[str, Any], strict: bool) -> list[str]:
    """Keys that identify a reference item. Lenient: all keys (possibly none). Strict: only keys
    of 4+ normalised characters, else the printed depth value; items with neither are
    not eligible for strict matching."""
    keys = [norm(k) for k in g["keys"]]
    if not strict:
        return keys
    long_keys = [k for k in keys if len(k) >= 4]
    if long_keys:
        return long_keys
    depth = g["attrs"].get("depth")
    return [norm(depth)] if depth else []


def match_items(
    gold: list[dict[str, Any]], preds: list[dict[str, Any]], strict: bool = False
) -> tuple[list[tuple[int, int]], dict[int, int]]:
    """Greedy match: same group and any usable key in the flattened candidate (lenient mode: an
    item without keys matches any candidate of its type). Returns pairs and type-confused pairs
    (gold idx -> pred idx) where only keys match."""
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    confused: dict[int, int] = {}
    for gi, g in enumerate(gold):
        keys = usable_keys(g, strict)
        if strict and not keys:
            continue
        best, score = None, -1
        for pi, p in enumerate(preds):
            if pi in used or p.get("type") != g["group"]:
                continue
            hits = sum(1 for k in keys if k and k in flat(p))
            if keys and hits == 0:
                continue
            if hits > score:
                best, score = pi, hits
        if best is not None:
            used.add(best)
            pairs.append((gi, best))
    for gi, g in enumerate(gold):
        if any(gi == a for a, _ in pairs):
            continue
        keys = usable_keys(g, strict)
        for pi, p in enumerate(preds):
            if pi in used:
                continue
            if keys and any(k and k in flat(p) for k in keys) and p.get("type") != g["group"]:
                confused[gi] = pi
                break
    return pairs, confused


def attr_check(g: dict[str, Any], p: dict[str, Any]) -> dict[str, str]:
    """Per-attribute verdicts: ok / wrong / missing / converted / md_tvd_confusion."""
    out: dict[str, str] = {}
    a = g["attrs"]
    d = p.get("depth") if isinstance(p.get("depth"), dict) else {}
    if "depth" in a:
        gv, pv = num(a["depth"]), num((d or {}).get("value"))
        if pv is None:
            out["depth"] = "missing"
        elif gv is not None and abs(gv - pv) < 1e-6:
            out["depth"] = "ok"
        elif gv and (abs(pv - gv * 3.28084) < 1 or abs(pv - gv / 3.28084) < 1):
            out["depth"] = "converted"
        else:
            out["depth"] = "wrong"
        pu = str((d or {}).get("unit", "")).lower()
        out["depth_unit"] = (
            "ok"
            if pu.startswith("m") and not pu.startswith("mm")
            else ("missing" if pu in ("", "unknown") else "wrong")
        )
    if "ref" in a:
        gt, pt = ref_tokens(a["ref"]), ref_tokens((d or {}).get("reference", ""))
        if "unspecified" in pt or not pt or "unknown" in pt:
            out["depth_ref"] = "missing"
        elif gt <= pt:
            out["depth_ref"] = "ok"
        elif "tvd" in pt and "md" in gt and "md" not in pt:
            out["depth_ref"] = "md_tvd_confusion"
        else:
            out["depth_ref"] = "wrong"
    for k in ("od", "id"):
        if k in a:
            gv, pv = num(a[k]), num(p.get(k))
            if pv is None:
                out[k] = "missing"
            elif gv is not None and abs(gv - pv) < 1e-6:
                out[k] = "ok"
            elif gv and abs(pv - gv * 25.4) < 1:
                out[k] = "converted"
            else:
                out[k] = "wrong"
    return out


def score_perfs(gold: list[dict[str, str]], preds: list[dict[str, Any]]) -> tuple[int, int, int]:
    hit = 0
    used: set[int] = set()
    for g in gold:
        for i, p in enumerate(preds):
            if i in used:
                continue
            if num(p.get("top")) == num(g["top"]) and num(p.get("bottom")) == num(g["bottom"]):
                used.add(i)
                hit += 1
                break
    return hit, len(gold), len(preds)


def load_text_layer(pv: str, page: int) -> str:
    f = SCRATCH / f"text_{pv}.json"
    if not f.exists():
        return ""
    return str(json.loads(f.read_text())[page - 1])


def score_record(rec: dict[str, Any]) -> dict[str, Any]:
    key = f"{rec['pv']}:{rec['page']}"
    out: dict[str, Any] = {
        "key": key,
        "mode": rec["mode"],
        "effort": rec["effort"],
        "long_side": rec.get("long_side"),
        "outcome": rec["outcome"],
    }
    u = (rec.get("usage") or [{}])[-1].get("usage") or {}
    out["in_tok"], out["out_tok"] = u.get("input_tokens"), u.get("output_tokens")
    out["reason_tok"] = (u.get("output_tokens_details") or {}).get("reasoning_tokens")
    out["cost"] = rec.get("committed_usd")
    out["elapsed_s"] = rec.get("elapsed_s")
    if rec["outcome"] != "ok":
        return out
    obj, how = parse_json(rec["text"])
    out["json"] = how
    if obj is None:
        return out
    probs = schema_problems(obj)
    out["schema_ok"] = not probs
    out["schema_problems"] = probs[:5]
    cands = [c for c in obj.get("candidates", []) if isinstance(c, dict)]
    perfs = [c for c in obj.get("perforations", []) if isinstance(c, dict)]
    out["n_cand"], out["n_perf"] = len(cands), len(perfs)
    out["page_kind"] = obj.get("page_kind")
    out["wells"] = obj.get("well_names_printed")
    layer = norm(load_text_layer(rec["pv"], rec["page"]))
    if layer:
        q = [norm(c.get("quote", "")) for c in cands]
        out["quote_in_layer"] = sum(1 for x in q if x and x in layer)
        out["quote_total"] = len(q)
    if key in GOLD:
        g = GOLD[key]["items"]
        pairs, confused = match_items(g, cands)
        sure = [i for i, x in enumerate(g) if not x["unsure"]]
        hit_sure = [gi for gi, _ in pairs if gi in sure]
        out["gold_sure"], out["tp_sure"] = len(sure), len(hit_sure)
        spairs, _ = match_items(g, cands, strict=True)
        elig = [i for i in sure if usable_keys(g[i], True)]
        out["strict_eligible"] = len(elig)
        out["tp_strict"] = len([gi for gi, _ in spairs if gi in elig])
        out["gold_unsure"] = len(g) - len(sure)
        out["tp_unsure"] = len([gi for gi, _ in pairs if gi not in sure])
        out["pred_matched"] = len(pairs)
        out["extra_preds"] = [
            f"{c.get('type')}|{str(c.get('name'))[:40]}"
            for i, c in enumerate(cands)
            if i not in {pi for _, pi in pairs}
        ]
        out["type_confused"] = {g[a]["name"]: cands[b].get("type") for a, b in confused.items()}
        attrs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for gi, pi in pairs:
            for k, v in attr_check(g[gi], cands[pi]).items():
                attrs[k][v] += 1
        out["attrs"] = {k: dict(v) for k, v in attrs.items()}
        out["perf"] = score_perfs(GOLD[key]["perforations"], perfs)
        out["missed"] = [x["name"] for i, x in enumerate(g) if i not in {a for a, _ in pairs}]
    elif key in CONTROLS:
        out["control_kind"] = CONTROLS[key]["kind"]
        out["control_perfs"] = len(perfs)
        out["control_cands"] = [f"{c.get('type')}|{str(c.get('name'))[:50]}" for c in cands]
    return out


def main() -> None:
    tags = sys.argv[1:]
    rows = []
    for tag in tags:
        for f in sorted((SCRATCH / "runs" / tag).glob("*.json")):
            rec = json.loads(f.read_text())
            row = score_record(rec)
            row["tag"] = tag
            rows.append(row)
    print(json.dumps(rows, indent=1, default=str))


if __name__ == "__main__":
    main()

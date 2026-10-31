"""Offline analysis of the "OCR token must agree with the model image read" rule (TASK-030 A).

Inputs: saved TASK-042 spike model outputs (read only, no provider call) and saved OCR results.
Values are compared after the ocr_common normalization (decimals by value, fractions as text).
The reference is the agent-read spike gold (not human verified, not exhaustive), so categories
are: ref_match (value is a reference number), suspected_misread (not a reference number but one
digit away from one of the same length) and unjudged (neither; cannot be called right or wrong).
"""

from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ocr_common import (
    ALL_PAGES,
    SPIKE042_RUNS,
    edit_distance,
    num_class,
    numbers_in,
    reference_tokens,
)
from ocr_score import load, merge

PAGES = {f"{pv}:{p}" for pv, p in ALL_PAGES}


def model_values(path: str) -> tuple[set[str], set[str]] | None:
    d = json.loads(Path(path).read_text())
    if d.get("outcome") != "ok":
        return None
    try:
        cands = json.loads(d["text"]).get("candidates", [])
    except (ValueError, KeyError):
        return None
    structured: set[str] = set()
    descriptive: set[str] = set()
    for c in cands:
        dep = c.get("depth") or {}
        for v in (
            c.get("od"),
            c.get("id"),
            c.get("length"),
            dep.get("value") if isinstance(dep, dict) else None,
        ):
            if isinstance(v, str):
                structured.update(numbers_in(v))
        for v in (c.get("name"), c.get("quote"), c.get("ident")):
            if isinstance(v, str):
                descriptive.update(numbers_in(v))
    return structured, descriptive - structured


def classify(v: str, ref: set[str]) -> str:
    if v in ref:
        return "ref_match"
    if num_class(v) != "int<3" and any(len(r) == len(v) and edit_distance(r, v) == 1 for r in ref):
        return "suspected_misread"
    return "unjudged"


def mutants(n: str) -> set[str]:
    """Every single-digit substitution of a numeric string (fractions included)."""
    out: set[str] = set()
    for i, ch in enumerate(n):
        if ch.isdigit():
            out.update(n[:i] + d + n[i + 1 :] for d in "0123456789" if d != ch)
    return {m for m in out if not (m.startswith("0") and len(m) > 1 and m[1] != ".")}


def coincidence(ocr: dict[str, set[str]]) -> None:
    """How often a wrong one-digit variant of a reference number is also an OCR token on the page.

    This estimates the chance that a model misread would be wrongly confirmed by coincidence.
    """
    tot: Counter[str] = Counter()
    hit: Counter[str] = Counter()
    for pv, page in ALL_PAGES:
        key = f"{pv}:{page}"
        refs = set(reference_tokens(key)["numbers"])
        for r in refs:
            cls = num_class(r)
            for m in mutants(r) - refs:
                tot[cls] += 1
                hit[cls] += m in ocr[key]
    print(
        "\ncoincidental confirmation of one-digit wrong variants (wrong value found in page OCR):"
    )
    for cls in sorted(tot):
        print(f"  {cls:10} {hit[cls]}/{tot[cls]} ({100 * hit[cls] / tot[cls]:.2f}%)")


def main() -> None:
    tag, dpi, angles, mc = (
        sys.argv[1],
        int(sys.argv[2]),
        [int(a) for a in sys.argv[3].split(",")],
        float(sys.argv[4]),
    )
    ocr: dict[str, set[str]] = {}
    for pv, page in ALL_PAGES:
        toks, _ = load(tag, dpi, pv, page, angles)
        ocr[f"{pv}:{page}"] = {n for t in merge(toks, mc) for n in numbers_in(t["t"])}
    coincidence(ocr)
    tally: dict[str, Counter[str]] = {"structured": Counter(), "descriptive": Counter()}
    ref_total: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []
    for f in sorted(glob.glob(str(SPIKE042_RUNS / "*" / "*_image.json"))):
        base = Path(f).name  # PV-17_p036_image.json
        key = f"{base[:5]}:{int(base[7:10])}"
        if key not in PAGES:
            continue
        mv = model_values(f)
        if mv is None:
            continue
        refs = (
            set(reference_tokens(key)["numbers"])
            if key in {f"{p}:{n}" for p, n in ALL_PAGES} and reference_tokens(key)["numbers"]
            else set()
        )
        cfg = Path(f).parent.name
        for kind, vals in zip(("structured", "descriptive"), mv, strict=True):
            for v in vals:
                cat = classify(v, refs) if refs else "unjudged"
                conf = v in ocr[key]
                tally[kind][f"{cat}|{'confirmed' if conf else 'unconfirmed'}"] += 1
                rows.append(
                    {"run": cfg, "page": key, "kind": kind, "v": v, "cat": cat, "confirmed": conf}
                )
        if refs:
            ref_total["ref_numbers_seen"] += len(refs)
            ref_total["model_read_ref"] += len(refs & (mv[0] | mv[1]))
            ref_total["accepted_ref"] += len(refs & (mv[0] | mv[1]) & ocr[key])
    print(f"OCR config: {tag} dpi={dpi} angles={angles} min_conf={mc}")
    for kind, c in tally.items():
        n = sum(c.values())
        n_ok = sum(v for k, v in c.items() if k.endswith("|confirmed"))
        print(
            f"\n[{kind}] model values (unique per run file): {n}, confirmed by OCR: {n_ok} ({100 * n_ok / max(n, 1):.0f}%)"
        )
        for k in sorted(c):
            print(f"  {k:36} {c[k]}")
    print("\nreference numbers across run files:", dict(ref_total))
    out = Path(__file__).resolve().parents[2] / ".local" / "ocr" / "agree_rows.json"
    out.write_text(json.dumps(rows))
    print(
        "\nunconfirmed model values that are not reference numbers (value page run nearest OCR numbers):"
    )
    for r in rows:
        if r["cat"] == "unjudged" and not r["confirmed"]:
            near = sorted(
                o for o in ocr[r["page"]] if len(o) == len(r["v"]) and edit_distance(o, r["v"]) == 1
            )
            print(" ", r["v"], r["page"], r["run"], r["kind"], near[:4])
    bad = [r for r in rows if r["cat"] == "suspected_misread"]
    print("\nsuspected misreads (value, page, run, OCR-confirmed):")
    for r in bad[:40]:
        print(" ", r["v"], r["page"], r["run"], r["confirmed"], r["kind"])


if __name__ == "__main__":
    main()

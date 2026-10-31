"""Score OCR results against the agent-read spike reference (TASK-030 phase A; offline).

Reads ``.local/ocr/res/<tag>/<dpi>/*.json`` written by ocr_run.py. The reference is the TASK-042
agent-read gold (not human verified) and is not exhaustive, so "extra" numbers are an upper bound
on false tokens, not a measured false-token rate.
"""

from __future__ import annotations

import json
import statistics
import sys
from typing import Any

from ocr_common import (
    ALL_PAGES,
    REFERENCE_PAGES,
    SCRATCH,
    edit_distance,
    num_class,
    numbers_in,
    reference_tokens,
    words_in,
)

Tok = dict[str, Any]


def load(tag: str, dpi: int, pv: str, page: int, angles: list[int]) -> tuple[list[Tok], float]:
    toks: list[Tok] = []
    el = 0.0
    for a in angles:
        f = SCRATCH / "res" / tag / str(dpi) / f"{pv}_p{page:03d}_a{a}.json"
        if not f.exists():
            raise FileNotFoundError(f)
        d = json.loads(f.read_text())
        toks += d["tokens"]
        el += d["elapsed_s"]
    return toks, el


def overlap(a: list[float], b: list[float]) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return inter / small if small > 0 else 0.0


def merge(toks: list[Tok], min_conf: float) -> list[Tok]:
    """Drop low-confidence tokens, then de-duplicate overlapping tokens across passes."""
    kept: list[Tok] = []
    for t in sorted((t for t in toks if t["c"] >= min_conf), key=lambda t: -t["c"]):
        if any(k["a"] != t["a"] and overlap(k["b"], t["b"]) > 0.5 for k in kept):
            continue
        kept.append(t)
    return kept


def score_page(key: str, toks: list[Tok]) -> dict[str, Any]:
    ref = reference_tokens(key)
    ocr_nums: dict[str, Tok] = {}
    for t in toks:
        for n in numbers_in(t["t"]):
            if n not in ocr_nums or t["c"] > ocr_nums[n]["c"]:
                ocr_nums[n] = t
    ocr_words = {w for t in toks for w in words_in(t["t"])}
    blob = " ".join(t["t"].lower() for t in toks)
    by_class: dict[str, list[int]] = {}
    missed: list[str] = []
    near: list[str] = []
    ed_sum = 0
    len_sum = 0
    for n in ref["numbers"]:
        hit = n in ocr_nums
        c = by_class.setdefault(num_class(n), [0, 0])
        c[1] += 1
        c[0] += hit
        if not hit:
            missed.append(n)
            if any(len(o) == len(n) and edit_distance(o, n) == 1 for o in ocr_nums):
                near.append(n)
        best = (
            0
            if hit
            else min(
                (edit_distance(o, n) for o in ocr_nums if abs(len(o) - len(n)) <= 2), default=len(n)
            )
        )
        ed_sum += min(best, len(n))
        len_sum += len(n)
    extra = [n for n in ocr_nums if n not in ref["numbers"]]
    wfound = [w for w in ref["words"] if w in ocr_words or w in blob]
    return {
        "ref_numbers": len(ref["numbers"]),
        "hit_numbers": len(ref["numbers"]) - len(missed),
        "by_class": by_class,
        "missed": missed,
        "near_miss": near,
        "extra_numbers": len(extra),
        "ocr_numbers": len(ocr_nums),
        "ref_words": len(ref["words"]),
        "hit_words": len(wfound),
        "cer_proxy": (ed_sum, len_sum),
        "tokens": len(toks),
    }


def run_config(
    tag: str, dpi: int, angles: list[int], min_conf: float, pages: list[tuple[str, int]]
) -> dict[str, Any]:
    per: dict[str, Any] = {}
    times: list[float] = []
    for pv, page in pages:
        toks, el = load(tag, dpi, pv, page, angles)
        times.append(el)
        key = f"{pv}:{page}"
        per[key] = (
            score_page(key, merge(toks, min_conf))
            if key in {f"{p}:{n}" for p, n in REFERENCE_PAGES}
            else {"tokens": len(merge(toks, min_conf))}
        )
    ref = [v for v in per.values() if "ref_numbers" in v]
    agg: dict[str, Any] = {
        "ref_numbers": sum(v["ref_numbers"] for v in ref),
        "hit_numbers": sum(v["hit_numbers"] for v in ref),
        "near_miss": sum(len(v["near_miss"]) for v in ref),
        "extra_numbers": sum(v["extra_numbers"] for v in ref),
        "ref_words": sum(v["ref_words"] for v in ref),
        "hit_words": sum(v["hit_words"] for v in ref),
        "cer_ed": sum(v["cer_proxy"][0] for v in ref),
        "cer_len": sum(v["cer_proxy"][1] for v in ref),
        "mean_s_per_page": round(statistics.mean(times), 2),
        "control_numbers": sum(v["tokens"] for k, v in per.items() if "ref_numbers" not in v),
    }
    cls: dict[str, list[int]] = {}
    for v in ref:
        for c, (h, n) in v["by_class"].items():
            x = cls.setdefault(c, [0, 0])
            x[0] += h
            x[1] += n
    agg["by_class"] = cls
    return {"agg": agg, "per_page": per}


def main() -> None:
    tags = (
        sys.argv[1].split(",")
        if len(sys.argv) > 1
        else sorted(p.name for p in (SCRATCH / "res").iterdir())
    )
    rows: list[str] = []
    for tag in tags:
        for dp in sorted((SCRATCH / "res" / tag).iterdir()):
            if not dp.is_dir():
                continue
            dpi = int(dp.name)
            for angles in ([0], [0, 270], [0, 90, 270]):
                for mc in (0, 60):
                    try:
                        r = run_config(tag, dpi, angles, mc, ALL_PAGES)
                    except FileNotFoundError:
                        continue
                    a = r["agg"]
                    cl = a["by_class"]
                    cs = " ".join(f"{k}:{v[0]}/{v[1]}" for k, v in sorted(cl.items()))
                    rows.append(
                        f"{tag:16} dpi={dpi:3} ang={'+'.join(map(str, angles)):9} conf>={mc:2} "
                        f"num {a['hit_numbers']}/{a['ref_numbers']} ({100 * a['hit_numbers'] / a['ref_numbers']:.0f}%) "
                        f"words {a['hit_words']}/{a['ref_words']} near {a['near_miss']} extra {a['extra_numbers']} "
                        f"cer {a['cer_ed']}/{a['cer_len']} t/page {a['mean_s_per_page']}s | {cs}"
                    )
                    (SCRATCH / "scores").mkdir(exist_ok=True)
                    (
                        SCRATCH / "scores" / f"{tag}_{dpi}_{'-'.join(map(str, angles))}_{mc}.json"
                    ).write_text(json.dumps(r))
    print("\n".join(rows))


if __name__ == "__main__":
    main()

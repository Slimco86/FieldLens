"""Offline per-setting and composite aggregation (reads saved runs; no network, no spend)."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from spike042_common import SCRATCH
from spike042_gold import GOLD
from spike042_score import score_record


def load(tag: str) -> list[dict[str, Any]]:
    rows = []
    for f in sorted((SCRATCH / "runs" / tag).glob("*.json")):
        rec = json.loads(f.read_text())
        row = score_record(rec)
        row["tag"] = tag
        rows.append(row)
    return rows


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    t: dict[str, Any] = defaultdict(int)
    for r in rows:
        if r.get("gold_sure") is None or r["key"] not in GOLD:
            continue
        t["pages"] += 1
        t["gold"] += r["gold_sure"]
        t["tp"] += r["tp_sure"]
        t["elig"] += r["strict_eligible"]
        t["tp_strict"] += r["tp_strict"]
        t["perf_hit"] += r["perf"][0]
        t["perf_gold"] += r["perf"][1]
    return dict(t)


def main() -> None:
    tags = [p.name for p in sorted((SCRATCH / "runs").iterdir())]
    data = {t: load(t) for t in tags}
    print(
        "PER SETTING (gold pages only; lenient tp/gold, strict tp/eligible, perforations hit/gold)"
    )
    for t in tags:
        r = totals(data[t])
        if r:
            print(
                f"{t:14s} pages={r['pages']:2d} lenient {r['tp']}/{r['gold']} "
                f"strict {r['tp_strict']}/{r['elig']} perf {r['perf_hit']}/{r['perf_gold']}"
            )

    def pick(special: dict[str, str]) -> list[dict[str, Any]]:
        out = [r for r in data["mainlow1600"] if r["key"] not in special]
        for key, tag in special.items():
            out += [r for r in data[tag] if r["key"] == key]
        return out

    tuned = pick({"PV-17:36": "rotmin2400", "PV-21:49": "cal1400"})
    uniform = pick({"PV-17:36": "callow1800", "PV-21:49": "cal1400"})
    for name, rows in (
        ("TUNED composite", tuned),
        ("UNIFORM low (p36 low1800, p49 low1400)", uniform),
    ):
        r = totals(rows)
        print(
            f"{name}: pages={r['pages']} lenient {r['tp']}/{r['gold']} "
            f"strict {r['tp_strict']}/{r['elig']} perf {r['perf_hit']}/{r['perf_gold']}"
        )
    print("CONTROL pages (mainlow1600): candidates / perforations returned")
    for r in data["mainlow1600"]:
        if r.get("control_kind"):
            print(r["key"], r["control_kind"], r["n_cand"], r["control_perfs"])


if __name__ == "__main__":
    main()

"""Offline aggregation of spike runs: spend and tokens per document, headline scores."""

from __future__ import annotations

import json
from collections import defaultdict
from decimal import Decimal

from spike042_common import SCRATCH
from spike042_score import score_record


def main() -> None:
    spend: dict[str, Decimal] = defaultdict(Decimal)
    toks: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    outcomes: dict[str, int] = defaultdict(int)
    calls = 0
    for f in sorted((SCRATCH / "runs").glob("*/*.json")):
        rec = json.loads(f.read_text())
        pv = rec["pv"]
        calls += 1
        outcomes[rec["outcome"]] += 1
        spend[pv] += Decimal(rec.get("committed_usd") or "0")
        for u in rec.get("usage", []):
            uu = u.get("usage") or {}
            toks[pv][0] += uu.get("input_tokens") or 0
            toks[pv][1] += uu.get("output_tokens") or 0
            toks[pv][2] += (uu.get("output_tokens_details") or {}).get("reasoning_tokens") or 0
            toks[pv][3] += 1
    total = sum(spend.values(), Decimal("0"))
    print("calls", calls, dict(outcomes), "spend", total)
    for pv in sorted(spend):
        print(pv, "spend", spend[pv], "in/out/reason/responses", toks[pv])
    print("totals in/out/reason/responses", [sum(t[i] for t in toks.values()) for i in range(4)])
    _ = score_record


if __name__ == "__main__":
    main()

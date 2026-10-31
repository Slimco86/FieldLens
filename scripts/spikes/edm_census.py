"""TASK-044 spike: read-only streaming census and table extractor for the Volve EDM XML export.

Uses the hardened expat set-up from ``fieldlens.profiles.safexml`` (no DTD/entities/network). The
file is streamed in 1 MiB chunks; only counters and (for ``dump``) selected rows are kept.

    python scripts/spikes/edm_census.py census SRC OUT.json
    python scripts/spikes/edm_census.py dump SRC OUT.jsonl TABLE [TABLE ...]

Every row records its 1-based line number (``_line``), the element's byte offset is not kept by
expat for rows, the line is the locator. Nothing here is a production profile."""

from __future__ import annotations

import json
import resource
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from fieldlens.profiles.safexml import _new_parser

CHUNK = 1024 * 1024
MAX_DEPTH = 16


def _drive(src: Path, start: Any, end: Any) -> None:
    parser = _new_parser()
    depth = 0

    def s(name: str, attrs: dict[str, str]) -> None:
        nonlocal depth
        depth += 1
        if depth > MAX_DEPTH:
            raise ValueError("depth limit")
        start(name, attrs, depth, parser.CurrentLineNumber)

    def e(name: str) -> None:
        nonlocal depth
        end(name, depth)
        depth -= 1

    parser.StartElementHandler = s
    parser.EndElementHandler = e
    with src.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            parser.Parse(chunk, False)
    parser.Parse(b"", True)


def census(src: Path, out: Path) -> None:
    counts: Counter[str] = Counter()
    attrs: dict[str, Counter[str]] = defaultdict(Counter)
    parents: dict[str, Counter[str]] = defaultdict(Counter)
    first_line: dict[str, int] = {}
    stack: list[str] = []
    max_depth = 0

    def start(name: str, a: dict[str, str], depth: int, line: int) -> None:
        nonlocal max_depth
        max_depth = max(max_depth, depth)
        counts[name] += 1
        first_line.setdefault(name, line)
        parents[name][stack[-1] if stack else ""] += 1
        for k in a:
            attrs[name][k] += 1
        stack.append(name)

    def end(_n: str, _d: int) -> None:
        stack.pop()

    t0 = time.time()
    _drive(src, start, end)
    out.write_text(
        json.dumps(
            {
                "seconds": round(time.time() - t0, 1),
                "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
                "max_depth": max_depth,
                "tables": {
                    t: {
                        "rows": counts[t],
                        "first_line": first_line[t],
                        "parents": dict(parents[t]),
                        "attrs": dict(attrs[t]),
                    }
                    for t in counts
                },
            },
            indent=1,
        )
    )


def dump(src: Path, out: Path, tables: set[str]) -> None:
    n = 0
    t0 = time.time()
    with out.open("w") as fh:

        def start(name: str, a: dict[str, str], _d: int, line: int) -> None:
            nonlocal n
            if name in tables:
                fh.write(json.dumps({"_t": name, "_line": line, **a}) + "\n")
                n += 1

        _drive(src, start, lambda _n, _d: None)
    print(
        json.dumps(
            {
                "rows": n,
                "seconds": round(time.time() - t0, 1),
                "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
            }
        )
    )


def main(argv: list[str]) -> int:
    if len(argv) >= 4 and argv[1] == "census":
        census(Path(argv[2]), Path(argv[3]))
    elif len(argv) >= 5 and argv[1] == "dump":
        dump(Path(argv[2]), Path(argv[3]), set(argv[4:]))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""Check, list and plan the ``docs/BACKLOG.md`` ledger (spec TRACKING.md, slice B).

    uv run python scripts/track.py check
    uv run python scripts/track.py list --status in_progress --tag backend
    uv run python scripts/track.py plan

Stdlib only; no network code in this slice (Taiga sync lands in slice C).
Exit codes: 0 ok, 1 ledger violations, 2 usage/IO error.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "docs" / "BACKLOG.md"


def _load(path: Path) -> ledger.Ledger | None:
    try:
        return ledger.load_ledger(path)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"track: cannot read {path}: {exc}", file=sys.stderr)
        return None


def _report(led: ledger.Ledger, path: Path) -> int:
    for v in led.violations:
        who = f"{v.item_id}: " if v.item_id else ""
        print(f"{path}:{v.line}: {who}{v.message}")
    if led.violations:
        print(f"track: {len(led.violations)} violation(s) in {path}", file=sys.stderr)
        return 1
    return 0


def cmd_check(path: Path) -> int:
    led = _load(path)
    if led is None:
        return 2
    code = _report(led, path)
    if code == 0:
        features = sum(1 for i in led.items if i.is_feature)
        print(f"ok: {features} features, {len(led.items) - features} tasks")
    return code


def cmd_list(path: Path, status: str | None, tag: str | None) -> int:
    led = _load(path)
    if led is None:
        return 2
    if _report(led, path):
        return 1
    rows = [
        i
        for i in led.items
        if (status is None or i.status == status) and (tag is None or tag in i.tags)
    ]
    header = ("ID", "Status", "Pri", "Due", "Assignee", "Depends on", "Title")
    table = [header] + [
        (
            i.id,
            i.status,
            i.priority,
            i.due.isoformat(),
            i.assignee,
            ", ".join(i.depends_on) or "none",
            i.title,
        )
        for i in rows
    ]
    widths = [max(len(r[c]) for r in table) for c in range(len(header) - 1)]
    for r in table:
        cells = [r[c].ljust(widths[c]) for c in range(len(header) - 1)] + [r[-1]]
        print("  ".join(cells))
    print(f"{len(rows)} item(s)")
    return 0


def cmd_plan(path: Path) -> int:
    led = _load(path)
    if led is None:
        return 2
    if _report(led, path):
        return 1
    counts: Counter[tuple[str, str]] = Counter((i.type, i.status) for i in led.items)
    for item_type in ledger.TYPES:
        parts = [f"{s}={counts[(item_type, s)]}" for s in ledger.STATUSES if counts[(item_type, s)]]
        total = sum(1 for i in led.items if i.type == item_type)
        print(f"{item_type}: {total} ({', '.join(parts) or 'none'})")
    print("sync not available in this slice")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="track.py", description="Backlog ledger tool.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="ledger file")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate the ledger")
    p_list = sub.add_parser("list", help="list items")
    p_list.add_argument("--status", choices=ledger.STATUSES)
    p_list.add_argument("--tag")
    sub.add_parser("plan", help="check, then summarize (Taiga plan arrives in slice C)")
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "check":
        return cmd_check(args.file)
    if args.command == "list":
        return cmd_list(args.file, args.status, args.tag)
    return cmd_plan(args.file)


if __name__ == "__main__":
    raise SystemExit(main())

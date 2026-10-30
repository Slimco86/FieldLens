"""Check, list and plan the ``docs/BACKLOG.md`` ledger (spec TRACKING.md, slice B).

    uv run python scripts/track.py check
    uv run python scripts/track.py list --status in_progress --tag backend
    uv run python scripts/track.py plan

    uv run python scripts/track.py sync [--apply] [--keep-drift] [--notify] [--only FL-001,TASK-002]

``plan`` and ``sync`` without ``--apply`` read Taiga (GET only) and print create/update/no-op per
item; ``sync --apply`` writes. ``plan --offline`` only summarizes the ledger. Stdlib only.
Exit codes: 0 ok, 1 ledger violations, 2 usage/IO/tracker/config/network error, 3 refused by a
privacy guard (non-private project, secret-like text).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
import notify as notify_mod  # noqa: E402
import taiga_client  # noqa: E402
import toolenv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FILE = ROOT / "docs" / "BACKLOG.md"
DEFAULT_SLUG = "slimco86-test"
STATE_NAME = Path(".local") / "run" / "taiga-state.json"
SUBJECT_RE = re.compile(r"^\[((?:FL|TASK)-\d{3})\] ")
MIN_REFUSE_LEN = 6
EXIT_OK, EXIT_LEDGER, EXIT_ERROR, EXIT_REFUSED = 0, 1, 2, 3


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


def cmd_plan_offline(path: Path) -> int:
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
    return 0


# ------------------------------------------------------------------------- Taiga sync


class SyncError(Exception):
    """Configuration/tracker problem (exit 2). Message is already redacted."""


class Refused(Exception):
    """A privacy guard refused the run (exit 3)."""


STORY_FIELDS = (
    "subject",
    "description",
    "status",
    "tags",
    "assigned_to",
    "due_date",
    "is_blocked",
    "blocked_note",
    "milestone",
)
TASK_FIELDS = (*STORY_FIELDS, "user_story")
KINDS = {True: "userstories", False: "tasks"}


def _norm(name: str, value: Any) -> Any:
    if name in ("description", "blocked_note", "subject"):
        return str(value or "").replace("\r\n", "\n").rstrip()
    if name == "tags":
        names = {t[0] if isinstance(t, (list, tuple)) and t else t for t in (value or [])}
        return sorted(str(n) for n in names if n)
    if name == "is_blocked":
        return bool(value)
    return value


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]


def _fields(item: ledger.Item) -> tuple[str, ...]:
    return STORY_FIELDS if item.is_feature else TASK_FIELDS


@dataclass
class Ctx:
    by_id: Mapping[str, ledger.Item]
    story_status: Mapping[str, int]
    task_status: Mapping[str, int]
    milestones: Mapping[str, int]
    owner_id: int | None
    tag_pairs: bool = False


def _tags(item: ledger.Item) -> list[str]:
    tags = set(item.tags)
    if item.priority:
        tags.add(item.priority.lower())
    if item.assignee.startswith("agent:"):
        tags.add("agent-" + item.assignee.split(":", 1)[1])
    task_tag = ledger.TAIGA_STATUS_MAP[item.status].task_tag
    if task_tag and not item.is_feature:
        tags.add(task_tag)
    return sorted(tags)


def _description(
    item: ledger.Item, by_id: Mapping[str, ledger.Item], refs: Mapping[str, int]
) -> str:
    lines = ledger.render_description(item, by_id).split("\n")
    for dep in item.depends_on:
        if dep in refs:
            prefix = f"- {dep} ("
            lines = [f"{ln} #{refs[dep]}" if ln.startswith(prefix) else ln for ln in lines]
    return "\n".join(lines)


def desired_fields(
    item: ledger.Item,
    ctx: Ctx,
    refs: Mapping[str, int],
    story_ids: Mapping[str, int],
) -> dict[str, Any]:
    mapping = ledger.TAIGA_STATUS_MAP[item.status]
    status_name = mapping.story if item.is_feature else mapping.task
    table = ctx.story_status if item.is_feature else ctx.task_status
    if status_name not in table:
        raise SyncError(f"Taiga status {status_name!r} not found in the project")
    sprint_item = item if item.is_feature else ctx.by_id.get(item.parent or "", item)
    if sprint_item.sprint not in ctx.milestones:
        raise SyncError(f"Taiga sprint {sprint_item.sprint!r} not found in the project")
    note = ledger.blocked_note(item, ctx.by_id)
    want: dict[str, Any] = {
        "subject": ledger.render_subject(item),
        "description": _description(item, ctx.by_id, refs),
        "status": table[status_name],
        "tags": _tags(item),
        "assigned_to": ctx.owner_id if item.assignee == "owner" else None,
        "due_date": item.due.isoformat(),
        "is_blocked": note is not None,
        "blocked_note": note or "",
        "milestone": ctx.milestones[sprint_item.sprint],
    }
    if not item.is_feature:
        want["user_story"] = story_ids.get(item.parent or "")
    return want


def _preflight(
    items: Sequence[ledger.Item], by_id: Mapping[str, ledger.Item], secrets: Sequence[str]
) -> None:
    """Secret guard over every outgoing text, before any network call."""
    long_secrets = [s for s in secrets if len(s) >= MIN_REFUSE_LEN]
    for item in items:
        try:
            texts = [ledger.render_subject(item), ledger.render_description(item, by_id)]
        except ledger.SecretInDescription as exc:
            raise Refused(str(exc)) from None
        texts += [ledger.blocked_note(item, by_id) or "", ",".join(_tags(item))]
        joined = "\n".join(texts)
        if ledger.find_secret(joined):
            raise Refused(f"{item.id}: secret-like text; refusing to send")
        if any(s in joined for s in long_secrets):
            raise Refused(f"{item.id}: text contains a configured credential value; refusing")


def _load_state(root: Path, project_id: int) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads((root / STATE_NAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict) or data.get("project") != project_id:
        return {}
    items = data.get("items")
    return (
        {k: v for k, v in items.items() if isinstance(v, dict)} if isinstance(items, dict) else {}
    )


def _save_state(root: Path, project_id: int, items: Mapping[str, Any]) -> None:
    path = root / STATE_NAME
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps({"project": project_id, "items": items}, sort_keys=True))
    path.chmod(0o600)


def _wire(fields: Mapping[str, Any], tag_pairs: bool) -> dict[str, Any]:
    out = dict(fields)
    if "tags" in out and tag_pairs:
        out["tags"] = [[t, None] for t in out["tags"]]
    return out


def _write(
    client: taiga_client.TaigaClient,
    ctx: Ctx,
    kind: str,
    fields: Mapping[str, Any],
    object_id: int | None = None,
    version: int = 0,
) -> dict[str, Any]:
    for attempt in range(3):
        wire = _wire(fields, ctx.tag_pairs)
        try:
            if object_id is None:
                return client.create(kind, wire)
            return client.patch(kind, object_id, version, wire)
        except taiga_client.TaigaError as exc:
            text = str(exc)
            if exc.status == 400 and "tags" in fields and "tags" in text and not ctx.tag_pairs:
                ctx.tag_pairs = True
                continue
            if (
                object_id is not None
                and exc.status in (400, 409)
                and "version" in text
                and attempt < 2
            ):
                version = int(client.get_object(kind, object_id)["version"])
                continue
            raise
    raise SyncError("write retries exhausted")


@dataclass
class SyncResult:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    writes: int = 0


def _index(
    objs: Sequence[Mapping[str, Any]], allowed: Callable[[str], bool], label: str
) -> tuple[dict[str, dict[str, Any]], list[str], int]:
    found: dict[str, dict[str, Any]] = {}
    foreign: list[str] = []
    unprefixed = 0
    for obj in objs:
        match = SUBJECT_RE.match(str(obj.get("subject", "")))
        if not match:
            unprefixed += 1
            continue
        ident = match.group(1)
        if not allowed(ident):
            foreign.append(ident)
            continue
        if ident in found:
            raise SyncError(f"duplicate {label} for {ident} in Taiga; resolve it manually")
        found[ident] = dict(obj)
    return found, foreign, unprefixed


def _sync_body(
    client: taiga_client.TaigaClient,
    led: ledger.Ledger,
    scope: Sequence[ledger.Item],
    values: Mapping[str, str],
    root: Path,
    *,
    apply: bool,
    keep_drift: bool,
    result: SyncResult,
) -> None:
    by_id = led.by_id()
    slug = values.get("TAIGA_PROJECT_SLUG") or DEFAULT_SLUG
    me = client.me()
    project = client.project_by_slug(slug)
    if not project.get("is_private") and values.get("TAIGA_ALLOW_PUBLIC") != "1":
        raise Refused("project is not private; set TAIGA_ALLOW_PUBLIC=1 to sync backlog text to it")
    pid = int(project["id"])
    story_status = {str(s["name"]): int(s["id"]) for s in client.story_statuses(pid)}
    task_status = {str(s["name"]): int(s["id"]) for s in client.task_statuses(pid)}
    milestones = {str(m["name"]): int(m["id"]) for m in client.milestones(pid)}
    members = {m.get("user") for m in client.memberships(pid)}
    owner_id = me.get("id") if me.get("id") in members else None
    if owner_id is None and any(i.assignee == "owner" for i in scope):
        raise SyncError("TAIGA_USERNAME is not a member of the project; cannot map assignee owner")
    ctx = Ctx(by_id, story_status, task_status, milestones, owner_id)

    stories, foreign_s, unpref_s = _index(
        client.userstories(pid), lambda i: i.startswith("FL-") and i in by_id, "user story"
    )
    tasks, foreign_t, unpref_t = _index(
        client.tasks(pid), lambda i: i.startswith("TASK-") and i in by_id, "task"
    )
    foreign = sorted({*foreign_s, *foreign_t})
    print(
        f"tracker: untouched {unpref_s} unprefixed user stor{'y' if unpref_s == 1 else 'ies'}, "
        f"{unpref_t} unprefixed task(s)"
        + (f"; prefixed but not managed here: {', '.join(foreign)}" if foreign else "")
    )
    live: dict[str, dict[str, Any]] = {**stories, **tasks}
    state = _load_state(root, pid)
    refs: dict[str, int] = {i: int(o["ref"]) for i, o in live.items() if o.get("ref") is not None}
    story_ids: dict[str, int] = {i: int(o["id"]) for i, o in stories.items()}
    ordered = [i for i in scope if i.is_feature] + [i for i in scope if not i.is_feature]
    created: set[str] = set()

    def label(item: ledger.Item) -> str:
        return f"{item.id:<9} {'story' if item.is_feature else 'task '}"

    for item in ordered:
        if (
            not item.is_feature
            and item.parent not in story_ids
            and not any(s.id == item.parent for s in scope)
        ):
            raise SyncError(
                f"{item.id}: parent {item.parent} is not in Taiga; include it in --only"
            )

    # Phase 1: create missing objects (stories first, then tasks).
    for item in ordered:
        if item.id in live:
            continue
        if not apply:
            print(f"create  {label(item)} {item.title[:60]}")
            result.created.append(item.id)
            continue
        want = desired_fields(item, ctx, refs, story_ids)
        want["project"] = pid
        if not item.is_feature and want.get("user_story") is None:
            raise SyncError(f"{item.id}: parent story id unknown")
        obj = _write(client, ctx, KINDS[item.is_feature], want)
        live[item.id] = obj
        created.add(item.id)
        if obj.get("ref") is not None:
            refs[item.id] = int(obj["ref"])
        if item.is_feature:
            story_ids[item.id] = int(obj["id"])
        print(f"create  {label(item)} {item.title[:60]}")
        result.created.append(item.id)

    # Phase 2: reconcile existing objects (incl. the description/link pass for new ones).
    new_state: dict[str, Any] = {k: v for k, v in state.items() if k in by_id}
    try:
        for item in ordered:
            cur = live.get(item.id)
            if cur is None:
                continue
            want = desired_fields(item, ctx, refs, story_ids)
            names = _fields(item)
            diff = [
                n
                for n in names
                if not (n == "user_story" and want[n] is None)
                and _norm(n, want[n]) != _norm(n, cur.get(n))
            ]
            stored = state.get(item.id, {}).get("hashes", {}) if item.id not in created else {}
            drifted = [n for n in diff if n in stored and _hash(_norm(n, cur.get(n))) != stored[n]]
            skip = set(drifted) if keep_drift else set()
            patch = {n: want[n] for n in diff if n not in skip}
            for n in drifted:
                result.drift.append(f"{item.id}:{n}")
                print(
                    f"drift   {label(item)} {n} (tracker edited since last push; "
                    f"{'kept' if keep_drift else 'will be overwritten'})"
                )
            written = False
            if patch and apply:
                cur = _write(
                    client, ctx, KINDS[item.is_feature], patch, int(cur["id"]), int(cur["version"])
                )
                live[item.id] = cur
                written = True
            if item.id in created:
                pass
            elif patch:
                print(f"update  {label(item)} changed: {', '.join(patch)}")
                result.updated.append(item.id)
            elif not drifted:
                print(f"no-op   {label(item)}")
                result.unchanged.append(item.id)
            elif keep_drift:
                result.unchanged.append(item.id)
            if item.id in created and written:
                print(f"link    {label(item)} changed: {', '.join(patch)}")
            if apply:
                hashes = dict(stored)
                for n in names:
                    if n in skip or (n == "user_story" and want[n] is None):
                        continue
                    hashes[n] = _hash(_norm(n, want[n]))
                new_state[item.id] = {
                    "id": int(live[item.id]["id"]),
                    "version": int(live[item.id]["version"]),
                    "hashes": hashes,
                }
    finally:
        if apply:
            _save_state(root, pid, new_state)
    result.writes = client.write_calls


def _summary_text(result: SyncResult, failed: bool) -> str:
    changed = [*result.created, *result.updated]
    shown = ", ".join(changed[:25]) + (f" (+{len(changed) - 25} more)" if len(changed) > 25 else "")
    head = "Taiga sync FAILED partway" if failed else "Taiga sync applied"
    text = (
        f"{head}: created {len(result.created)}, updated {len(result.updated)}, "
        f"unchanged {len(result.unchanged)}, drift fields {len(result.drift)}."
    )
    return text + (f" Changed: {shown}" if changed else "")


def cmd_sync(
    path: Path,
    *,
    apply: bool = False,
    keep_drift: bool = False,
    notify: bool = False,
    only: str | None = None,
    timeout: float = taiga_client.TIMEOUT,
    root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
    transport: taiga_client.Transport = taiga_client.urllib_transport,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    led = _load(path)
    if led is None:
        return EXIT_ERROR
    if _report(led, path):
        return EXIT_LEDGER
    by_id = led.by_id()
    scope: list[ledger.Item] = list(led.items)
    if only:
        wanted = [x.strip() for x in only.split(",") if x.strip()]
        unknown = [x for x in wanted if x not in by_id]
        if unknown:
            print(f"track: unknown ID(s) in --only: {', '.join(unknown)}", file=sys.stderr)
            return EXIT_ERROR
        scope = [i for i in led.items if i.id in wanted]
    values = toolenv.load(root, os.environ if environ is None else environ)
    secrets = toolenv.secret_values(values)
    try:
        _preflight(scope, by_id, secrets)
    except Refused as exc:
        print(f"track: refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    missing = [k for k in ("TAIGA_USERNAME", "TAIGA_PASSWORD") if not values.get(k)]
    if missing:
        print(f"track: missing configuration keys: {', '.join(missing)}", file=sys.stderr)
        return EXIT_ERROR
    result = SyncResult()
    code = EXIT_OK
    client: taiga_client.TaigaClient | None = None
    try:
        client = taiga_client.TaigaClient(
            values.get("TAIGA_URL") or taiga_client.DEFAULT_URL,
            values["TAIGA_USERNAME"],
            values["TAIGA_PASSWORD"],
            transport=transport,
            sleep=sleep,
            timeout=timeout,
            secrets=secrets,
        )
        _sync_body(
            client, led, scope, values, root, apply=apply, keep_drift=keep_drift, result=result
        )
    except Refused as exc:
        print(f"track: refused: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    except (SyncError, taiga_client.TaigaError, OSError, KeyError, ValueError, TypeError) as exc:
        text = (
            f"{type(exc).__name__}"
            if not isinstance(exc, SyncError | taiga_client.TaigaError)
            else str(exc)
        )
        print(f"track: error: {client.redact(text) if client else text}", file=sys.stderr)
        code = EXIT_ERROR
    if client is not None:
        result.writes = client.write_calls
    print(
        f"{'applied' if apply else 'dry-run'}: created={len(result.created)} "
        f"updated={len(result.updated)} unchanged={len(result.unchanged)} "
        f"drift={len(result.drift)} writes={result.writes}"
    )
    if notify and apply:
        notify_mod.notify(
            "info",
            _summary_text(result, code != EXIT_OK),
            best_effort=True,
            root=root,
            environ=environ,
        )
    return code


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="track.py", description="Backlog ledger tool.")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE, help="ledger file")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate the ledger")
    p_list = sub.add_parser("list", help="list items")
    p_list.add_argument("--status", choices=ledger.STATUSES)
    p_list.add_argument("--tag")
    p_plan = sub.add_parser("plan", help="read-only diff against Taiga (see sync)")
    p_plan.add_argument("--offline", action="store_true", help="only summarize the ledger")
    p_plan.add_argument("--only", help="comma-separated item IDs")
    p_plan.add_argument("--timeout", type=float, default=taiga_client.TIMEOUT)
    p_sync = sub.add_parser("sync", help="mirror the ledger into Taiga (dry-run unless --apply)")
    p_sync.add_argument("--apply", action="store_true", help="write to Taiga")
    p_sync.add_argument("--keep-drift", action="store_true", help="do not overwrite tracker edits")
    p_sync.add_argument("--notify", action="store_true", help="Telegram summary after --apply")
    p_sync.add_argument("--only", help="comma-separated item IDs")
    p_sync.add_argument("--timeout", type=float, default=taiga_client.TIMEOUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    if args.command == "check":
        return cmd_check(args.file)
    if args.command == "list":
        return cmd_list(args.file, args.status, args.tag)
    if args.command == "plan":
        if args.offline:
            return cmd_plan_offline(args.file)
        return cmd_sync(args.file, only=args.only, timeout=args.timeout)
    return cmd_sync(
        args.file,
        apply=args.apply,
        keep_drift=args.keep_drift,
        notify=args.notify,
        only=args.only,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    raise SystemExit(main())

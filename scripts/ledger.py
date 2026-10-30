"""Strict parser and validator for the ``docs/BACKLOG.md`` ledger (spec TRACKING.md 4.1).

Stdlib only and free of network code. ``track.py`` uses it for ``check|list|plan`` and the
later Taiga sync reuses the item model, dependency helpers, the status mapping table and the
deterministic description renderer.

Format: ``## Features`` and ``## Tasks`` sections hold one block per item::

    ### FL-005 · Title
    | Field | Value |
    |---|---|
    | Type | feature |
    ...
    **Outcome.** text
    **Next action.** text
    **Evidence.** text

Everything from ``## Journal`` to the end of the file is history and is not parsed.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import NamedTuple

HEADING_RE = re.compile(r"^### ((?:FL|TASK)-\d{3}) · (.+)$")
ITEM_ID_RE = re.compile(r"^(?:FL|TASK)-\d{3}$")
LABEL_RE = re.compile(r"^\*\*(Outcome|Next action|Evidence)\.\*\*(?: (.*))?$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
ASSIGNEE_RE = re.compile(r"^(?:owner|unassigned|agent:[a-z0-9]+(?:-[a-z0-9]+)*)$")
TAG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SLICE_RE = re.compile(r"^(?:FL|TASK)-\d{3}(?:-[A-Z])?$")

STATUSES = (
    "proposed",
    "specifying",
    "ready",
    "in_progress",
    "testing",
    "integration_pending",
    "done",
    "blocked",
    "cancelled",
)
PRIORITIES = ("P0", "P1", "P2")
TYPES = ("feature", "task")
# Fixed tag vocabulary (documented in the BACKLOG preamble).
TAGS = (
    "foundation",
    "ingestion",
    "backend",
    "frontend",
    "3d",
    "charts",
    "rag",
    "geospatial",
    "qa",
    "infra",
    "data",
    "docs",
    "agent",
    "release",
)
SPRINT = "Hackathon"
WINDOW_START = date(2026, 10, 29)
WINDOW_END = date(2026, 11, 4)

COMMON_FIELDS = (
    "Type",
    "Status",
    "Priority",
    "Tags",
    "Depends on",
    "Assignee",
    "Due",
    "Sprint",
    "Spec",
    "Version",
)
TASK_ONLY_FIELDS = ("Parent", "Slice")
ALL_FIELDS = COMMON_FIELDS + TASK_ONLY_FIELDS
LABELS = ("Outcome", "Next action", "Evidence")

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("telegram-bot-token", re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}")),
    ("api-key", re.compile(r"\b(?:sk|pk|ghp|gho|ghs|xox[bp])[-_][A-Za-z0-9_-]{16,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "credential-assignment",
        re.compile(
            r"(?i)\b(?:password|passwd|secret|token|api[_-]?key|auth[_-]?token)\s*[=:]\s*"
            r"[^\s`'\"]{6,}"
        ),
    ),
    ("url-credentials", re.compile(r"://[^/\s:@]+:[^/\s@]+@")),
)


class TaigaStatus(NamedTuple):
    """Spec 4.2 row: Taiga status for a story (feature) and a task, plus flags."""

    story: str
    task: str
    is_blocked: bool = False
    task_tag: str | None = None


# Data only; the Taiga sync (slice C) consumes it. Keys are ledger statuses.
TAIGA_STATUS_MAP: Mapping[str, TaigaStatus] = {
    "proposed": TaigaStatus("New", "New"),
    "specifying": TaigaStatus("New", "New"),
    "ready": TaigaStatus("Ready", "New"),
    "in_progress": TaigaStatus("In progress", "In progress"),
    "testing": TaigaStatus("Ready for test", "Ready for test"),
    "integration_pending": TaigaStatus("Ready for test", "Ready for test"),
    "done": TaigaStatus("Done", "Closed"),
    "blocked": TaigaStatus("New", "New", is_blocked=True),
    "cancelled": TaigaStatus("Archived", "Closed", task_tag="cancelled"),
}


@dataclass(frozen=True)
class Violation:
    line: int
    message: str
    item_id: str | None = None

    def __str__(self) -> str:
        where = f"{self.item_id}: " if self.item_id else ""
        return f"line {self.line}: {where}{self.message}"


@dataclass(frozen=True)
class Item:
    id: str
    title: str
    line: int
    type: str
    status: str
    priority: str
    tags: tuple[str, ...]
    depends_on: tuple[str, ...]
    assignee: str
    due: date
    sprint: str
    spec: str
    version: str
    outcome: str
    next_action: str
    evidence: str
    parent: str | None = None
    slice: str | None = None
    field_lines: Mapping[str, int] = field(default_factory=dict, compare=False)

    @property
    def is_feature(self) -> bool:
        return self.type == "feature"

    @property
    def is_done(self) -> bool:
        return self.status == "done"


@dataclass(frozen=True)
class ParseResult:
    items: tuple[Item, ...]
    violations: tuple[Violation, ...]
    has_journal: bool


# --------------------------------------------------------------------------- parsing


@dataclass
class _Block:
    id: str
    title: str
    line: int
    section: str
    rows: list[tuple[int, str, str]] = field(default_factory=list)
    labels: dict[str, tuple[int, str]] = field(default_factory=dict)
    saw_table: bool = False


def _split_row(line: str) -> list[str] | None:
    stripped = line.strip()
    if not (stripped.startswith("|") and stripped.endswith("|") and len(stripped) > 1):
        return None
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _is_separator(cells: Sequence[str]) -> bool:
    return len(cells) == 2 and all(re.fullmatch(r":?-{3,}:?", c) for c in cells)


def parse_text(text: str) -> ParseResult:
    """Parse ledger text. Returns items plus every structural violation (never raises)."""
    violations: list[Violation] = []
    blocks: list[_Block] = []
    section = "preamble"
    has_journal = False
    current: _Block | None = None
    table_state = "none"  # none | header | rows | done
    label_open: str | None = None
    lines = text.splitlines()

    def bad(n: int, msg: str, item: str | None = None) -> None:
        violations.append(Violation(n, msg, item))

    for n, raw in enumerate(lines, start=1):
        if raw.startswith("## "):
            name = raw[3:].strip()
            current, table_state, label_open = None, "none", None
            if name == "Journal":
                if has_journal:
                    bad(n, "duplicate '## Journal' heading")
                has_journal = True
                section = "journal"
                # The journal is history: nothing after this heading is parsed.
                break
            section = {"Features": "features", "Tasks": "tasks"}.get(name, "other")
            continue
        if raw.startswith("### "):
            current, table_state, label_open = None, "none", None
            m = HEADING_RE.match(raw)
            if m is None:
                if section in ("features", "tasks"):
                    bad(n, "heading does not match '### <FL|TASK>-NNN · title'")
                elif ITEM_ID_RE.match(raw[4:].split(" ")[0]):
                    bad(n, "item heading outside '## Features'/'## Tasks' or malformed")
                continue
            item_id, title = m.group(1), m.group(2).strip()
            expected = {"features": "FL", "tasks": "TASK"}.get(section)
            if expected is None:
                bad(n, "item heading outside '## Features'/'## Tasks'", item_id)
                continue
            if not item_id.startswith(expected):
                bad(n, f"{item_id} is in the wrong section (expected {expected}-NNN)", item_id)
            current = _Block(item_id, title, n, section)
            blocks.append(current)
            continue
        if current is None:
            continue
        stripped = raw.strip()
        if not stripped:
            label_open = None
            if table_state in ("header", "rows"):
                table_state = "done"
            continue
        cells = _split_row(raw)
        if cells is not None and label_open is None:
            if table_state == "done":
                bad(n, "second table in item block", current.id)
                continue
            if table_state == "none":
                if cells != ["Field", "Value"]:
                    bad(n, "table header must be exactly '| Field | Value |'", current.id)
                table_state = "header"
                current.saw_table = True
                continue
            if table_state == "header":
                if not _is_separator(cells):
                    bad(n, "table separator row missing or malformed", current.id)
                table_state = "rows"
                continue
            if len(cells) != 2:
                bad(n, f"table row must have exactly 2 columns, found {len(cells)}", current.id)
                continue
            current.rows.append((n, cells[0], cells[1]))
            continue
        lm = LABEL_RE.match(stripped)
        if lm is not None:
            label = lm.group(1)
            if label in current.labels:
                bad(n, f"duplicate label **{label}.**", current.id)
            current.labels[label] = (n, (lm.group(2) or "").strip())
            label_open = label
            table_state = "done" if table_state in ("header", "rows") else table_state
            continue
        if label_open is not None:
            ln, prev = current.labels[label_open]
            current.labels[label_open] = (ln, f"{prev} {stripped}".strip())
            continue
        bad(
            n,
            "unexpected text; item blocks allow only the table and the three bold labels",
            current.id,
        )

    if not has_journal:
        bad(max(len(lines), 1), "missing '## Journal' section")

    items: list[Item] = []
    seen: dict[str, int] = {}
    for blk in blocks:
        if blk.id in seen:
            bad(blk.line, f"duplicate ID (first defined at line {seen[blk.id]})", blk.id)
            continue
        seen[blk.id] = blk.line
        item = _build_item(blk, violations)
        if item is not None:
            items.append(item)
    violations.sort(key=lambda v: v.line)
    return ParseResult(tuple(items), tuple(violations), has_journal)


def _parse_ids(value: str) -> list[str]:
    if value.strip().lower() == "none":
        return []
    return [p.strip() for p in value.split(",")]


def _build_item(blk: _Block, out: list[Violation]) -> Item | None:
    start = len(out)

    def bad(n: int, msg: str) -> None:
        out.append(Violation(n, msg, blk.id))

    if not blk.saw_table:
        bad(blk.line, "missing '| Field | Value |' table")
    fields: dict[str, str] = {}
    flines: dict[str, int] = {}
    for n, name, value in blk.rows:
        if name not in ALL_FIELDS:
            bad(n, f"unknown field '{name}'")
            continue
        if name in fields:
            bad(n, f"duplicate field '{name}'")
            continue
        fields[name] = value
        flines[name] = n
    is_task = blk.id.startswith("TASK")
    required = COMMON_FIELDS + (TASK_ONLY_FIELDS if is_task else ())
    for name in required:
        if name not in fields:
            bad(blk.line, f"missing required field '{name}'")
        elif not fields[name]:
            bad(flines[name], f"field '{name}' is empty")
    if not is_task:
        for name in TASK_ONLY_FIELDS:
            if name in fields:
                bad(flines[name], f"field '{name}' is for tasks only")
    for label in LABELS:
        if label not in blk.labels:
            bad(blk.line, f"missing label **{label}.**")
        elif not blk.labels[label][1]:
            bad(blk.labels[label][0], f"label **{label}.** has no text")

    def get(name: str) -> str:
        return fields.get(name, "")

    def line(name: str) -> int:
        return flines.get(name, blk.line)

    item_type = get("Type")
    if item_type and item_type not in TYPES:
        bad(line("Type"), f"Type '{item_type}' not in {'|'.join(TYPES)}")
    elif item_type and item_type != ("task" if is_task else "feature"):
        bad(line("Type"), f"Type '{item_type}' contradicts the {blk.id} heading")
    status = get("Status")
    if status and status not in STATUSES:
        bad(line("Status"), f"Status '{status}' not in {'|'.join(STATUSES)}")
    priority = get("Priority")
    if priority and priority not in PRIORITIES:
        bad(line("Priority"), f"Priority '{priority}' not in {'|'.join(PRIORITIES)}")
    tags: list[str] = []
    if get("Tags"):
        tags = [t.strip() for t in get("Tags").split(",")]
        for tag in tags:
            if not TAG_RE.match(tag):
                bad(line("Tags"), f"tag '{tag}' is not lowercase kebab-case")
            elif tag not in TAGS:
                bad(line("Tags"), f"tag '{tag}' is not in the vocabulary ({', '.join(TAGS)})")
        if len(set(tags)) != len(tags):
            bad(line("Tags"), "duplicate tags")
    deps: list[str] = []
    if get("Depends on"):
        deps = _parse_ids(get("Depends on"))
        for dep in deps:
            if not ITEM_ID_RE.match(dep):
                bad(line("Depends on"), f"'{dep}' is not an item ID (or 'none')")
        if len(set(deps)) != len(deps):
            bad(line("Depends on"), "duplicate dependency")
    if get("Assignee") and not ASSIGNEE_RE.match(get("Assignee")):
        bad(line("Assignee"), "Assignee must be owner | unassigned | agent:<profile>")
    due: date | None = None
    if get("Due"):
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", get("Due")):
                raise ValueError
            due = date.fromisoformat(get("Due"))
        except ValueError:
            bad(line("Due"), f"Due '{get('Due')}' is not a valid YYYY-MM-DD date")
    if get("Sprint") and get("Sprint") != SPRINT:
        bad(line("Sprint"), f"Sprint must be '{SPRINT}'")
    version = get("Version")
    if version and version.lower() != "none" and not VERSION_RE.match(version):
        bad(line("Version"), f"Version '{version}' is not MAJOR.MINOR.PATCH or 'none'")
    if is_task:
        if get("Parent") and not ITEM_ID_RE.match(get("Parent")):
            bad(line("Parent"), f"Parent '{get('Parent')}' is not an item ID")
        if get("Slice") and not SLICE_RE.match(get("Slice")):
            bad(line("Slice"), f"Slice '{get('Slice')}' is not <ID> or <ID>-<letter>")
    if len(out) > start:
        return None
    return Item(
        id=blk.id,
        title=blk.title,
        line=blk.line,
        type=item_type,
        status=status,
        priority=priority,
        tags=tuple(tags),
        depends_on=tuple(deps),
        assignee=get("Assignee"),
        due=due or WINDOW_START,
        sprint=get("Sprint"),
        spec=get("Spec"),
        version=version,
        outcome=blk.labels["Outcome"][1],
        next_action=blk.labels["Next action"][1],
        evidence=blk.labels["Evidence"][1],
        parent=get("Parent") or None,
        slice=get("Slice") or None,
        field_lines=flines,
    )


# ------------------------------------------------------------------------- validation


def find_secret(text: str) -> str | None:
    """Return the name of the first secret-like pattern in ``text`` (never the value)."""
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            return name
    return None


def _norm_none(value: str) -> bool:
    return value.strip().lower() == "none"


def find_cycle(items: Iterable[Item]) -> list[str] | None:
    """Return one dependency cycle as an ID path (first == last), or None."""
    graph = {i.id: [d for d in i.depends_on] for i in items}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, []):
            if dep not in graph:
                continue
            if state.get(dep, 0) == 1:
                return [*stack[stack.index(dep) :], dep]
            if state.get(dep, 0) == 0:
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if state.get(node, 0) == 0:
            found = visit(node)
            if found:
                return found
    return None


def validate(items: Sequence[Item], base_dir: Path | None = None) -> list[Violation]:
    """Semantic BK-1 rules over parsed items. ``base_dir`` resolves ``Spec`` paths."""
    out: list[Violation] = []
    by_id = {i.id: i for i in items}

    def bad(item: Item, msg: str, name: str | None = None) -> None:
        out.append(Violation(item.field_lines.get(name or "", item.line), msg, item.id))

    for item in items:
        for dep in item.depends_on:
            if dep == item.id:
                bad(item, "depends on itself", "Depends on")
            elif dep not in by_id:
                bad(item, f"dependency {dep} does not exist", "Depends on")
        if item.is_feature and item.parent:
            bad(item, "features have no Parent", "Parent")
        if not item.is_feature:
            parent = by_id.get(item.parent or "")
            if parent is None:
                bad(item, f"Parent {item.parent} does not exist", "Parent")
            elif not parent.is_feature:
                bad(item, f"Parent {item.parent} is not a feature", "Parent")
            if item.slice and item.parent and not item.slice.startswith(item.parent):
                bad(item, f"Slice {item.slice} does not belong to Parent {item.parent}", "Slice")
        if item.is_done:
            if _norm_none(item.version):
                bad(item, "done items need a Version", "Version")
            if item.evidence.strip().rstrip(".").lower() == "none yet":
                bad(item, "done items need real Evidence, not 'none yet'")
            if item.due > WINDOW_END:
                bad(item, f"Due {item.due} is after the deadline {WINDOW_END}", "Due")
            for dep in item.depends_on:
                target = by_id.get(dep)
                if target is not None and not target.is_done:
                    bad(item, f"done item depends on {dep} which is {target.status}", "Depends on")
        elif item.status != "cancelled":
            if not WINDOW_START <= item.due <= WINDOW_END:
                bad(item, f"Due {item.due} outside {WINDOW_START}..{WINDOW_END}", "Due")
            for dep in item.depends_on:
                target = by_id.get(dep)
                if target is not None and target.due > item.due:
                    bad(
                        item,
                        f"Due {item.due} is before dependency {dep} due {target.due}",
                        "Due",
                    )
        if not _norm_none(item.spec) and base_dir is not None:
            path = item.spec.split("#", 1)[0]
            if "://" not in path and not (base_dir / path).exists():
                bad(item, f"Spec path '{path}' does not exist", "Spec")
        secret = find_secret(" ".join((item.title, item.outcome, item.next_action, item.evidence)))
        if secret:
            bad(item, f"secret-like text ({secret}) in item")
    cycle = find_cycle(items)
    if cycle:
        first = by_id[cycle[0]]
        bad(first, "dependency cycle: " + " -> ".join(cycle), "Depends on")
    out.sort(key=lambda v: v.line)
    return out


@dataclass(frozen=True)
class Ledger:
    items: tuple[Item, ...]
    violations: tuple[Violation, ...]

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_id(self) -> dict[str, Item]:
        return {i.id: i for i in self.items}


def load_ledger(path: Path) -> Ledger:
    """Parse and validate a ledger file. Raises OSError only when it cannot be read."""
    text = path.read_text(encoding="utf-8")
    parsed = parse_text(text)
    semantic = validate(parsed.items, path.parent)
    merged = sorted([*parsed.violations, *semantic], key=lambda v: v.line)
    return Ledger(parsed.items, tuple(merged))


# ------------------------------------------------------------- helpers for the Taiga sync


def unmet_dependencies(item: Item, by_id: Mapping[str, Item]) -> list[Item]:
    """Existing dependencies that are not ``done`` (cancelled still counts as unmet)."""
    return [by_id[d] for d in item.depends_on if d in by_id and not by_id[d].is_done]


def blocked_note(item: Item, by_id: Mapping[str, Item]) -> str | None:
    """Spec 4.2 blocker note, or None when done/cancelled or nothing is unmet."""
    if item.status in ("done", "cancelled"):
        return None
    unmet = unmet_dependencies(item, by_id)
    if not unmet:
        return None
    return "Waiting for " + ", ".join(f"{d.id} ({d.status})" for d in unmet)


class SecretInDescription(ValueError):
    """Raised when text destined for an external tracker looks like a credential."""


def render_description(item: Item, by_id: Mapping[str, Item]) -> str:
    """Deterministic Markdown description for the tracker (no file contents, no env values)."""
    lines = [
        f"**Outcome.** {item.outcome}",
        "",
        f"**Next action.** {item.next_action}",
        "",
        f"**Evidence.** {item.evidence}",
        "",
        "**Depends on.**",
    ]
    if item.depends_on:
        for dep in item.depends_on:
            target = by_id.get(dep)
            lines.append(f"- {dep} ({target.status})" if target else f"- {dep} (missing)")
    else:
        lines.append("- none")
    lines += ["", f"**Spec.** {item.spec}", f"**Version.** {item.version}"]
    text = "\n".join(lines) + "\n"
    secret = find_secret(text)
    if secret:
        raise SecretInDescription(f"{item.id}: secret-like text ({secret}); refusing to render")
    return text

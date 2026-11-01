"""Deterministic merge guards G1..G6 (the evidence guard G7 lives with quote validation).

Pure functions over small party records: no I/O, no model. Every check always reports a code,
pass/fail and a short non-sensitive detail, so a blocked proposal shows exactly which rule held.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from fieldlens.identity.merges import ActiveMerge

from .designator import Designator, designator_of, status_marker

GUARD_VERSION = "merge-guards-1"

G1, G2, G3, G4, G5, G6, G7 = (
    "g1_scope",
    "g2_level",
    "g3_designator",
    "g4_sidetrack",
    "g5_planned_as_built",
    "g6_no_chains",
    "g7_evidence",
)
GUARD_CODES = (G1, G2, G3, G4, G5, G6, G7)


@dataclass(frozen=True)
class GuardCheck:
    code: str
    passed: bool
    detail: str

    def as_json(self) -> dict[str, object]:
        return {"code": self.code, "passed": self.passed, "detail": self.detail}


@dataclass(frozen=True)
class Party:
    """A target or member. ``kind`` is ``wellbore`` (resolved row) or ``label`` (raw source name);
    ``key`` is the durable source key (wellbore key or normalized label)."""

    kind: str
    key: str
    name: str
    designator: Designator | None
    wellbore_id: UUID | None = None

    @classmethod
    def wellbore(cls, wellbore_id: UUID, key: str) -> Party:
        return cls("wellbore", key, key, designator_of(key), wellbore_id)

    @classmethod
    def label(cls, key: str, name: str) -> Party:
        return cls("label", key, name, designator_of(name))


def _fmt(items: Sequence[str]) -> str:
    return ", ".join(items[:4]) + (" ..." if len(items) > 4 else "")


def evaluate(
    target: Party,
    members: Sequence[Party],
    merges: Sequence[ActiveMerge],
    *,
    in_project_keys: set[str],
) -> list[GuardCheck]:
    """G1..G6 for one proposed group (G7 is appended by the validator).

    ``in_project_keys`` holds the resolved wellbore keys of the project (for G1 of ``wellbore``
    parties); label parties are known to the caller by construction."""
    out: list[GuardCheck] = []

    # G1 scope: target is a project wellbore; members are distinct and none is the target.
    bad: list[str] = []
    if target.kind != "wellbore" or target.key not in in_project_keys:
        bad.append(f"target {target.key}")
    seen: set[tuple[str, str]] = set()
    for member in members:
        ident = (member.kind, member.key)
        if ident in seen or ident == (target.kind, target.key):
            bad.append(f"duplicate or self member {member.name}")
        seen.add(ident)
        if member.kind == "wellbore" and member.key not in in_project_keys:
            bad.append(f"member {member.key} not in project")
    if not members:
        bad.append("no members")
    out.append(GuardCheck(G1, not bad, "; ".join(bad) or "all parties belong to the project"))

    # G2 level: every party carries a wellbore designator (no field-level or well-only names).
    missing = [p.name for p in (target, *members) if p.designator is None]
    out.append(
        GuardCheck(
            G2,
            not missing,
            ("no wellbore designator: " + _fmt(missing))
            if missing
            else "all names carry a designator",
        )
    )

    # G3 designator equality (well slot + block); G4 suffix equality (sidetrack preserved).
    g3: list[str] = []
    g4: list[str] = []
    t = target.designator
    if t is not None:
        for member in members:
            d = member.designator
            if d is None:
                continue
            if d.slot != t.slot:
                g3.append(f"{member.name}: {d.slot} is not {t.slot}")
            elif d.block and t.block and d.block != t.block:
                g3.append(f"{member.name}: block {d.block} is not {t.block}")
            if d.suffix != t.suffix:
                g4.append(f"{member.name}: suffix {d.suffix or 'none'} is not {t.suffix or 'none'}")
    out.append(GuardCheck(G3, not g3, "; ".join(g3) or "well slot and block agree"))
    out.append(GuardCheck(G4, not g4, "; ".join(g4) or "suffixes agree; sidetracks stay distinct"))

    # G5 planned vs as-built: all names share the same lexical marker (or none).
    marks = {p.name: status_marker(p.name) for p in (target, *members)}
    distinct = set(marks.values())
    g5_fail = len(distinct) > 1 or "mixed" in distinct
    out.append(
        GuardCheck(
            G5,
            not g5_fail,
            "planned and as-built names are never mixed"
            if g5_fail
            else "no planned/as-built conflict",
        )
    )

    # G6 no chains: sources are not active targets, the target is not an active source and no
    # source already has an active merge.
    active_sources = {(m.source_kind, m.source_key) for m in merges}
    active_targets = {m.target_key for m in merges}
    g6: list[str] = []
    if (target.kind, target.key) in active_sources:
        g6.append(f"target {target.key} is itself merged away")
    for member in members:
        if (member.kind, member.key) in active_sources:
            g6.append(f"{member.name} already has an active merge")
        if member.kind == "wellbore" and member.key in active_targets:
            g6.append(f"{member.name} is the target of an active merge")
    out.append(GuardCheck(G6, not g6, "; ".join(g6) or "no merge chain"))
    return out


def failed(checks: Sequence[GuardCheck]) -> list[GuardCheck]:
    return [c for c in checks if not c.passed]

"""Deterministic well/wellbore identity resolution (post-extraction, per project, idempotent).

Pure analysis (``analyze``) over the distinct record subjects of a project, then a set-based
write (``resolve_project``). No model call, no guess:

* a subject resolves from the first parseable bore label (``wellbore_label``, ``wellbore_name``,
  else ``well_name``) using the shared rule in :mod:`fieldlens.identity.labels`; field-level
  names such as ``Volve F`` are skipped;
* the structured ``well_key`` and every other parseable label of the SAME record must name the
  same well; an unqualified spelling (``F-12``) joins a block-qualified one only when exactly one
  qualified well in the project has that short name; a contradiction or several candidates are
  ``ambiguous``: no row, no link, an ``IDENTITY_MISMATCH`` finding on the affected run;
* a suffixed bore (``F-11 B``) is a distinct wellbore whose parent is the well's base wellbore
  when that base wellbore is itself observed (a name-based link, not a verified drilling
  relationship); ``F-12``, ``F-12 A``, ``F-12 H`` never merge;
* identities are scoped to the project; nothing is shared across projects.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import bindparam, delete, func, insert, literal, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from fieldlens.persistence import models as m

from .labels import BoreLabel, parse_bore_label
from .tables import record_wellbore_link

logger = logging.getLogger(__name__)

RESOLVER_VERSION = "identity-1"
OK_STATUSES = ("succeeded", "partial")
MAX_ORDINALS = 200
MAX_LOCATORS = 5
RANGE_TOLERANCE = 0.05  # DC-3: a defaulted MD beyond the known MD range by more than 5%
ISSUE_PREFIX = "identity_resolution:"
_LABEL_KEYS = ("wellbore_label", "wellbore_name", "well_name")

# DC-3 inputs: which attributes carry a defaulted measured depth, which carry a known MD range.
_DEFAULTED_MD = {
    "perforation_interval": ("perforation.top_md", "perforation.base_md"),
    "formation_pick": ("pick.md",),
}
_RANGE_ATTRS = {
    "trajectory_station": ("trajectory_station.md",),
    "las_header": ("las_header.stop", "las_header.last_index"),
}


@dataclass(frozen=True)
class Resolved:
    bore: BoreLabel  # always block-qualified

    @property
    def well_name(self) -> str:
        return self.bore.well_name

    @property
    def wellbore_name(self) -> str:
        return self.bore.wellbore_name


@dataclass(frozen=True)
class Unresolved:
    reason: str  # not_a_well | unqualified_label | ambiguous
    detail: str
    ambiguous: bool = False


Outcome = Resolved | Unresolved


def _str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _labels(subject: dict[str, Any]) -> list[tuple[str, BoreLabel]]:
    hint = _str(subject.get("wellbore_suffix"))
    out: list[tuple[str, BoreLabel]] = []
    for key in _LABEL_KEYS:
        text_ = _str(subject.get(key))
        if text_ is None:
            continue
        parsed = parse_bore_label(text_, hint)
        if parsed is not None:
            out.append((key, parsed))
    return out


def _tails(subjects: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Short slot (``F-12``) -> qualified well names the project's subjects write."""
    found: dict[str, set[str]] = defaultdict(set)
    for subject in subjects:
        candidates = [b for _, b in _labels(subject)]
        key = _str(subject.get("well_key"))
        parsed_key = parse_bore_label(key) if key else None
        if parsed_key is not None:
            candidates.append(parsed_key)
        for bore in candidates:
            if bore.block:
                found[bore.well_slot].add(bore.well_name)
    return found


def resolve_subject(subject: dict[str, Any], tails: dict[str, set[str]]) -> Outcome:
    labels = _labels(subject)
    key = _str(subject.get("well_key"))
    parsed_key = parse_bore_label(key) if key else None
    if parsed_key is not None and parsed_key.suffix:
        parsed_key = None  # a well key never names a bore; ignore a malformed one
    if not labels and parsed_key is None:
        return Unresolved("not_a_well", "no well or wellbore label parses as an identifier")
    # The bore: wellbore labels first, else the well label, else the structured key.
    bore_pick = next((b for k, b in labels if k != "well_name"), None) or next(
        (b for _, b in labels), None
    )
    bore = bore_pick if bore_pick is not None else BoreLabel(None, parsed_key.well_slot, None)  # type: ignore[union-attr]
    qualified = {b.well_name for _, b in labels if b.block}
    if parsed_key is not None and parsed_key.block:
        qualified.add(parsed_key.well_name)
    slots = {b.well_slot for _, b in labels} | ({parsed_key.well_slot} if parsed_key else set())
    if len(qualified) > 1 or len(slots) > 1:
        return Unresolved(
            "ambiguous",
            "labels in one record name different wells: " + ", ".join(sorted(qualified | slots)),
            True,
        )
    if qualified:
        well = next(iter(qualified))
        block = well.rsplit("-" + bore.well_slot, 1)[0]
        return Resolved(BoreLabel(block, bore.well_slot, bore.suffix))
    candidates = sorted(tails.get(bore.well_slot, ()))
    if len(candidates) == 1:
        block = candidates[0].rsplit("-" + bore.well_slot, 1)[0]
        return Resolved(BoreLabel(block, bore.well_slot, bore.suffix))
    if len(candidates) > 1:
        return Unresolved(
            "ambiguous",
            f"{bore.well_slot} exists in several blocks of this project: " + ", ".join(candidates),
            True,
        )
    return Unresolved(
        "unqualified_label",
        f"{bore.well_slot} has no block qualifier and no block-qualified source names it",
    )


@dataclass
class SubjectGroup:
    subject: dict[str, Any]
    outcome: Outcome
    runs: dict[UUID, list[int]] = field(default_factory=dict)  # run -> sample ordinals
    kinds: dict[str, int] = field(default_factory=dict)
    documents: set[UUID] = field(default_factory=set)
    records: int = 0

    @property
    def label(self) -> str:
        for key in _LABEL_KEYS:
            if (v := _str(self.subject.get(key))) is not None:
                return v
        return _str(self.subject.get("well_key")) or "(no label)"


def current_subject_groups(session: Session, project_id: UUID) -> list[SubjectGroup]:
    """Distinct subjects of the project's current successful runs, with per-run bounded
    ordinals, kind counts and documents, resolved by the shared rule."""
    er, ru = m.extracted_record, m.extraction_run
    rows = session.execute(
        select(
            er.c.subject,
            er.c.run_id,
            er.c.document_id,
            er.c.kind,
            func.count().label("n"),
            func.min(er.c.ordinal).label("first"),
        )
        .join(ru, ru.c.run_id == er.c.run_id)
        .where(
            ru.c.project_id == project_id,
            ru.c.superseded.is_(False),
            ru.c.status.in_(OK_STATUSES),
        )
        .group_by(er.c.subject, er.c.run_id, er.c.document_id, er.c.kind)
    ).all()
    by_subject: dict[str, SubjectGroup] = {}
    subjects: dict[str, dict[str, Any]] = {}
    for row in rows:
        sk = json.dumps(row.subject, sort_keys=True)
        subjects[sk] = row.subject
    tails = _tails(list(subjects.values()))
    for row in rows:
        sk = json.dumps(row.subject, sort_keys=True)
        group = by_subject.get(sk)
        if group is None:
            group = by_subject[sk] = SubjectGroup(row.subject, resolve_subject(row.subject, tails))
        group.records += row.n
        group.kinds[row.kind] = group.kinds.get(row.kind, 0) + row.n
        group.documents.add(row.document_id)
        group.runs.setdefault(row.run_id, []).append(row.first)
    return list(by_subject.values())


@dataclass
class ResolveOutcome:
    wells: int
    wellbores: int
    linked_records: int
    unresolved_records: int
    identity_findings: int
    range_findings: int


def _lock(session: Session, project_id: UUID) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"identity:{project_id}"}
    )


def resolve_project(session: Session, project_id: UUID) -> ResolveOutcome:
    """Rebuild the project's identities from its current extraction output (idempotent: stable
    row ids by key, links and findings replaced atomically). Caller commits."""
    _lock(session, project_id)
    groups = current_subject_groups(session, project_id)
    resolved = [g for g in groups if isinstance(g.outcome, Resolved)]
    wells = sorted({g.outcome.well_name for g in resolved})  # type: ignore[union-attr]
    bores: dict[str, BoreLabel] = {}
    for g in resolved:
        assert isinstance(g.outcome, Resolved)
        bores[g.outcome.wellbore_name] = g.outcome.bore

    w, wb = m.well, m.wellbore
    # Release links and parent pointers, drop identities no longer supported, upsert the rest.
    session.execute(
        delete(record_wellbore_link).where(record_wellbore_link.c.project_id == project_id)
    )
    session.execute(update(wb).where(wb.c.project_id == project_id).values(parent_wellbore_id=None))
    session.execute(
        delete(wb).where(
            wb.c.project_id == project_id, wb.c.wellbore_key.notin_(list(bores) or [""])
        )
    )
    well_ids: dict[str, UUID] = {}
    for name in wells:
        stmt = (
            pg_insert(w)
            .values(well_id=uuid4(), project_id=project_id, name=name, well_key=name)
            .on_conflict_do_update(
                index_elements=[w.c.project_id, w.c.well_key], set_={"name": name}
            )
            .returning(w.c.well_id)
        )
        well_ids[name] = session.execute(stmt).scalar_one()
    bore_ids: dict[str, UUID] = {}
    for name, bore in sorted(bores.items()):
        stmt = (
            pg_insert(wb)
            .values(
                wellbore_id=uuid4(),
                project_id=project_id,
                well_id=well_ids[bore.well_name],
                name=name,
                wellbore_key=name,
                suffix=bore.suffix,
            )
            .on_conflict_do_update(
                index_elements=[wb.c.project_id, wb.c.wellbore_key],
                set_={"name": name, "suffix": bore.suffix, "well_id": well_ids[bore.well_name]},
            )
            .returning(wb.c.wellbore_id)
        )
        bore_ids[name] = session.execute(stmt).scalar_one()
    for name, bore in bores.items():
        if bore.suffix and bore.well_name in bore_ids:
            session.execute(
                update(wb)
                .where(wb.c.wellbore_id == bore_ids[name])
                .values(parent_wellbore_id=bore_ids[bore.well_name])
            )
    # Remove wells without wellbores (a well exists only through an observed bore).
    session.execute(
        delete(w).where(
            w.c.project_id == project_id,
            ~w.c.well_id.in_(select(wb.c.well_id).where(wb.c.project_id == project_id)),
        )
    )
    er, ru = m.extracted_record, m.extraction_run
    for g in resolved:
        assert isinstance(g.outcome, Resolved)
        wid = bore_ids[g.outcome.wellbore_name]
        sel = (
            select(er.c.run_id, er.c.ordinal, ru.c.project_id, literal(wid), literal("label"))
            .join(ru, ru.c.run_id == er.c.run_id)
            .where(
                ru.c.project_id == project_id,
                ru.c.superseded.is_(False),
                ru.c.status.in_(OK_STATUSES),
                er.c.subject == bindparam("subj", g.subject, type_=JSONB),
            )
        )
        session.execute(
            insert(record_wellbore_link).from_select(
                ["run_id", "ordinal", "project_id", "wellbore_id", "basis"], sel
            )
        )

    linked = session.execute(
        select(func.count())
        .select_from(record_wellbore_link)
        .where(record_wellbore_link.c.project_id == project_id)
    ).scalar_one()
    identity_findings = _replace_findings(session, project_id, groups, bore_ids)
    range_findings = _range_findings(session, project_id, bore_ids)
    unresolved = sum(g.records for g in groups if isinstance(g.outcome, Unresolved))
    return ResolveOutcome(
        len(well_ids), len(bore_ids), linked, unresolved, identity_findings, range_findings
    )


def _issue_id(run_id: UUID, key: str) -> UUID:
    from fieldlens.extraction.runner import issue_id

    return issue_id(run_id, key)


def _key(prefix: str, token: str) -> str:
    digest = hashlib.sha256(token.encode()).hexdigest()[:16]
    return f"{ISSUE_PREFIX}{prefix}:{digest}"[:256]


def _insert_issues(session: Session, rows: list[dict[str, Any]]) -> None:
    if rows:
        session.execute(insert(m.extraction_issue), rows)


def _replace_findings(
    session: Session, project_id: UUID, groups: list[SubjectGroup], bore_ids: dict[str, UUID]
) -> int:
    ei = m.extraction_issue
    session.execute(
        delete(ei).where(ei.c.project_id == project_id, ei.c.producer_key.like(f"{ISSUE_PREFIX}%"))
    )
    rows: list[dict[str, Any]] = []
    for g in groups:
        out = g.outcome
        if not (isinstance(out, Unresolved) and out.ambiguous):
            continue
        token = json.dumps(g.subject, sort_keys=True)
        for run_id in sorted(g.runs, key=str):
            key = _key("IDENTITY_MISMATCH", token)
            ords = _ordinals(session, run_id, g.subject)
            rows.append(
                {
                    "issue_id": _issue_id(run_id, key),
                    "project_id": project_id,
                    "run_id": run_id,
                    "producer_key": key,
                    "code": "IDENTITY_MISMATCH",
                    "severity": "warning",
                    "message": (
                        f"Label {g.label!r} cannot be resolved to one well: {out.detail}. "
                        "No well or wellbore row was created and these records are not linked "
                        "to a wellbore; the names are not merged."
                    ),
                    "attribute_keys": [],
                    "record_ordinals": ords[:MAX_ORDINALS],
                    "locators": [],
                    "blocked_operations": ["claim_acceptance"],
                }
            )
    _insert_issues(session, rows)
    return len(rows)


def _ordinals(session: Session, run_id: UUID, subject: dict[str, Any]) -> list[int]:
    er = m.extracted_record
    return list(
        session.execute(
            select(er.c.ordinal)
            .where(er.c.run_id == run_id, er.c.subject == bindparam("subj", subject, type_=JSONB))
            .order_by(er.c.ordinal)
            .limit(MAX_ORDINALS)
        ).scalars()
    )


def _norm_m(attr: dict[str, Any]) -> float | None:
    value = attr.get("normalized_number")
    if attr.get("normalized_unit") == "m" and isinstance(value, int | float):
        return float(value)
    return None


def _range_findings(session: Session, project_id: UUID, bore_ids: dict[str, UUID]) -> int:
    """DC-3: a defaulted (unit-less) MD beyond the wellbore's known MD range (trajectory stations
    or log header) by more than 5% is a SUSPICIOUS_VALUE warning; the value never changes and a
    wellbore with no range gets no check. Only the deep end is checked: logs and surveys do not
    legitimately end before a perforation or pick, but they may start below the surface."""
    if not bore_ids:
        return 0
    er, lk = m.extracted_record, record_wellbore_link
    rows = session.execute(
        select(lk.c.wellbore_id, er.c.run_id, er.c.ordinal, er.c.kind, er.c.attributes)
        .join(er, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
        .where(
            lk.c.project_id == project_id,
            er.c.kind.in_([*_RANGE_ATTRS, *_DEFAULTED_MD]),
        )
    ).all()
    high: dict[UUID, tuple[float, str]] = {}
    for row in rows:
        keys = _RANGE_ATTRS.get(row.kind)
        if not keys:
            continue
        for attr in row.attributes:
            if attr.get("key") in keys and (v := _norm_m(attr)) is not None:
                label = "trajectory" if row.kind == "trajectory_station" else "log"
                if row.wellbore_id not in high or v > high[row.wellbore_id][0]:
                    high[row.wellbore_id] = (v, label)
    flagged: dict[tuple[UUID, UUID], list[tuple[int, dict[str, Any], float]]] = defaultdict(list)
    for row in rows:
        keys = _DEFAULTED_MD.get(row.kind)
        if not keys or row.wellbore_id not in high:
            continue
        limit = high[row.wellbore_id][0] * (1 + RANGE_TOLERANCE)
        for attr in row.attributes:
            if (
                attr.get("key") in keys
                and attr.get("unit") is None
                and attr.get("validation_state") == "unreviewed"
                and (v := _norm_m(attr)) is not None
                and v > limit
            ):
                flagged[(row.run_id, row.wellbore_id)].append((row.ordinal, attr, v))
    names = {wid: name for name, wid in bore_ids.items()}
    out: list[dict[str, Any]] = []
    for (run_id, wid), items in sorted(
        flagged.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))
    ):
        top, source = high[wid]
        key = _key("SUSPICIOUS_VALUE", f"{wid}")
        worst = max(v for _, _, v in items)
        out.append(
            {
                "issue_id": _issue_id(run_id, key),
                "project_id": project_id,
                "run_id": run_id,
                "producer_key": key,
                "code": "SUSPICIOUS_VALUE",
                "severity": "warning",
                "message": (
                    f"{len(items)} depth value(s) for {names[wid]} assumed to be meters (no unit "
                    f"stated) exceed the known {source} MD range (max {top:g} m) by more than "
                    f"{RANGE_TOLERANCE:.0%} (deepest {worst:g}); the unit may differ. Values "
                    "are unchanged."
                ),
                "attribute_keys": sorted({a["key"] for _, a, _ in items}),
                "record_ordinals": sorted({o for o, _, _ in items})[:MAX_ORDINALS],
                "locators": [a.get("locator") for _, a, _ in items[:MAX_LOCATORS]],
                "blocked_operations": [],
            }
        )
    _insert_issues(session, out)
    return len(out)

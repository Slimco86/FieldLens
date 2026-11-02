"""Deterministic candidate blocking over the resolver's output (one project, no model).

A block is one resolved target wellbore plus the names that pass the deterministic guards G1..G6
against it: raw labels the resolver could not resolve, and other resolved wellbores that differ only
in spelling (for example the block written ``15/09``). Names that would break a guard are never
shown to the model, so the model can only choose among guard-compatible candidates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldlens.identity.merges import ActiveMerge, active_merges, label_key
from fieldlens.identity.resolver import (
    _LABEL_KEYS,
    RESOLVER_VERSION,
    Resolved,
    SubjectGroup,
    Unresolved,
    _str,
    current_subject_groups,
)
from fieldlens.persistence import models as m

from . import guards
from .designator import Designator, designator_of
from .guards import Party
from .tables import merge_proposal, merge_proposal_member

MAX_MEMBERS_PER_BLOCK = 8
MAX_FAMILY = 4
MAX_BLOCKS = 60
MAX_DOCS = 5


@dataclass
class MemberCandidate:
    party: Party
    documents: list[UUID] = field(default_factory=list)
    records: int = 0


@dataclass
class Block:
    target: Party
    target_documents: list[UUID]
    members: list[MemberCandidate]
    allow_short_target: bool
    family: list[MemberCandidate] = field(default_factory=list)
    """Same-slot names that FAIL a guard (``F-12 A`` beside ``F-12``): shown to the model as
    distinct wellbores. A model group that still includes one is persisted ``blocked``."""

    @property
    def block_id(self) -> str:
        raw = json.dumps(
            [self.target.key, [(c.party.kind, c.party.key) for c in self.members]]
        ).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    @property
    def all_documents(self) -> list[UUID]:
        seen: dict[UUID, None] = dict.fromkeys(self.target_documents)
        for c in (*self.members, *self.family):
            seen.update(dict.fromkeys(c.documents))
        return list(seen)


@dataclass
class Dataset:
    fingerprint: str
    blocks: list[Block]
    resolved: dict[str, UUID]  # wellbore key -> id
    merges: list[ActiveMerge]
    deferred_blocks: int = 0
    resolved_current: bool = True


def _docs(values: set[UUID]) -> list[UUID]:
    return sorted(values, key=str)[:MAX_DOCS]


def rejected_pairs(session: Session, project_id: UUID) -> set[tuple[str, str, str]]:
    """(target_key, member kind, member key) the user already rejected: never proposed again."""
    p, mm = merge_proposal, merge_proposal_member
    rows = session.execute(
        select(p.c.target_key, mm.c.kind, mm.c.source_key)
        .join(mm, mm.c.proposal_id == p.c.proposal_id)
        .where(p.c.project_id == project_id, p.c.status == "rejected", mm.c.role == "member")
    ).all()
    return {(r.target_key, r.kind, r.source_key) for r in rows}


@dataclass
class _Inputs:
    bores: dict[str, UUID]
    groups: list[SubjectGroup]
    merges: list[ActiveMerge]
    bore_docs: dict[str, set[UUID]]
    label_docs: dict[str, tuple[str, set[UUID], int]]
    fingerprint: str
    resolved_current: bool


def _inputs(session: Session, project_id: UUID) -> _Inputs:
    bores = {
        r.wellbore_key: r.wellbore_id
        for r in session.execute(
            select(m.wellbore.c.wellbore_id, m.wellbore.c.wellbore_key).where(
                m.wellbore.c.project_id == project_id, m.wellbore.c.wellbore_key.is_not(None)
            )
        )
    }
    groups = current_subject_groups(session, project_id)
    merges = active_merges(session, project_id)
    bore_docs: dict[str, set[UUID]] = {}
    label_docs: dict[str, tuple[str, set[UUID], int]] = {}
    for g in groups:
        o = g.outcome
        if isinstance(o, Resolved):
            bore_docs.setdefault(o.wellbore_name, set()).update(g.documents)
        elif isinstance(o, Unresolved):
            for key in _LABEL_KEYS:
                text_ = _str(g.subject.get(key))
                if text_ is None:
                    continue
                lk = label_key(text_)
                name, docs, n = label_docs.get(lk, (text_, set(), 0))
                label_docs[lk] = (name, docs | g.documents, n + g.records)
    run_ids = sorted({str(r) for g in groups for r in g.runs})
    merge_sig = sorted((x.source_kind, x.source_key, x.target_key) for x in merges)
    fingerprint = hashlib.sha256(
        json.dumps(
            [RESOLVER_VERSION, sorted(bores), sorted(label_docs), run_ids, merge_sig]
        ).encode()
    ).hexdigest()
    return _Inputs(
        bores, groups, merges, bore_docs, label_docs, fingerprint, set(bores) == set(bore_docs)
    )


def current_fingerprint(session: Session, project_id: UUID) -> str:
    """Dataset fingerprint: resolver version, resolved wellbores, unresolved labels, current
    extraction runs and active merges. Versions every proposal context."""
    return _inputs(session, project_id).fingerprint


def build_dataset(session: Session, project_id: UUID, *, max_blocks: int = MAX_BLOCKS) -> Dataset:
    inp = _inputs(session, project_id)
    bores, merges, bore_docs, label_docs = inp.bores, inp.merges, inp.bore_docs, inp.label_docs
    fingerprint = inp.fingerprint

    excluded = rejected_pairs(session, project_id)
    well_slot_count: dict[str, set[str]] = {}
    for key in bores:
        d = designator_of(key)
        if d is not None and d.block:
            well_slot_count.setdefault(d.slot, set()).add(d.block)
    blocks: list[Block] = []
    for key in sorted(bores):
        target = Party.wellbore(bores[key], key)
        td: Designator | None = target.designator
        if td is None:
            continue
        cands: list[MemberCandidate] = []
        family: list[MemberCandidate] = []
        pool = [
            MemberCandidate(Party.wellbore(bid, bk), _docs(bore_docs.get(bk, set())))
            for bk, bid in sorted(bores.items())
            if bk != key
        ] + [
            MemberCandidate(Party.label(lk, name), _docs(docs), n)
            for lk, (name, docs, n) in sorted(label_docs.items())
        ]
        for cand in pool:
            if (key, cand.party.kind, cand.party.key) in excluded:
                continue
            cd = cand.party.designator
            if td.block is None and cand.party.kind == "wellbore" and cd is not None and cd.block:
                # D9: the pair is proposed once, with the block-qualified wellbore as target.
                continue
            checks = guards.evaluate(target, [cand.party], merges, in_project_keys=set(bores))
            if guards.failed(checks):
                dd = cand.party.designator
                if dd is not None and dd.slot == td.slot and len(family) < MAX_FAMILY:
                    family.append(cand)
                continue
            cands.append(cand)
        if cands:
            blocks.append(
                Block(
                    target,
                    _docs(bore_docs.get(key, set())),
                    cands[:MAX_MEMBERS_PER_BLOCK],
                    allow_short_target=len(well_slot_count.get(td.slot, ())) <= 1,
                    family=family,
                )
            )
    deferred = max(len(blocks) - max_blocks, 0)
    return Dataset(fingerprint, blocks[:max_blocks], bores, merges, deferred, inp.resolved_current)

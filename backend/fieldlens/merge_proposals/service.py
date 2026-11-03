"""Persistence and review of merge proposals: store a run, list, accept, reject, revert.

Accepting is the only path that changes identity: one transaction that re-checks the proposal
(state, guards, staleness), inserts the revertible ``identity_merge`` rows and re-resolves the
project. Nothing here is reachable from model output without a user request."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.merge_proposals import (
    MergeEvidenceQuote,
    MergeGuardResult,
    MergeProposal,
    MergeProposalMember,
    MergeProposalPage,
    MergeProposalRun,
    MergeProposalRunPage,
    MergeProposalStatus,
    MergeRunCall,
)
from fieldlens.identity.labels import parse_bore_label
from fieldlens.identity.resolver import resolve_project
from fieldlens.identity.service import require_project
from fieldlens.identity.tables import identity_merge
from fieldlens.persistence import models as m

from . import guards, hooks
from .blocking import _inputs, current_fingerprint
from .guards import G7, GuardCheck, Party
from .tables import merge_proposal, merge_proposal_member, merge_proposal_run
from .validation import ValidProposal

P, MM, RUN = merge_proposal, merge_proposal_member, merge_proposal_run
MAX_NOTE = 500


def _now() -> datetime:
    return datetime.now(UTC)


def _conflict(reason: str, message: str, **details: Any) -> ContractError:
    return ContractError(ErrorCode.CONFLICT, message, 409, {"reason": reason, **details})


# --- storing a run -------------------------------------------------------------------------


def store_run(
    session: Session,
    project_id: UUID,
    *,
    state: str,
    reason: str | None,
    model_id: str,
    prompt_version: str,
    fingerprint: str,
    blocks: int,
    deferred: int,
    proposals: list[ValidProposal],
    drops: Counter[str],
    calls: list[dict[str, Any]],
    created_at: datetime,
) -> UUID:
    tokens_in = [c["input_tokens"] for c in calls if c.get("input_tokens") is not None]
    tokens_out = [c["output_tokens"] for c in calls if c.get("output_tokens") is not None]
    costs = [Decimal(str(c["cost_usd"])) for c in calls if c.get("cost_usd") is not None]
    run_id = uuid4()
    session.execute(
        insert(RUN).values(
            run_id=run_id,
            project_id=project_id,
            state=state,
            reason=reason,
            model_id=model_id[:80],
            prompt_version=prompt_version,
            guard_version=guards.GUARD_VERSION,
            dataset_fingerprint=fingerprint,
            blocks=blocks,
            deferred_blocks=deferred,
            proposals_created=len(proposals),
            proposals_dropped=sum(drops.values()),
            drop_reasons=dict(drops),
            calls=calls,
            provider_calls=sum(int(c.get("attempts", 0)) for c in calls),
            input_tokens=sum(tokens_in) if tokens_in else None,
            output_tokens=sum(tokens_out) if tokens_out else None,
            cost_usd=sum(costs, Decimal(0)) if costs else None,
            created_at=created_at,
            finished_at=_now(),
        )
    )
    for prop in proposals:
        proposal_id = uuid4()
        session.execute(
            insert(P).values(
                proposal_id=proposal_id,
                project_id=project_id,
                run_id=run_id,
                status=prop.status,
                target_wellbore_id=prop.block.target.wellbore_id,
                target_key=prop.block.target.key,
                guard_result=[c.as_json() for c in prop.checks],
                rationale=prop.rationale,
                dataset_fingerprint=fingerprint,
            )
        )
        rows: list[dict[str, Any]] = [
            {
                "proposal_id": proposal_id,
                "ordinal": 0,
                "project_id": project_id,
                "role": "target",
                "kind": "wellbore",
                "source_key": prop.block.target.key,
                "display_name": prop.block.target.name,
                "wellbore_id": prop.block.target.wellbore_id,
                "evidence": [],
            }
        ]
        for i, (cand, evidence) in enumerate(prop.members, start=1):
            rows.append(
                {
                    "proposal_id": proposal_id,
                    "ordinal": i,
                    "project_id": project_id,
                    "role": "member",
                    "kind": cand.party.kind,
                    "source_key": cand.party.key,
                    "display_name": cand.party.name,
                    "wellbore_id": cand.party.wellbore_id,
                    "evidence": [e.as_json() for e in evidence],
                }
            )
        session.execute(insert(MM), rows)
    return run_id


def taken_pairs(session: Session, project_id: UUID) -> set[tuple[str, str, str]]:
    """(target key, member kind, member key) already proposed and not rejected/reverted."""
    rows = session.execute(
        select(P.c.target_key, MM.c.kind, MM.c.source_key)
        .join(MM, MM.c.proposal_id == P.c.proposal_id)
        .where(
            P.c.project_id == project_id,
            P.c.status.in_(("pending", "blocked", "accepted")),
            MM.c.role == "member",
        )
    ).all()
    return {(r.target_key, r.kind, r.source_key) for r in rows}


# --- reading -------------------------------------------------------------------------------


def _member_dto(row: Any) -> MergeProposalMember:
    return MergeProposalMember(
        role=row.role,
        kind=row.kind,
        name=row.display_name,
        key=row.source_key,
        wellbore_id=row.wellbore_id,
        evidence=[MergeEvidenceQuote.model_validate(e) for e in row.evidence],
    )


def _proposals(
    session: Session, project_id: UUID, rows: list[Any], current: str
) -> list[MergeProposal]:
    if not rows:
        return []
    ids = [r.proposal_id for r in rows]
    members = session.execute(
        select(MM).where(MM.c.proposal_id.in_(ids)).order_by(MM.c.proposal_id, MM.c.ordinal)
    ).all()
    by_id: dict[UUID, list[Any]] = {}
    for mem in members:
        by_id.setdefault(mem.proposal_id, []).append(mem)
    out: list[MergeProposal] = []
    for r in rows:
        parts = by_id.get(r.proposal_id, [])
        target = next(x for x in parts if x.role == "target")
        results = [MergeGuardResult.model_validate(c) for c in r.guard_result]
        out.append(
            MergeProposal(
                proposal_id=r.proposal_id,
                project_id=r.project_id,
                run_id=r.run_id,
                status=MergeProposalStatus(r.status),
                target=_member_dto(target),
                members=[_member_dto(x) for x in parts if x.role == "member"],
                guard_results=results,
                acceptable=r.status == "pending" and all(c.passed for c in results),
                rationale=r.rationale,
                dataset_fingerprint=r.dataset_fingerprint,
                dataset_current=r.dataset_fingerprint == current,
                decided_by=r.decided_by,
                decided_at=r.decided_at,
                decision_note=r.decision_note,
                created_at=r.created_at,
            )
        )
    return out


def list_proposals(
    session: Session, project_id: UUID, status: str | None, limit: int
) -> MergeProposalPage:
    require_project(session, project_id)
    cond = [P.c.project_id == project_id]
    if status is not None:
        cond.append(P.c.status == status)
    total = session.execute(select(func.count()).select_from(P).where(*cond)).scalar_one()
    rows = session.execute(
        select(P).where(*cond).order_by(P.c.created_at.desc(), P.c.proposal_id.desc()).limit(limit)
    ).all()
    current = current_fingerprint(session, project_id)
    return MergeProposalPage(
        items=_proposals(session, project_id, list(rows), current), total=total
    )


def get_proposal(session: Session, project_id: UUID, proposal_id: UUID) -> MergeProposal:
    require_project(session, project_id)
    row = session.execute(
        select(P).where(P.c.project_id == project_id, P.c.proposal_id == proposal_id)
    ).first()
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "merge proposal not found", 404)
    return _proposals(session, project_id, [row], current_fingerprint(session, project_id))[0]


def _run_dto(r: Any) -> MergeProposalRun:
    return MergeProposalRun(
        run_id=r.run_id,
        project_id=r.project_id,
        state=r.state,
        reason=r.reason,
        model_id=r.model_id,
        prompt_version=r.prompt_version,
        guard_version=r.guard_version,
        dataset_fingerprint=r.dataset_fingerprint,
        blocks=r.blocks,
        deferred_blocks=r.deferred_blocks,
        proposals_created=r.proposals_created,
        proposals_dropped=r.proposals_dropped,
        drop_reasons=r.drop_reasons,
        calls=[MergeRunCall.model_validate(c) for c in r.calls],
        provider_calls=r.provider_calls,
        input_tokens=r.input_tokens,
        output_tokens=r.output_tokens,
        cost_usd=r.cost_usd,
        created_at=r.created_at,
        finished_at=r.finished_at,
    )


def get_run(session: Session, project_id: UUID, run_id: UUID) -> MergeProposalRun:
    row = session.execute(
        select(RUN).where(RUN.c.project_id == project_id, RUN.c.run_id == run_id)
    ).one()
    return _run_dto(row)


def list_runs(session: Session, project_id: UUID, limit: int = 50) -> MergeProposalRunPage:
    require_project(session, project_id)
    rows = session.execute(
        select(RUN)
        .where(RUN.c.project_id == project_id)
        .order_by(RUN.c.created_at.desc(), RUN.c.run_id.desc())
        .limit(limit)
    ).all()
    return MergeProposalRunPage(items=[_run_dto(r) for r in rows])


# --- decisions -----------------------------------------------------------------------------


def _locked(session: Session, project_id: UUID, proposal_id: UUID) -> Any:
    require_project(session, project_id)
    row = session.execute(
        select(P)
        .where(P.c.project_id == project_id, P.c.proposal_id == proposal_id)
        .with_for_update()
    ).first()
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "merge proposal not found", 404)
    return row


def _decide(
    session: Session, proposal_id: UUID, status: str, decided_by: str, note: str | None
) -> None:
    session.execute(
        update(P)
        .where(P.c.proposal_id == proposal_id)
        .values(
            status=status,
            decided_by=decided_by[:80],
            decided_at=_now(),
            decision_note=note[:MAX_NOTE] if note else None,
        )
    )


def reject(
    session: Session, project_id: UUID, proposal_id: UUID, decided_by: str, note: str | None
) -> MergeProposal:
    row = _locked(session, project_id, proposal_id)
    if row.status not in ("pending", "blocked"):
        raise _conflict("invalid_transition", f"a {row.status} proposal cannot be rejected")
    _decide(session, proposal_id, "rejected", decided_by, note)
    return get_proposal(session, project_id, proposal_id)


def _recheck(session: Session, project_id: UUID, row: Any) -> list[Party]:
    """Re-validate at accept time; returns the member parties or raises a 409."""
    parts = session.execute(
        select(MM).where(MM.c.proposal_id == row.proposal_id).order_by(MM.c.ordinal)
    ).all()
    target_row = next(x for x in parts if x.role == "target")
    members = [x for x in parts if x.role == "member"]
    inp = _inputs(session, project_id)
    if inp.fingerprint != row.dataset_fingerprint:
        # Inputs moved: the specific parties must still exist, otherwise the proposal is stale.
        if target_row.source_key not in inp.bores:
            raise _conflict("proposal_stale", "the target wellbore no longer exists")
        for x in members:
            if x.kind == "wellbore" and x.source_key not in inp.bores:
                raise _conflict("proposal_stale", f"{x.display_name} no longer exists")
            if x.kind == "label" and x.source_key not in inp.label_docs:
                raise _conflict(
                    "proposal_stale", f"{x.display_name} is no longer an unresolved name"
                )
    for x in members:
        for ev in x.evidence:
            sha = session.execute(
                select(m.source_document.c.sha256).where(
                    m.source_document.c.project_id == project_id,
                    m.source_document.c.document_id == UUID(ev["document_id"]),
                )
            ).scalar()
            if sha != ev["content_sha256"]:
                raise _conflict("proposal_stale", "a cited source changed or was replaced")
    parties = [
        Party.wellbore(x.wellbore_id, x.source_key)
        if x.kind == "wellbore"
        else Party.label(x.source_key, x.display_name)
        for x in members
    ]
    target = Party.wellbore(target_row.wellbore_id, target_row.source_key)
    checks = guards.evaluate(target, parties, inp.merges, in_project_keys=set(inp.bores)) + [
        GuardCheck(G7, True, "verified when the proposal was created")
    ]
    bad = guards.failed(checks)
    if bad:
        raise _conflict(
            "guard_blocked",
            "a deterministic guard blocks this merge",
            guards=[c.as_json() for c in bad],
        )
    return parties


def accept(
    session: Session, project_id: UUID, proposal_id: UUID, decided_by: str, note: str | None
) -> MergeProposal:
    row = _locked(session, project_id, proposal_id)
    if row.status == "blocked":
        bad = [c for c in row.guard_result if not c.get("passed")]
        raise _conflict("guard_blocked", "a deterministic guard blocks this proposal", guards=bad)
    if row.status != "pending":
        raise _conflict("invalid_transition", f"a {row.status} proposal cannot be accepted")
    members = _recheck(session, project_id, row)
    # Accepting deletes a merged-away wellbore (and its well when empty); remember the row ids
    # so a revert restores them exactly.
    ids = {
        r.wellbore_key: (r.wellbore_id, r.well_id)
        for r in session.execute(
            select(m.wellbore.c.wellbore_key, m.wellbore.c.wellbore_id, m.wellbore.c.well_id).where(
                m.wellbore.c.project_id == project_id,
                m.wellbore.c.wellbore_key.in_([p.key for p in members if p.kind == "wellbore"]),
            )
        )
    }
    try:
        with session.begin_nested():
            session.execute(
                insert(identity_merge),
                [
                    {
                        "project_id": project_id,
                        "proposal_id": proposal_id,
                        "source_kind": p.kind,
                        "source_key": p.key,
                        "target_key": row.target_key,
                        "decided_by": decided_by[:80],
                        "source_wellbore_id": ids.get(p.key, (None, None))[0],
                        "source_well_id": ids.get(p.key, (None, None))[1],
                    }
                    for p in members
                ],
            )
    except IntegrityError as exc:
        raise _conflict("merge_conflict", "a source is already merged by another proposal") from exc
    resolve_project(session, project_id)
    _decide(session, proposal_id, "accepted", decided_by, note)
    hooks.fire(
        session,
        hooks.MergeChange(
            project_id,
            proposal_id,
            "merge_applied",
            row.target_key,
            tuple(p.key for p in members),
            automatic=decided_by.startswith("auto:"),
        ),
    )
    return get_proposal(session, project_id, proposal_id)


def revert(
    session: Session, project_id: UUID, proposal_id: UUID, decided_by: str, note: str | None
) -> MergeProposal:
    row = _locked(session, project_id, proposal_id)
    if row.status != "accepted":
        raise _conflict("invalid_transition", f"a {row.status} proposal cannot be reverted")
    bore_hints: dict[str, UUID] = {}
    well_hints: dict[str, UUID] = {}
    reverted_keys = tuple(
        k
        for (k,) in session.execute(
            select(identity_merge.c.source_key).where(
                identity_merge.c.proposal_id == proposal_id,
                identity_merge.c.reverted_at.is_(None),
            )
        )
    )
    for r in session.execute(
        select(identity_merge).where(
            identity_merge.c.proposal_id == proposal_id,
            identity_merge.c.reverted_at.is_(None),
            identity_merge.c.source_kind == "wellbore",
        )
    ):
        parsed = parse_bore_label(r.source_key)
        if r.source_wellbore_id is not None:
            bore_hints[r.source_key] = r.source_wellbore_id
        if r.source_well_id is not None and parsed is not None and parsed.well_name:
            well_hints[parsed.well_name] = r.source_well_id
    session.execute(
        update(identity_merge)
        .where(identity_merge.c.proposal_id == proposal_id, identity_merge.c.reverted_at.is_(None))
        .values(reverted_at=_now(), reverted_by=decided_by[:80])
    )
    resolve_project(session, project_id, bore_id_hints=bore_hints, well_id_hints=well_hints)
    _decide(session, proposal_id, "reverted", decided_by, note)
    hooks.fire(
        session,
        hooks.MergeChange(project_id, proposal_id, "merge_reverted", row.target_key, reverted_keys),
    )
    return get_proposal(session, project_id, proposal_id)


__all__ = [
    "accept",
    "get_proposal",
    "require_project",
    "get_run",
    "list_proposals",
    "list_runs",
    "reject",
    "revert",
    "store_run",
    "taken_pairs",
]

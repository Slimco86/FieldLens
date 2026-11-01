"""Project-scoped identity read service (no writes; resolution is ``resolver.resolve_project``)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.well_identity import (
    IdentityKindCount,
    IdentityListing,
    ResolvedWell,
    ResolvedWellbore,
    UnresolvedIdentityGroup,
    WellboreEvidence,
    WellboreEvidenceDocument,
)
from fieldlens.persistence import models as m

from .resolver import RESOLVER_VERSION, Resolved, Unresolved, current_subject_groups
from .tables import record_wellbore_link

MAX_UNRESOLVED_LABELS = 10


def require_project(session: Session, project_id: UUID) -> None:
    if (
        session.execute(
            select(m.project.c.project_id).where(m.project.c.project_id == project_id)
        ).first()
        is None
    ):
        raise ContractError(ErrorCode.NOT_FOUND, "project not found", 404)


def _wellbores(session: Session, project_id: UUID) -> list[ResolvedWellbore]:
    wb, er, lk = m.wellbore, m.extracted_record, record_wellbore_link
    rows = session.execute(
        select(
            wb.c.wellbore_id,
            wb.c.well_id,
            wb.c.name,
            wb.c.suffix,
            wb.c.parent_wellbore_id,
        )
        .where(wb.c.project_id == project_id)
        .order_by(wb.c.name)
    ).all()
    counts = session.execute(
        select(lk.c.wellbore_id, er.c.kind, er.c.document_id, func.count().label("n"))
        .join(er, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
        .where(lk.c.project_id == project_id)
        .group_by(lk.c.wellbore_id, er.c.kind, er.c.document_id)
    ).all()
    kinds: dict[UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    docs: dict[UUID, set[UUID]] = defaultdict(set)
    for c in counts:
        kinds[c.wellbore_id][c.kind] += c.n
        docs[c.wellbore_id].add(c.document_id)
    out = []
    for r in rows:
        per_kind = kinds.get(r.wellbore_id, {})
        out.append(
            ResolvedWellbore(
                wellbore_id=r.wellbore_id,
                well_id=r.well_id,
                name=r.name,
                suffix=r.suffix,
                parent_wellbore_id=r.parent_wellbore_id,
                parent_basis="name_suffix" if r.parent_wellbore_id else None,
                record_count=sum(per_kind.values()),
                document_count=len(docs.get(r.wellbore_id, ())),
                record_counts=[
                    IdentityKindCount(kind=k, records=n) for k, n in sorted(per_kind.items())
                ],
            )
        )
    return out


def listing(session: Session, project_id: UUID) -> IdentityListing:
    require_project(session, project_id)
    wells = session.execute(
        select(m.well.c.well_id, m.well.c.name)
        .where(m.well.c.project_id == project_id)
        .order_by(m.well.c.name)
    ).all()
    bores = _wellbores(session, project_id)
    by_well: dict[UUID, list[ResolvedWellbore]] = defaultdict(list)
    for b in bores:
        by_well[b.well_id].append(b)
    # A well's document count needs a distinct union, so it is read again per well.
    lk, er = record_wellbore_link, m.extracted_record
    well_docs: dict[UUID, int] = {
        r.well_id: r.n
        for r in session.execute(
            select(m.wellbore.c.well_id, func.count(func.distinct(er.c.document_id)).label("n"))
            .join(lk, lk.c.wellbore_id == m.wellbore.c.wellbore_id)
            .join(er, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
            .where(m.wellbore.c.project_id == project_id)
            .group_by(m.wellbore.c.well_id)
        )
    }
    groups = current_subject_groups(session, project_id)
    unresolved_groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    expected: set[str] = set()
    resolved_records = 0
    for g in groups:
        if isinstance(g.outcome, Unresolved):
            unresolved_groups[(g.outcome.reason, g.outcome.detail)].append(g)
        elif isinstance(g.outcome, Resolved):
            expected.add(g.outcome.wellbore_name)
            resolved_records += g.records
    unresolved = []
    for (reason, detail), gs in sorted(unresolved_groups.items()):
        unresolved.append(
            UnresolvedIdentityGroup(
                reason=reason,
                detail=detail,
                labels=sorted({g.label for g in gs})[:MAX_UNRESOLVED_LABELS],
                record_count=sum(g.records for g in gs),
                document_count=len({d for g in gs for d in g.documents}),
            )
        )
    stored = session.execute(
        select(m.wellbore.c.wellbore_key).where(m.wellbore.c.project_id == project_id)
    ).scalars()
    linked = session.execute(
        select(func.count()).select_from(lk).where(lk.c.project_id == project_id)
    ).scalar_one()
    return IdentityListing(
        project_id=project_id,
        resolver_version=RESOLVER_VERSION,
        wells=[
            ResolvedWell(
                well_id=w.well_id,
                name=w.name,
                record_count=sum(b.record_count for b in by_well[w.well_id]),
                document_count=well_docs.get(w.well_id, 0),
                wellbores=by_well[w.well_id],
            )
            for w in wells
        ],
        linked_record_count=linked,
        unresolved_record_count=sum(u.record_count for u in unresolved),
        unresolved=unresolved,
        resolved_current=set(stored) == expected and linked == resolved_records,
    )


def wellbore_evidence(session: Session, project_id: UUID, wellbore_id: UUID) -> WellboreEvidence:
    require_project(session, project_id)
    bore = next((b for b in _wellbores(session, project_id) if b.wellbore_id == wellbore_id), None)
    if bore is None:
        raise ContractError(ErrorCode.NOT_FOUND, "wellbore not found", 404)
    er, ru, lk, sd = m.extracted_record, m.extraction_run, record_wellbore_link, m.source_document
    rows = session.execute(
        select(
            er.c.document_id,
            er.c.run_id,
            er.c.kind,
            func.count().label("n"),
            func.min(er.c.ordinal).label("first"),
        )
        .join(lk, (er.c.run_id == lk.c.run_id) & (er.c.ordinal == lk.c.ordinal))
        .where(lk.c.project_id == project_id, lk.c.wellbore_id == wellbore_id)
        .group_by(er.c.document_id, er.c.run_id, er.c.kind)
    ).all()
    per_doc: dict[tuple[UUID, UUID], dict[str, int]] = defaultdict(dict)
    first: dict[tuple[UUID, UUID], int] = {}
    for r in rows:
        per_doc[(r.document_id, r.run_id)][r.kind] = r.n
        key = (r.document_id, r.run_id)
        first[key] = min(first.get(key, r.first), r.first)
    docs = []
    from fieldlens.exposure import service as exposure_service  # local: avoids an import cycle

    for (document_id, run_id), kinds in sorted(per_doc.items(), key=lambda kv: str(kv[0][0])):
        meta = session.execute(
            select(sd.c.original_filename, ru.c.profile_name, ru.c.profile_version)
            .select_from(ru.join(sd, sd.c.document_id == ru.c.document_id))
            .where(ru.c.run_id == run_id)
        ).one()
        locator = session.execute(
            select(er.c.locator).where(
                er.c.run_id == run_id, er.c.ordinal == first[(document_id, run_id)]
            )
        ).scalar_one()
        docs.append(
            WellboreEvidenceDocument(
                document_id=document_id,
                run_id=run_id,
                filename=meta.original_filename,
                profile_name=meta.profile_name,
                profile_version=meta.profile_version,
                record_count=sum(kinds.values()),
                record_counts=[
                    IdentityKindCount(kind=k, records=n) for k, n in sorted(kinds.items())
                ],
                first_record_ordinal=first[(document_id, run_id)],
                first_record_locator=locator,
            )
        )
    return WellboreEvidence(
        project_id=project_id,
        wellbore=bore,
        documents=docs,
        exposure=exposure_service.wellbore_exposure(
            session, project_id, bore.well_id, bore.wellbore_id, bore.name
        ),
    )

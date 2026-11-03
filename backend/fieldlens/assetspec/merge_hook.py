"""Invalidate current asset specs when a wellbore merge is applied or reverted (AG-3).

Registered on the merge-change seam; it runs in the merge transaction, after the resolver, so a
rolled-back merge leaves the specs untouched. History is kept (state ``invalidated``)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldlens.identity.tables import identity_merge
from fieldlens.merge_proposals import hooks
from fieldlens.persistence import models as m

from . import service

HOOK_NAME = "assetspec.invalidate"


def affected_wellbores(session: Session, change: hooks.MergeChange) -> set[object]:
    ids: set[object] = set(
        session.execute(
            select(m.wellbore.c.wellbore_id).where(
                m.wellbore.c.project_id == change.project_id,
                m.wellbore.c.wellbore_key.in_([change.target_key, *change.source_keys]),
            )
        ).scalars()
    )
    ids.update(
        session.execute(
            select(identity_merge.c.source_wellbore_id).where(
                identity_merge.c.proposal_id == change.proposal_id,
                identity_merge.c.source_wellbore_id.is_not(None),
            )
        ).scalars()
    )
    return ids


def invalidate(session: Session, change: hooks.MergeChange) -> None:
    for wellbore_id in affected_wellbores(session, change):
        service.invalidate_current(session, change.project_id, wellbore_id)  # type: ignore[arg-type]


def install() -> None:
    hooks.register(HOOK_NAME, invalidate)

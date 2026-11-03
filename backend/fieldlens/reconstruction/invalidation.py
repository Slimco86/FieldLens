"""Mark reconstruction drafts stale when a wellbore merge is applied or reverted (TASK-076).

Merge keys are identity names, not wellbore ids, and a merge can retarget which wellbore a file
belongs to, so every finished draft of the project is invalidated (conservative, reversible by a
re-run). Runs in the merge transaction through :mod:`fieldlens.merge_proposals.hooks`.
"""

from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from fieldlens.merge_proposals import hooks
from fieldlens.reconstruction.tables import reconstruction_run as rr

HOOK_NAME = "reconstruction.invalidate"
TERMINAL = ("succeeded", "partial")


def invalidate(session: Session, change: hooks.MergeChange) -> None:
    reason = "merge_applied" if change.kind == "merge_applied" else "merge_reverted"
    session.execute(
        update(rr)
        .where(
            rr.c.project_id == change.project_id,
            rr.c.status.in_(TERMINAL),
            rr.c.summary.is_not(None),
            rr.c.invalidated_at.is_(None),
        )
        .values(invalidated_at=func.now(), invalidated_reason=reason)
    )


def install() -> None:
    hooks.register(HOOK_NAME, invalidate)

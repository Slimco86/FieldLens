"""Active identity merges (user-accepted, revertible) as read by the resolver.

A merge maps a source name to a target wellbore key. ``label`` sources are raw source labels the
resolver could not resolve; ``wellbore`` sources are resolved wellbore keys (for example another
spelling of the block). The rows are written only by an accepted merge proposal
(``fieldlens.merge_proposals.service``) and applied in ``resolver.current_subject_groups``."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from .labels import norm_identifier
from .tables import identity_merge

SOURCE_LABEL = "label"
SOURCE_WELLBORE = "wellbore"
MERGE_BASIS = "merge:accepted"


@dataclass(frozen=True)
class ActiveMerge:
    source_kind: str
    source_key: str
    target_key: str
    proposal_id: UUID


def label_key(label: str) -> str:
    """Normalized label used as the durable source key of a ``label`` merge."""
    return norm_identifier(label)


def active_merges(session: Session, project_id: UUID) -> list[ActiveMerge]:
    rows = session.execute(
        select(
            identity_merge.c.source_kind,
            identity_merge.c.source_key,
            identity_merge.c.target_key,
            identity_merge.c.proposal_id,
        )
        .where(identity_merge.c.project_id == project_id, identity_merge.c.reverted_at.is_(None))
        .order_by(identity_merge.c.created_at, identity_merge.c.merge_id)
    ).all()
    return [ActiveMerge(r.source_kind, r.source_key, r.target_key, r.proposal_id) for r in rows]

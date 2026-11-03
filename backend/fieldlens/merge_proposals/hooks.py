"""Identity-change hook: one in-process seam for everything that depends on a merge (TASK-076).

An applied or reverted merge changes which records belong to which wellbore, so drafts built
from the old grouping are out of date. ``accept`` and ``revert`` call :func:`fire` inside their
transaction *after* the resolver ran; a listener (``session``, change) must only write through the
given session (it commits or rolls back with the merge) and must not raise for its own reasons.
The reconstruction package registers an invalidator for run summaries; the asset-spec lane
(TASK-077/079) registers its own to invalidate a draft ``VisualAssetSpec``.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

ChangeKind = Literal["merge_applied", "merge_reverted"]


@dataclass(frozen=True)
class MergeChange:
    project_id: UUID
    proposal_id: UUID
    kind: ChangeKind
    target_key: str
    source_keys: tuple[str, ...]
    automatic: bool = False
    """Applied without a user decision (reconstruction S3, owner decision Q1)."""


Listener = Callable[[Session, MergeChange], None]
_listeners: dict[str, Listener] = {}


def register(name: str, listener: Listener) -> None:
    """Idempotent by ``name``: registering again replaces the listener."""
    _listeners[name] = listener


def unregister(name: str) -> None:
    _listeners.pop(name, None)


def fire(session: Session, change: MergeChange) -> None:
    for name, listener in list(_listeners.items()):
        listener(session, change)
        log.info("merge change %s delivered to %s", change.kind, name)

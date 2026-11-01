"""Settle reservations of finished units (D8).

A unit is finalized before its reservation is settled, so a crash or a settle failure between
the two leaves a finished unit whose reservation is still ``reserved``. Settlement is
idempotent: this sweep finds such units and settles them (a reservation with no dispatched attempt
is released by the ledger). It never re-dispatches a call and never touches a running unit."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.tables import spend_reservation
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

logger = logging.getLogger(__name__)
FINISHED = ("succeeded", "failed", "cancelled")


def settle_finished_units(
    factory: sessionmaker[Session], ledger: BudgetLedger, project_id: UUID | None = None
) -> list[UUID]:
    """Settle every open reservation that belongs to a finished unit. Returns reservation ids."""
    u, r = m.agent_work_unit, spend_reservation
    stmt = (
        select(r.c.reservation_id)
        .join(u, u.c.reservation_id == r.c.reservation_id)
        .where(u.c.state.in_(FINISHED), r.c.state == "reserved")
        .order_by(r.c.reservation_id)
    )
    if project_id is not None:
        stmt = stmt.where(u.c.project_id == project_id)
    with session_scope(factory) as s:
        open_ids = list(s.execute(stmt).scalars())
    settled: list[UUID] = []
    for rid in open_ids:
        try:
            ledger.settle(rid)
            settled.append(rid)
        except Exception:  # noqa: BLE001 - one bad reservation must not stop the sweep
            logger.warning("could not settle reservation %s", rid)
    return settled

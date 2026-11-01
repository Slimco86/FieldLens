"""``known_md_max``: the read-only DC-3 range helper that TASK-041 equipment depths use."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import text

from fieldlens.identity.resolver import known_md_max
from fieldlens.persistence.session import session_scope
from tests.identity.test_identity_resolution import _perf, _resolve, _station
from tests.retrieval.support import World


def test_known_md_max_is_per_wellbore_and_absent_without_a_range(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "perf.dat",
        [
            _perf("NO 15/9-F-12", "15/9-F-12", None, 3100, 3140),
            _perf("NO 15/9-F-14", "15/9-F-14", None, 9000, 9010),
        ],
    )
    world.add_doc(
        pid,
        "survey.pdf",
        [_station("F-12", "15/9-F-12", 2500.0), _station("F-12", "15/9-F-12", 3000.0)],
    )
    _resolve(world, pid)
    with session_scope(world.factory) as session:
        rows = dict(
            session.execute(
                text("select wellbore_key, wellbore_id from wellbore where project_id = :p"),
                {"p": UUID(pid)},
            ).all()
        )
        assert known_md_max(session, UUID(pid), rows["15/9-F-12"]) == pytest.approx(3000.0)
        # a perforation depth is not a range; no range of its own means no check
        assert known_md_max(session, UUID(pid), rows["15/9-F-14"]) is None

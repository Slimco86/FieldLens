"""Migration 0014 on real PostgreSQL: failed/quarantined conversion round trip (TASK-070)."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from tests.activity.test_activity_migration import downgrade
from tests.conftest import migrate
from tests.jobs.test_extraction_flow import _ingest
from tests.upload_support import TEXT, make_api


def test_failed_rows_round_trip_through_0013_and_back(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path / "root")
    pid, docs = _ingest(api, [("n.txt", TEXT)])
    did = str(docs[0]["document_id"])
    with engine.begin() as c:
        c.execute(
            text(
                "update document_processing set storage_state='failed',"
                " storage_failure_reason='missing', detail='verification_missing'"
                " where document_id=:d"
            ),
            {"d": did},
        )
    downgrade(migrated_url, "0013_reconstruction_runs")
    with engine.connect() as c:
        state = c.execute(
            text("select storage_state from document_processing where document_id=:d"),
            {"d": did},
        ).scalar_one()
        assert state == "quarantined"
    migrate(migrated_url)
    with engine.connect() as c:
        row = c.execute(
            text(
                "select storage_state, storage_failure_reason from document_processing"
                " where document_id=:d"
            ),
            {"d": did},
        ).one()
    assert tuple(row) == ("failed", "missing")

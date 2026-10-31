"""Migration 0006 on real PostgreSQL: upgrade from 0005 with data, downgrade, re-upgrade (AX-10)."""

from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from fieldlens.persistence.readiness import alembic_config
from tests.conftest import migrate


def downgrade(url: URL, revision: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, revision)
    finally:
        engine.dispose()


TABLES = (
    "SELECT table_name FROM information_schema.tables WHERE table_name LIKE 'agent_%' ORDER BY 1"
)


def test_upgrade_from_0005_preserves_rows_and_round_trips_ax10(empty_database: URL) -> None:
    migrate(empty_database, "0005_native_profiles")
    engine = create_engine(empty_database)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO project (name) VALUES ('Old')"))
            assert conn.execute(text(TABLES)).all() == []
        migrate(empty_database)
        with engine.connect() as conn:
            assert conn.execute(text("SELECT name FROM project")).scalar_one() == "Old"
            assert [r[0] for r in conn.execute(text(TABLES))] == ["agent_step", "agent_work_unit"]
        downgrade(empty_database, "0005_native_profiles")
        with engine.connect() as conn:
            assert conn.execute(text(TABLES)).all() == []
            assert conn.execute(text("SELECT name FROM project")).scalar_one() == "Old"
        migrate(empty_database)
        with engine.connect() as conn:
            assert len(conn.execute(text(TABLES)).all()) == 2
    finally:
        engine.dispose()

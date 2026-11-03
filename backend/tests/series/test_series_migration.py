"""Migration 0009 on real PostgreSQL: populated 0008 upgrade, downgrade, re-upgrade, scoping."""

from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from fieldlens.persistence.readiness import alembic_config, expected_head
from tests.conftest import migrate

TABLES = (
    "SELECT table_name FROM information_schema.tables WHERE table_name IN "
    "('series_axis','series_curve') ORDER BY 1"
)


def _downgrade(url: URL, revision: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, revision)
    finally:
        engine.dispose()


def test_single_head_is_0009_on_top_of_0008() -> None:
    assert expected_head() == "0019_asset_spec"


def test_upgrade_from_0008_with_data_round_trips_and_enforces_scope(empty_database: URL) -> None:
    migrate(empty_database, "0008_identity_links")
    engine = create_engine(empty_database)
    try:
        with engine.begin() as conn:
            pid = conn.execute(
                text("INSERT INTO project (name) VALUES ('Old') RETURNING project_id")
            ).scalar_one()
            other = conn.execute(
                text("INSERT INTO project (name) VALUES ('Other') RETURNING project_id")
            ).scalar_one()
            assert conn.execute(text(TABLES)).all() == []
        migrate(empty_database)
        with engine.begin() as conn:
            assert [r[0] for r in conn.execute(text(TABLES))] == ["series_axis", "series_curve"]
            assert conn.execute(text("SELECT count(*) FROM project")).scalar_one() == 2
            storage = {
                (r[0], r[1])
                for r in conn.execute(
                    text(
                        "SELECT c.relname, a.attname FROM pg_attribute a JOIN pg_class c ON "
                        "c.oid = a.attrelid WHERE c.relname IN ('series_axis','series_curve') "
                        "AND a.attname IN ('index_data','positions_data','values_data') "
                        "AND a.attstorage = 'e'"
                    )
                )
            }
            assert storage == {
                ("series_axis", "index_data"),
                ("series_axis", "positions_data"),
                ("series_curve", "values_data"),
            }, "arrays are STORAGE EXTERNAL so a window is a cheap substring"
        # a series row cannot reference a run that is not in its own project
        for p in (pid, other):
            with engine.connect() as conn:
                tx = conn.begin()
                try:
                    conn.execute(
                        text(
                            "INSERT INTO series_axis (project_id, run_id, document_id, ordinal, "
                            "kind, index_type, index_encoding, index_name, index_unit_status, "
                            "index_order, sample_count, index_first, index_last, index_min, "
                            "index_max, position_kind, subject, evidence, index_data, "
                            "positions_data) VALUES (:p, gen_random_uuid(), gen_random_uuid(), 0,"
                            " 'log', 'depth', 'numeric', 'D', 'missing', 'increasing', 1, 0, 0, "
                            "0, 0, 'line', '{}', '{}', decode('0000000000000000','hex'), "
                            "decode('00000000','hex'))"
                        ),
                        {"p": p},
                    )
                    raise AssertionError("an axis must reference an existing run and document")
                except IntegrityError:
                    tx.rollback()
        _downgrade(empty_database, "0008_identity_links")
        with engine.connect() as conn:
            assert conn.execute(text(TABLES)).all() == []
            assert conn.execute(text("SELECT count(*) FROM project")).scalar_one() == 2
        migrate(empty_database)
        with engine.connect() as conn:
            assert len(conn.execute(text(TABLES)).all()) == 2
    finally:
        engine.dispose()

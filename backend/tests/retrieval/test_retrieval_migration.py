"""Migration 0007 on real PostgreSQL: populated 0006 upgrade, downgrade, re-upgrade, one head."""

from __future__ import annotations

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from fieldlens.persistence.readiness import alembic_config, expected_head
from tests.conftest import migrate

TABLES = (
    "SELECT table_name FROM information_schema.tables WHERE table_name IN "
    "('retrieval_index','evidence_chunk','chunk_identifier','chunk_embedding') ORDER BY 1"
)


def downgrade(url: URL, revision: str) -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.downgrade(cfg, revision)
    finally:
        engine.dispose()


def test_single_head_is_current() -> None:
    assert expected_head() == "0013_reconstruction_runs"


def test_upgrade_from_0006_with_data_round_trips_and_enforces_scope(empty_database: URL) -> None:
    migrate(empty_database, "0006_agent_activity_log")
    engine = create_engine(empty_database)
    try:
        with engine.begin() as conn:
            pid = conn.execute(
                text("INSERT INTO project (name) VALUES ('Old') RETURNING project_id")
            ).scalar_one()
            other = conn.execute(
                text("INSERT INTO project (name) VALUES ('Other') RETURNING project_id")
            ).scalar_one()
            doc = conn.execute(
                text(
                    "INSERT INTO source_document (project_id, sha256, size_bytes, original_filename,"
                    " storage_key) VALUES (:p, repeat('a', 64), 1, 'x', 'k') RETURNING document_id"
                ),
                {"p": pid},
            ).scalar_one()
            assert conn.execute(text(TABLES)).all() == []
        migrate(empty_database)
        with engine.begin() as conn:
            assert [r[0] for r in conn.execute(text(TABLES))] == [
                "chunk_embedding",
                "chunk_identifier",
                "evidence_chunk",
                "retrieval_index",
            ]
            assert (
                conn.execute(
                    text("SELECT name FROM project WHERE project_id = :p"), {"p": pid}
                ).scalar_one()
                == "Old"
            )
            assert conn.execute(text("SELECT count(*) FROM source_document")).scalar_one() == 1
            assert (
                conn.execute(
                    text("SELECT extname FROM pg_extension WHERE extname='vector'")
                ).scalar_one()
                == "vector"
            )
        # scope: a chunk cannot reference another project's document
        with engine.connect() as conn:
            bad = conn.begin()
            try:
                conn.execute(
                    text(
                        "INSERT INTO retrieval_index (project_id, run_id, document_id, "
                        "source_revision_id, kind, chunker_version) VALUES (:p, gen_random_uuid(),"
                        " :d, gen_random_uuid(), 'chunks', 'v')"
                    ),
                    {"p": other, "d": doc},
                )
                raise AssertionError("an index row must not reference a non-existent run")
            except IntegrityError:
                bad.rollback()
        downgrade(empty_database, "0006_agent_activity_log")
        with engine.connect() as conn:
            assert conn.execute(text(TABLES)).all() == []
            assert (
                conn.execute(
                    text("SELECT name FROM project WHERE project_id = :p"), {"p": pid}
                ).scalar_one()
                == "Old"
            )
        migrate(empty_database)
        with engine.connect() as conn:
            assert len(conn.execute(text(TABLES)).all()) == 4
    finally:
        engine.dispose()

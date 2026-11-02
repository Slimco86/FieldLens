"""Migration 0016 (TASK-055): upgrade/downgrade round trip on real PostgreSQL, with data."""

from __future__ import annotations

import uuid

import pytest
from alembic import command
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from fieldlens.persistence.readiness import alembic_config
from tests.conftest import migrate

PREVIOUS = "0015_project_deletion"
NEW_TABLES = {"document_model_result", "document_identity_proposal"}


def _alembic(engine: Engine, fn: str, rev: str) -> None:
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        getattr(command, fn)(cfg, rev)


def _tables(engine: Engine) -> set[str]:
    with engine.connect() as c:
        return {
            r[0]
            for r in c.execute(
                text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            )
        }


def _run(conn: Connection, project: uuid.UUID, provider: str) -> uuid.UUID:
    row = conn.execute(
        text(
            "INSERT INTO processing_run (project_id, status, step, provider, route, "
            "request_fingerprint, estimated_pages, estimated_input_tokens, estimated_output_tokens, "
            "estimated_usd, pricing_source, total_cap_usd, remaining_budget_usd) "
            "VALUES (:p, 'estimated', 's', :prov, 'model', 'f', 1, 1, 1, 0, 'x', 5, 5) "
            "RETURNING run_id"
        ),
        {"p": project, "prov": provider},
    ).one()
    return uuid.UUID(str(row[0]))


def test_upgrade_adds_tables_and_downgrade_removes_them_keeping_stub_runs(
    empty_database: URL,
) -> None:
    migrate(empty_database, PREVIOUS)
    engine = create_engine(empty_database)
    try:
        assert not NEW_TABLES & _tables(engine)
        with engine.begin() as conn:
            project = uuid.UUID(
                str(
                    conn.execute(
                        text("INSERT INTO project (name) VALUES ('P') RETURNING project_id")
                    ).scalar_one()
                )
            )
            stub_run = _run(conn, project, "stub")
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _run(conn, project, "meta")  # not admitted before 0016

        migrate(empty_database)
        assert NEW_TABLES <= _tables(engine)
        with engine.begin() as conn:
            meta_run = _run(conn, project, "meta")
            assert meta_run != stub_run

        _alembic(engine, "downgrade", PREVIOUS)
        assert not NEW_TABLES & _tables(engine)
        with engine.connect() as c:
            runs = [r[0] for r in c.execute(text("SELECT provider FROM processing_run"))]
            columns = {
                r[0]
                for r in c.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='processing_run_document'"
                    )
                )
            }
        assert runs == ["stub"]  # the meta run cannot exist under the old provider check
        assert "cache_hit" not in columns

        migrate(empty_database)  # and up again
        assert NEW_TABLES <= _tables(engine)
    finally:
        engine.dispose()

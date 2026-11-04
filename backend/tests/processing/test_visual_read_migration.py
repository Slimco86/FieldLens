"""Migration 0021 (TASK-115, VR-10): read_mode columns up/down on real PostgreSQL, with data."""

from __future__ import annotations

from alembic import command
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from fieldlens.persistence.readiness import alembic_config
from tests.conftest import migrate

PREVIOUS = "0020_chat"


def _alembic(engine: Engine, fn: str, rev: str) -> None:
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        getattr(command, fn)(cfg, rev)


def _columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as c:
        return {
            r[0]
            for r in c.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_name = :t"),
                {"t": table},
            )
        }


def test_upgrade_adds_read_mode_and_downgrade_drops_image_proposals(empty_database: URL) -> None:
    migrate(empty_database, PREVIOUS)
    engine = create_engine(empty_database)
    try:
        assert "read_mode" not in _columns(engine, "document_identity_proposal")
        migrate(empty_database)
        assert "read_mode" in _columns(engine, "document_identity_proposal")
        assert "read_mode" in _columns(engine, "document_model_result")
        with engine.connect() as c:
            default = c.execute(
                text(
                    "SELECT column_default FROM information_schema.columns WHERE "
                    "table_name='document_identity_proposal' AND column_name='read_mode'"
                )
            ).scalar_one()
        assert "text" in str(default)
        with engine.connect() as c:
            checks = " ".join(
                r[0]
                for r in c.execute(
                    text(
                        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid = "
                        "'document_identity_proposal'::regclass AND contype = 'c'"
                    )
                )
            )
        assert "read_mode" in checks and "image" in checks
        _alembic(engine, "downgrade", PREVIOUS)
        assert "read_mode" not in _columns(engine, "document_identity_proposal")
        assert "read_mode" not in _columns(engine, "document_model_result")
        migrate(empty_database)  # and back up again
        assert "read_mode" in _columns(engine, "document_identity_proposal")
    finally:
        engine.dispose()

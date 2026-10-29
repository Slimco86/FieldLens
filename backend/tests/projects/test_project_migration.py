"""Migration 0002 on real PostgreSQL: bound, index, round trip from 0001 with data."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from tests.conftest import migrate


def test_upgrade_from_0001_preserves_rows_and_enforces_bound(empty_database: URL) -> None:
    migrate(empty_database, "0001_foundation_core")
    engine = create_engine(empty_database)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO project (name, description) VALUES ('Old', 'kept')"))
        migrate(empty_database)
        with engine.begin() as conn:
            assert conn.execute(text("SELECT name, description FROM project")).one() == (
                "Old",
                "kept",
            )
            conn.execute(
                text("INSERT INTO project (name, description) VALUES ('Max', repeat('d', 4000))")
            )
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(
                text("INSERT INTO project (name, description) VALUES ('Over', repeat('d', 4001))")
            )
        with engine.connect() as conn:
            idx = conn.execute(
                text(
                    "SELECT indexdef FROM pg_indexes WHERE indexname='ix_project_created_at_project_id'"
                )
            ).scalar_one()
        assert "created_at DESC" in idx and "project_id DESC" in idx
    finally:
        engine.dispose()

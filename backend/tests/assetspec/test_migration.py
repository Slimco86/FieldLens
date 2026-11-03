"""Migration 0019: upgrade/downgrade round trip; project delete purges the table."""

from __future__ import annotations

from alembic import command
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL

from fieldlens.persistence.readiness import alembic_config
from tests.conftest import migrate

PREVIOUS = "0018_reconstruction_stages"


def _alembic(engine: Engine, fn: str, rev: str) -> None:
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        getattr(command, fn)(cfg, rev)


def _has_table(engine: Engine) -> bool:
    with engine.connect() as c:
        return bool(
            c.execute(
                text(
                    "select count(*) from information_schema.tables where table_name='wellbore_asset_spec'"
                )
            ).scalar_one()
        )


def test_round_trip(empty_database: URL) -> None:
    migrate(empty_database, PREVIOUS)
    engine = create_engine(empty_database)
    try:
        assert not _has_table(engine)
        _alembic(engine, "upgrade", "0019_asset_spec")
        assert _has_table(engine)
        _alembic(engine, "downgrade", PREVIOUS)
        assert not _has_table(engine)
        _alembic(engine, "upgrade", "0019_asset_spec")
        assert _has_table(engine)
    finally:
        engine.dispose()

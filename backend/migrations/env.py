"""Alembic environment: online only, PostgreSQL only, never the demo database."""

from __future__ import annotations

import logging.config

from alembic import context
from sqlalchemy import Connection, create_engine, pool
from sqlalchemy.engine import make_url

from fieldlens.config import Settings
from fieldlens.persistence.models import metadata

config = context.config
if config.config_file_name is not None:
    logging.config.fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = metadata


def _refuse_unsafe(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        raise RuntimeError("FieldLens migrations run on PostgreSQL only")
    name = connection.engine.url.database or ""
    if "demo" in name.lower():
        raise RuntimeError(f"refusing to migrate protected database {name!r}")


def _run(connection: Connection) -> None:
    _refuse_unsafe(connection)
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    supplied = config.attributes.get("connection")
    if supplied is not None:
        _run(supplied)
        return
    # Same Settings path as the API: environment first, then the repository-root .env.
    url = Settings().database_url
    if url is None:
        raise RuntimeError(
            "FIELDLENS_DATABASE_URL is not configured; run `uv run python scripts/init_env.py`"
        )
    parsed = make_url(url.get_secret_value())
    engine = create_engine(parsed, poolclass=pool.NullPool)
    with engine.connect() as connection:
        _run(connection)
        connection.commit()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline migration SQL generation is not supported")
run_migrations_online()

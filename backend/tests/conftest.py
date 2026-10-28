"""Default test configuration: loopback-only network, explicit unique test database."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from fieldlens.config import Settings
from fieldlens.persistence.readiness import alembic_config
from tests import support


@pytest.fixture(scope="session", autouse=True)
def _deny_external_network() -> Iterator[None]:
    undo = support.install_network_guard()
    try:
        yield
    finally:
        for owner, name, original in undo:
            setattr(owner, name, original)


@pytest.fixture(scope="session")
def test_database_base() -> URL:
    """Validated URL from FIELDLENS_TEST_DATABASE_URL; fails explicitly if absent or unsafe."""
    try:
        return support.validate_test_database_url(os.environ.get(support.ENV_VAR))
    except support.UnsafeTestDatabase as exc:
        pytest.fail(str(exc), pytrace=False)


@pytest.fixture
def empty_database(test_database_base: URL) -> Iterator[URL]:
    """A fresh, uniquely named, unmigrated database; dropped afterwards."""
    with support.temporary_database(test_database_base) as url:
        yield url


def migrate(url: URL, revision: str = "head") -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, revision)
    finally:
        engine.dispose()


@pytest.fixture
def migrated_url(empty_database: URL) -> URL:
    migrate(empty_database)
    return empty_database


@pytest.fixture
def engine(migrated_url: URL) -> Iterator[Engine]:
    eng = create_engine(migrated_url)
    try:
        yield eng
    finally:
        eng.dispose()


def settings_for(url: URL | None = None, **overrides: object) -> Settings:
    values: dict[str, object] = dict(overrides)
    if url is not None:
        values["database_url"] = url.render_as_string(hide_password=False)
    return Settings(**values)  # type: ignore[arg-type]

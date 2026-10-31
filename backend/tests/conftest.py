"""Default test configuration: loopback-only network, explicit unique test database."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine

from fieldlens.config import Settings
from tests import live_meta_support, support

# Default tests never see a real provider key: an explicitly blank process variable wins over
# both the real environment and the root .env, so Settings() resolves the key as absent.
if os.environ.get(live_meta_support.OPT_IN_VAR) == "1":
    live_meta_support.STASHED_KEY["key"] = os.environ.get("MODEL_API_KEY", "")
os.environ["MODEL_API_KEY"] = ""
# Default tests never load the real local embedding model, even when it is installed under
# .local: embeddings are disabled unless a test sets the provider explicitly (fake offline).
os.environ["FIELDLENS_EMBEDDING_PROVIDER"] = "none"


@pytest.fixture(scope="session", autouse=True)
def _deny_external_network() -> Iterator[None]:
    undo = support.install_network_guard()
    live_meta_support.GUARD_UNDO.extend(undo)
    try:
        yield
    finally:
        for owner, name, original in undo:
            setattr(owner, name, original)


@pytest.fixture(scope="session")
def test_database_base() -> URL:
    """Explicit override or a unique sibling derived from .env; fails explicitly if unsafe/absent."""
    try:
        return support.resolve_test_database_url()
    except support.UnsafeTestDatabase as exc:
        pytest.fail(str(exc), pytrace=False)


@pytest.fixture
def empty_database(test_database_base: URL) -> Iterator[URL]:
    """A fresh, uniquely named, unmigrated database; dropped afterwards."""
    with support.temporary_database(test_database_base) as url:
        yield url


def migrate(url: URL, revision: str = "head") -> None:
    support.migrate(url, revision)


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
    """Explicit configuration: never reads the developer's .env (``_env_file=None``)."""
    values: dict[str, object] = dict(overrides)
    if url is not None:
        values["database_url"] = url.render_as_string(hide_password=False)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]

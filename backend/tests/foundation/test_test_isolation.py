"""FN-6: default tests deny external network and use a uniquely named test database."""

from __future__ import annotations

import socket

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from tests import support

OK = "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_app_test_0a1b2c3d"


def test_external_connect_is_blocked() -> None:
    s = socket.socket()
    try:
        with pytest.raises(support.ExternalNetworkBlocked):
            s.connect(("93.184.216.34", 443))
    finally:
        s.close()


def test_external_name_resolution_is_blocked() -> None:
    with pytest.raises(support.ExternalNetworkBlocked):
        socket.getaddrinfo("api.example.invalid", 443)


def test_loopback_is_still_allowed() -> None:
    s = socket.socket()
    try:
        # Port 1 is closed: a real refusal proves the guard let loopback through.
        assert s.connect_ex(("127.0.0.1", 1)) != 0
    finally:
        s.close()


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "sqlite:///x.db",
        "postgresql://u:p@127.0.0.1:55432/fieldlens_app_test_0a1b2c3d",
        "postgresql+psycopg://u:p@db.example.com:5432/fieldlens_app_test_0a1b2c3d",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_demo",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_app",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_demo_test_0a1b2c3d",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_app_test_0A1B2C3D",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_app_test_0a1b2c3",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_fl004a_w1_test_0a1b2c3d",
    ],
)
def test_absent_or_unsafe_test_url_is_rejected(raw: str | None) -> None:
    with pytest.raises(support.UnsafeTestDatabase):
        support.validate_test_database_url(raw)


def test_safe_url_accepted_and_sibling_names_are_unique() -> None:
    url = support.validate_test_database_url(OK)
    a, b = support.sibling_url(url), support.sibling_url(url)
    assert a.database != b.database
    assert support.TEST_DB_NAME.fullmatch(a.database or "")


@pytest.mark.parametrize(
    "query",
    [
        "host=evil.example.com",
        "hostaddr=8.8.8.8",
        "service=external",
        "host=localhost&host=evil.example.com",
        "dbname=fieldlens_demo",
        "port=5432",
        "options=-csearch_path%3Dpublic",
    ],
)
def test_connection_query_options_cannot_override_test_isolation(query: str) -> None:
    with pytest.raises(support.UnsafeTestDatabase):
        support.validate_test_database_url(f"{OK}?{query}")


@pytest.mark.parametrize("variable", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
def test_ambient_libpq_redirects_are_rejected(
    variable: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(variable, "external")
    with pytest.raises(support.UnsafeTestDatabase):
        support.validate_test_database_url(OK)


def test_active_database_is_postgres_with_unique_name(
    migrated_url: URL, test_database_base: URL
) -> None:
    assert migrated_url.drivername == "postgresql+psycopg"
    assert migrated_url.database != test_database_base.database
    assert "demo" not in (migrated_url.database or "")
    eng = create_engine(migrated_url)
    with eng.connect() as conn:
        assert conn.execute(text("select current_database()")).scalar_one() == migrated_url.database
        assert "PostgreSQL" in conn.execute(text("select version()")).scalar_one()
    eng.dispose()


# --- derived test database (FL-018) ---------------------------------------------------------

APP_URL = "postgresql+psycopg://svc:s3cret-_x@127.0.0.1:55432/fieldlens_app"


def _no_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        support.ENV_VAR,
        support.APP_URL_VAR,
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "FIELDLENS_DB_PORT",
    ):
        monkeypatch.delenv(key, raising=False)


def test_test_url_is_derived_as_unique_sibling_of_the_app_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_env(monkeypatch)
    a = support.resolve_test_database_url({support.APP_URL_VAR: APP_URL})
    b = support.resolve_test_database_url({support.APP_URL_VAR: APP_URL})
    assert a.database != b.database
    assert support.TEST_DB_NAME.fullmatch(a.database or "")
    assert (a.username, a.host, a.port) == ("svc", "127.0.0.1", 55432)
    assert a.database != "fieldlens_app"


def test_test_url_is_derived_from_components_when_no_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_env(monkeypatch)
    url = support.resolve_test_database_url(
        {
            "POSTGRES_USER": "u",
            "POSTGRES_PASSWORD": "p",
            "POSTGRES_DB": "x",
            "FIELDLENS_DB_PORT": "1",
        }
    )
    assert (url.username, url.host, url.port) == ("u", "127.0.0.1", 1)
    assert support.TEST_DB_NAME.fullmatch(url.database or "")


def test_missing_database_configuration_names_the_bootstrap_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _no_env(monkeypatch)
    with pytest.raises(support.UnsafeTestDatabase, match=r"scripts/init_env\.py"):
        support.resolve_test_database_url({})
    with pytest.raises(support.UnsafeTestDatabase, match=r"scripts/init_env\.py"):
        support.resolve_test_database_url({"POSTGRES_USER": "u"})  # incomplete


def test_explicit_override_wins_and_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_env(monkeypatch)
    values = {support.APP_URL_VAR: APP_URL, support.ENV_VAR: OK}
    assert support.resolve_test_database_url(values).database == "fieldlens_app_test_0a1b2c3d"
    bad = {support.APP_URL_VAR: APP_URL, support.ENV_VAR: APP_URL}
    with pytest.raises(support.UnsafeTestDatabase):
        support.resolve_test_database_url(bad)


@pytest.mark.parametrize(
    "app_url",
    [
        "postgresql+psycopg://u:p@db.example.com:5432/fieldlens_app",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_app?host=evil.example.com",
        "postgresql://u:p@127.0.0.1:55432/fieldlens_app",
    ],
)
def test_unsafe_app_url_never_yields_a_test_database(
    app_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_env(monkeypatch)
    with pytest.raises(support.UnsafeTestDatabase):
        support.resolve_test_database_url({support.APP_URL_VAR: app_url})


def test_real_environment_beats_dotenv_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _no_env(monkeypatch)
    monkeypatch.setenv(support.APP_URL_VAR, "postgresql+psycopg://env:p@127.0.0.1:2/fieldlens_app")
    url = support.resolve_test_database_url({support.APP_URL_VAR: APP_URL})
    assert (url.username, url.port) == ("env", 2)

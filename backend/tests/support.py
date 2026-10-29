"""Test isolation helpers: unsafe-URL rejection, unique databases and a loopback-only network."""

from __future__ import annotations

import os
import re
import secrets
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from ipaddress import ip_address

from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from fieldlens.localenv import load_local_env
from fieldlens.persistence.readiness import alembic_config

# fieldlens_app_test_<8 lowercase hex>
TEST_DB_NAME = re.compile(r"^fieldlens_app_test_[0-9a-f]{8}$")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
ENV_VAR = "FIELDLENS_TEST_DATABASE_URL"
APP_URL_VAR = "FIELDLENS_DATABASE_URL"


class UnsafeTestDatabase(Exception):
    pass


def _config_value(key: str, file_values: dict[str, str]) -> str | None:
    """Real environment first, then the repository-root .env (FIELDLENS_/POSTGRES_ keys only)."""
    return os.environ.get(key) or file_values.get(key) or None


def resolve_test_database_url(file_values: dict[str, str] | None = None) -> URL:
    """Explicit FIELDLENS_TEST_DATABASE_URL, else a unique sibling derived from the app DB.

    The derived URL has the application URL's server and credentials but a fresh
    ``fieldlens_app_test_<8 hex>`` database name; it never equals the application database.
    """
    values = load_local_env() if file_values is None else file_values
    explicit = _config_value(ENV_VAR, values)
    if explicit:
        return validate_test_database_url(explicit)
    app_raw = _config_value(APP_URL_VAR, values)
    if not app_raw:
        user, password, db, port = (
            _config_value(k, values)
            for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "FIELDLENS_DB_PORT")
        )
        if not (user and password and db):
            raise UnsafeTestDatabase(
                "database configuration is missing; run `uv run python scripts/init_env.py` "
                f"(or set {ENV_VAR} to a dedicated test database)."
            )
        app_raw = URL.create(
            "postgresql+psycopg", user, password, "127.0.0.1", int(port or 55432), db
        ).render_as_string(hide_password=False)
    try:
        app_url = make_url(app_raw)
    except (ArgumentError, ValueError) as exc:
        raise UnsafeTestDatabase(f"{APP_URL_VAR} is not a valid URL") from exc
    derived = app_url.set(database=f"fieldlens_app_test_{secrets.token_hex(4)}")
    if derived.database == app_url.database:
        raise UnsafeTestDatabase("the test database must never be the application database")
    return validate_test_database_url(derived.render_as_string(hide_password=False))


def validate_test_database_url(raw: str | None) -> URL:
    """Fail explicitly for an absent or unsafe test database URL."""
    if not raw:
        raise UnsafeTestDatabase(
            f"{ENV_VAR} is not set and no database configuration was found; run "
            "`uv run python scripts/init_env.py`."
        )
    try:
        url = make_url(raw)
    except (ArgumentError, ValueError) as exc:
        raise UnsafeTestDatabase("the test database URL is not a valid URL") from exc
    if url.drivername != "postgresql+psycopg":
        raise UnsafeTestDatabase(
            "the test database URL must use postgresql+psycopg:// (never SQLite)"
        )
    if url.host not in LOOPBACK_HOSTS:
        raise UnsafeTestDatabase("the test database URL must target a loopback host")
    if url.query:
        raise UnsafeTestDatabase(
            "the test database URL must not contain connection query overrides"
        )
    if any(os.environ.get(key) for key in ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")):
        raise UnsafeTestDatabase("unset libpq host-address/service environment overrides for tests")
    name = url.database or ""
    if "demo" in name.lower() or not TEST_DB_NAME.fullmatch(name):
        raise UnsafeTestDatabase(
            f"test database {name!r} is not a uniquely named fieldlens_app_test_<8 hex> database"
        )
    return url


def sibling_url(base: URL) -> URL:
    """A fresh uniquely named database on the same server (same name pattern)."""
    assert base.database is not None
    return base.set(database=base.database[:-8] + secrets.token_hex(4))


def _admin_engine(url: URL):  # type: ignore[no-untyped-def]
    return create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")


def create_database(url: URL) -> None:
    assert url.database is not None and TEST_DB_NAME.fullmatch(url.database)
    eng = _admin_engine(url)
    with eng.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    eng.dispose()


def drop_database(url: URL) -> None:
    assert url.database is not None and TEST_DB_NAME.fullmatch(url.database)
    eng = _admin_engine(url)
    with eng.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
    eng.dispose()


def migrate(url: URL, revision: str = "head") -> None:
    engine = create_engine(url)
    try:
        with engine.begin() as conn:
            config = alembic_config()
            config.attributes["connection"] = conn
            command.upgrade(config, revision)
    finally:
        engine.dispose()


@contextmanager
def temporary_database(base: URL) -> Iterator[URL]:
    url = sibling_url(base)
    create_database(url)
    try:
        yield url
    finally:
        drop_database(url)


class ExternalNetworkBlocked(RuntimeError):
    pass


def _is_local(address: object) -> bool:
    if not isinstance(address, tuple) or not address:
        return True  # AF_UNIX paths
    host = str(address[0])
    if host in {"localhost", "testserver"}:
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def install_network_guard() -> list[tuple[object, str, object]]:
    """Deny non-loopback connects and external name resolution. Returns undo records."""
    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex
    real_getaddrinfo = socket.getaddrinfo

    def connect(self: socket.socket, address: object) -> None:
        if not _is_local(address):
            raise ExternalNetworkBlocked(f"external network blocked: {address!r}")
        real_connect(self, address)  # type: ignore[arg-type]

    def connect_ex(self: socket.socket, address: object) -> int:
        if not _is_local(address):
            raise ExternalNetworkBlocked(f"external network blocked: {address!r}")
        return real_connect_ex(self, address)  # type: ignore[arg-type]

    def getaddrinfo(host, *args, **kwargs):  # type: ignore[no-untyped-def]
        if host is not None and not _is_local((host,)):
            raise ExternalNetworkBlocked(f"external name resolution blocked: {host!r}")
        return real_getaddrinfo(host, *args, **kwargs)

    socket.socket.connect = connect  # type: ignore[method-assign,assignment]
    socket.socket.connect_ex = connect_ex  # type: ignore[method-assign,assignment]
    socket.getaddrinfo = getaddrinfo  # type: ignore[assignment]
    return [
        (socket.socket, "connect", real_connect),
        (socket.socket, "connect_ex", real_connect_ex),
        (socket, "getaddrinfo", real_getaddrinfo),
    ]

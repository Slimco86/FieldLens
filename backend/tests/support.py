"""Test isolation helpers: unsafe-URL rejection, unique databases and a loopback-only network."""

from __future__ import annotations

import re
import secrets
import socket
from collections.abc import Iterator
from contextlib import contextmanager
from ipaddress import ip_address

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

# fieldlens_<slice>_w<lane>_test_<8 lowercase hex>
TEST_DB_NAME = re.compile(r"^fieldlens_[a-z0-9]+_w[0-9]+_test_[0-9a-f]{8}$")
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
ENV_VAR = "FIELDLENS_TEST_DATABASE_URL"


class UnsafeTestDatabase(Exception):
    pass


def validate_test_database_url(raw: str | None) -> URL:
    """Fail explicitly for an absent or unsafe test database URL."""
    if not raw:
        raise UnsafeTestDatabase(
            f"{ENV_VAR} is not set. Use a dedicated loopback PostgreSQL database named "
            "fieldlens_<slice>_w<lane>_test_<8 lowercase hex>."
        )
    try:
        url = make_url(raw)
    except Exception as exc:
        raise UnsafeTestDatabase(f"{ENV_VAR} is not a valid URL") from exc
    if url.drivername != "postgresql+psycopg":
        raise UnsafeTestDatabase(f"{ENV_VAR} must use postgresql+psycopg:// (never SQLite)")
    if url.host not in LOOPBACK_HOSTS:
        raise UnsafeTestDatabase(f"{ENV_VAR} must target a loopback host")
    name = url.database or ""
    if "demo" in name.lower() or not TEST_DB_NAME.fullmatch(name):
        raise UnsafeTestDatabase(
            f"{ENV_VAR} database {name!r} is not a uniquely named test database"
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

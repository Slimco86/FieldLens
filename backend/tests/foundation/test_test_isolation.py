"""FN-6: default tests deny external network and use a uniquely named test database."""

from __future__ import annotations

import socket

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from tests import support

OK = "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_fl004a_w1_test_0a1b2c3d"


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
        "postgresql://u:p@127.0.0.1:55432/fieldlens_fl004a_w1_test_0a1b2c3d",
        "postgresql+psycopg://u:p@db.example.com:5432/fieldlens_fl004a_w1_test_0a1b2c3d",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_demo",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_fl004a_w1",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_demo_test_0a1b2c3d",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_fl004a_w1_test_0A1B2C3D",
        "postgresql+psycopg://u:p@127.0.0.1:55432/fieldlens_fl004a_w1_test_0a1b2c3",
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

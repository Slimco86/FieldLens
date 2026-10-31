"""FN-1 / FN-4 backend half: /health is 200; /ready reports unavailable DB as 503."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy.engine import URL

from fieldlens.app import create_app
from tests.conftest import migrate, settings_for

BASE = "http://127.0.0.1:8101"
SECRET = "pw-should-never-leak-9f3a"


def client(**kw: object) -> TestClient:
    return TestClient(create_app(settings_for(**kw)), base_url=BASE)  # type: ignore[arg-type]


def test_health_ok_without_database() -> None:
    r = client(database_url=None).get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers["x-request-id"]


def test_ready_unconfigured_database_is_503_not_empty_success() -> None:
    r = client(database_url=None).get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["error"]["code"] == "NOT_READY"
    assert body["error"]["request_id"] == r.headers["x-request-id"]
    checks = {c["name"]: c["ok"] for c in body["error"]["details"]["checks"]}
    assert checks == {"database": False, "migrations": False, "pgvector": False}


def test_ready_unreachable_database_is_503_and_does_not_leak_credentials() -> None:
    c = client(
        database_url=f"postgresql+psycopg://svc:{SECRET}@127.0.0.1:1/fieldlens_x",
        db_connect_timeout_s=1,
    )
    started = time.monotonic()
    r = c.get("/api/v1/ready")
    assert time.monotonic() - started < 10
    assert r.status_code == 503
    assert SECRET not in r.text
    assert "127.0.0.1:1" not in r.text


def test_create_app_does_not_touch_the_database() -> None:
    # An unreachable URL must not fail at import/creation time.
    create_app(settings_for(database_url="postgresql+psycopg://u:p@127.0.0.1:1/db"))


def test_ready_reports_unmigrated_then_ready(empty_database: URL) -> None:
    c = client(url=empty_database)
    r = c.get("/ready")
    assert r.status_code == 503
    checks = {x["name"]: x for x in r.json()["error"]["details"]["checks"]}
    assert checks["database"]["ok"] is True
    assert checks["migrations"]["ok"] is False
    migrate(empty_database)
    r = c.get("/ready")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ready"
    assert {x["name"] for x in r.json()["checks"]} == {"database", "migrations", "pgvector"}
    assert all(x["ok"] for x in r.json()["checks"])
    assert r.headers["cache-control"] == "no-store"


def test_ready_detects_missing_pgvector(migrated_url: URL) -> None:
    from sqlalchemy import create_engine, text

    eng = create_engine(migrated_url, isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        # 0007 adds a vector column that depends on the extension: CASCADE drops that column
        conn.execute(text("DROP EXTENSION vector CASCADE"))
    eng.dispose()
    r = client(url=migrated_url).get("/ready")
    assert r.status_code == 503
    checks = {x["name"]: x["ok"] for x in r.json()["error"]["details"]["checks"]}
    assert checks == {"database": True, "migrations": True, "pgvector": False}

"""FN-3: loopback binding, Host/Origin/fetch-metadata guards, token bootstrap, no secrets."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from fieldlens.app import create_app, require_mutation
from fieldlens.config import Settings
from fieldlens.contracts.base import ContractModel
from tests.conftest import settings_for

BASE = "http://127.0.0.1:8101"
REPO = Path(__file__).resolve().parents[3]


class _Body(ContractModel):
    name: str


def mutable_app(url: URL | None) -> FastAPI:
    app = create_app(settings_for(url))
    router = APIRouter()

    @router.post(
        "/api/v1/_probe/projects", status_code=201, dependencies=[Depends(require_mutation)]
    )
    def create_project(body: _Body) -> dict[str, str]:
        with create_engine(url).begin() as conn:  # type: ignore[arg-type]
            conn.execute(text("INSERT INTO project (name) VALUES (:n)"), {"n": body.name})
        return {"name": body.name}

    app.include_router(router)
    return app


def count(url: URL) -> int:
    eng = create_engine(url)
    with eng.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM project")).scalar_one()
    eng.dispose()
    return int(n)


# --- configuration / binding ---------------------------------------------------------------


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.5", "example.com", "::"])
def test_non_loopback_bind_host_is_rejected(host: str) -> None:
    with pytest.raises(ValidationError):
        Settings(host=host)


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_loopback_bind_host_is_accepted(host: str) -> None:
    assert Settings(host=host).host == host


def test_non_psycopg_database_url_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(database_url="sqlite:///x.db")


def test_secret_configuration_is_redacted() -> None:
    s = Settings(database_url="postgresql+psycopg://u:topsecret@127.0.0.1:1/db")
    assert "topsecret" not in repr(s)
    assert "topsecret" not in str(s.redacted())
    assert s.redacted()["database_url"] == "***"


def test_compose_binds_database_to_loopback_only() -> None:
    text_ = (REPO / "infra" / "compose.yaml").read_text()
    assert '"127.0.0.1:${FIELDLENS_DB_PORT:-55432}:5432"' in text_
    assert "0.0.0.0" not in text_
    assert "@sha256:" in text_  # image pinned by digest


def test_openapi_and_defaults_contain_no_secret_config() -> None:
    schema = str(create_app(settings_for(database_url=None)).openapi())
    for needle in ("database_url", "postgresql", "password", "FIELDLENS_"):
        assert needle not in schema


# --- Host / Origin / fetch metadata ---------------------------------------------------------


def test_disallowed_host_is_refused() -> None:
    c = TestClient(create_app(settings_for(database_url=None)), base_url="http://evil.example:8101")
    r = c.get("/health")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN_HOST"


def test_session_bootstrap_contract() -> None:
    app = create_app(settings_for(database_url=None))
    c = TestClient(app, base_url=BASE)
    r = c.get("/api/v1/session")
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    token = r.json()["csrf_token"]
    assert set(r.json()) == {"csrf_token"}
    assert len(token) >= 43  # 32 random bytes, base64url
    assert c.get("/api/v1/session").json()["csrf_token"] == token  # stable per process
    other = TestClient(create_app(settings_for(database_url=None)), base_url=BASE)
    assert other.get("/api/v1/session").json()["csrf_token"] != token  # new process -> new token


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({}, 200),  # local CLI / tests without fetch metadata
        ({"Sec-Fetch-Site": "same-origin"}, 200),
        ({"Sec-Fetch-Site": "none"}, 200),
        ({"Sec-Fetch-Site": "same-site", "Origin": "http://127.0.0.1:5174"}, 200),
        ({"Sec-Fetch-Site": "cross-site"}, 403),
        ({"Sec-Fetch-Site": "cross-site", "Origin": "http://127.0.0.1:5174"}, 403),
        ({"Origin": "https://evil.example"}, 403),
        ({"Sec-Fetch-Site": "same-site", "Origin": "http://127.0.0.1:9999"}, 403),
    ],
)
def test_session_bootstrap_fetch_metadata(headers: dict[str, str], status: int) -> None:
    c = TestClient(create_app(settings_for(database_url=None)), base_url=BASE)
    r = c.get("/api/v1/session", headers=headers)
    assert r.status_code == status
    if status == 403:
        assert "csrf_token" not in r.text


def test_no_wildcard_cors() -> None:
    c = TestClient(create_app(settings_for(database_url=None)), base_url=BASE)
    r = c.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
    r = c.options("/api/v1/session", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


# --- mutation guard --------------------------------------------------------------------------


def test_mutations_need_token_and_allowed_origin(migrated_url: URL) -> None:
    app = mutable_app(migrated_url)
    c = TestClient(app, base_url=BASE)
    token = c.get("/api/v1/session").json()["csrf_token"]
    path, body = "/api/v1/_probe/projects", {"name": "A"}

    r = c.post(path, json=body)  # no token
    assert (r.status_code, r.json()["error"]["code"]) == (403, "SESSION_TOKEN_INVALID")
    r = c.post(path, json=body, headers={"X-FieldLens-Token": "x" * 43})  # wrong token
    assert r.status_code == 403
    r = c.post(
        path, json=body, headers={"X-FieldLens-Token": token, "Origin": "https://evil.example"}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN_ORIGIN")
    r = c.post(
        path, json=body, headers={"X-FieldLens-Token": token, "Sec-Fetch-Site": "cross-site"}
    )
    assert (r.status_code, r.json()["error"]["code"]) == (403, "FORBIDDEN_FETCH_SITE")
    assert count(migrated_url) == 0  # nothing was written by any rejected attempt

    r = c.post(path, json=body, headers={"X-FieldLens-Token": token})
    assert r.status_code == 201
    r = c.post(
        path,
        json={"name": "B"},
        headers={"X-FieldLens-Token": token, "Origin": "http://127.0.0.1:5174"},
    )
    assert r.status_code == 201
    assert count(migrated_url) == 2

    bad_host = TestClient(app, base_url="http://evil.example:8101")
    r = bad_host.post(path, json=body, headers={"X-FieldLens-Token": token})
    assert r.status_code == 403
    assert count(migrated_url) == 2


def test_token_is_stale_after_restart_and_not_replayed(migrated_url: URL) -> None:
    first = TestClient(mutable_app(migrated_url), base_url=BASE)
    old = first.get("/api/v1/session").json()["csrf_token"]
    restarted = TestClient(mutable_app(migrated_url), base_url=BASE)  # new process, new token
    r = restarted.post(
        "/api/v1/_probe/projects", json={"name": "A"}, headers={"X-FieldLens-Token": old}
    )
    assert r.status_code == 403
    assert count(migrated_url) == 0
    fresh = restarted.get("/api/v1/session").json()["csrf_token"]
    r = restarted.post(
        "/api/v1/_probe/projects", json={"name": "A"}, headers={"X-FieldLens-Token": fresh}
    )
    assert r.status_code == 201


def test_token_never_in_logs(caplog: pytest.LogCaptureFixture) -> None:
    c = TestClient(create_app(settings_for(database_url=None)), base_url=BASE)
    with caplog.at_level("DEBUG"):
        token = c.get("/api/v1/session").json()["csrf_token"]
        c.get("/ready")
    assert token not in caplog.text


# --- static serving / error envelope -----------------------------------------------------------


def test_unknown_api_path_is_json_404_even_with_spa_build(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets" / "a.js").write_text("1")
    (tmp_path / "secret.txt").write_text("outside")
    app = create_app(settings_for(database_url=None, frontend_dist=dist))
    c = TestClient(app, base_url=BASE)

    for method in ("GET", "POST"):
        r = c.request(method, "/api/v1/nope")
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("application/json")
        assert r.json()["error"]["code"] == "NOT_FOUND"
    assert c.get("/api").json()["error"]["code"] == "NOT_FOUND"
    assert c.get("/projects/x").text == "<html>spa</html>"  # client-side route
    assert c.get("/assets/a.js").text == "1"
    assert c.get("/assets/missing.js").status_code == 404
    assert "outside" not in c.get("/..%2fsecret.txt").text
    assert "outside" not in c.get("/%2e%2e/secret.txt").text


def test_unhandled_error_is_sanitized() -> None:
    app = create_app(settings_for(database_url=None))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret-internal-detail")

    r = TestClient(app, base_url=BASE, raise_server_exceptions=False).get("/boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-internal-detail" not in r.text

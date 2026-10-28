from importlib.metadata import version
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from fieldlens import __version__
from fieldlens.app import create_app
from tests.conftest import settings_for


def test_health_and_package_version_follow_root_version() -> None:
    expected = (Path(__file__).resolve().parents[3] / "VERSION").read_text().strip()
    client = TestClient(create_app(settings_for()), base_url="http://127.0.0.1:8101")
    response = client.get("/health")
    assert response.json()["version"] == __version__ == version("fieldlens") == expected
    assert response.headers["cache-control"] == "no-store"


def test_unhandled_error_has_consistent_headers_and_sanitized_diagnostic(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(settings_for())

    @app.get("/api/v1/_probe/error")
    def fail() -> None:
        raise RuntimeError("secret-test-value")

    client = TestClient(app, base_url="http://127.0.0.1:8101", raise_server_exceptions=False)
    with caplog.at_level("ERROR"):
        response = client.get("/api/v1/_probe/error")
    assert response.status_code == 500
    assert response.headers["x-request-id"] == response.json()["error"]["request_id"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "Unhandled RuntimeError" in caplog.text
    assert "secret-test-value" not in caplog.text + response.text


def test_generic_http_forbidden_is_not_internal_error() -> None:
    app = create_app(settings_for())

    @app.get("/api/v1/_probe/forbidden")
    def forbidden() -> None:
        raise HTTPException(403, "Forbidden")

    response = TestClient(app, base_url="http://127.0.0.1:8101").get("/api/v1/_probe/forbidden")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"

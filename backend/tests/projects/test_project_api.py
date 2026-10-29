"""TASK-PRJ-01..05 backend: lifecycle API against real PostgreSQL (no SQLite, no mocks)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from fieldlens.app import create_app
from fieldlens.contracts.identity import Project
from tests.conftest import settings_for

BASE = "http://127.0.0.1:8101"
PATH = "/api/v1/projects"


def make_client(url: URL | None) -> tuple[TestClient, dict[str, str]]:
    settings = settings_for(url) if url is not None else settings_for(database_url=None)
    client = TestClient(create_app(settings), base_url=BASE)
    token = client.get("/api/v1/session").json()["csrf_token"]
    return client, {"X-FieldLens-Token": token}


@pytest.fixture
def api(migrated_url: URL) -> tuple[TestClient, dict[str, str]]:
    return make_client(migrated_url)


def create(api: tuple[TestClient, dict[str, str]], **body: Any) -> dict[str, Any]:
    client, headers = api
    r = client.post(PATH, json=body, headers=headers)
    assert r.status_code == 201, r.text
    return dict(r.json())


def error_code(r: Any) -> str:
    assert r.headers["cache-control"] == "no-store"
    body = r.json()
    assert set(body) == {"error"} and body["error"]["request_id"]
    return str(body["error"]["code"])


# --- create / get / patch ---------------------------------------------------------------------


def test_create_returns_closed_project_with_server_fields(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = api
    r = client.post(PATH, json={"name": "  Alpha  ", "description": "first"}, headers=headers)
    assert r.status_code == 201
    body = r.json()
    project = Project.model_validate(body)  # closed contract
    assert set(body) == set(Project.model_fields)
    assert project.name == "Alpha" and project.description == "first"
    assert project.latest_source_revision_id is None and project.active_model_revision_id is None
    assert project.created_at.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
    assert r.headers["location"] == f"{PATH}/{project.project_id}"
    assert client.get(f"{PATH}/{project.project_id}").json() == body


def test_client_cannot_choose_server_owned_fields(api: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = api
    for extra in ("project_id", "created_at", "latest_source_revision_id", "crs"):
        r = client.post(PATH, json={"name": "A", extra: str(uuid.uuid4())}, headers=headers)
        assert (r.status_code, error_code(r)) == (422, "VALIDATION_ERROR"), extra


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 121},
        {"name": None},
        {"name": 5},
        {"name": "ok", "description": "d" * 4001},
        {"name": "ok", "description": None},
    ],
)
def test_create_validation_422_and_nothing_persisted(
    api: tuple[TestClient, dict[str, str]], body: dict[str, Any]
) -> None:
    client, headers = api
    r = client.post(PATH, json=body, headers=headers)
    assert (r.status_code, error_code(r)) == (422, "VALIDATION_ERROR")
    assert client.get(PATH).json()["items"] == []


def test_name_and_description_boundaries(api: tuple[TestClient, dict[str, str]]) -> None:
    a = create(api, name="x" * 120, description="d" * 4000)
    assert len(a["name"]) == 120 and len(a["description"]) == 4000
    assert create(api, name=" " + "y" * 120 + " ")["name"] == "y" * 120  # trimmed first


def test_patch_partial_updates_and_preserves_the_rest(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, headers = api
    a = create(api, name="Alpha", description="keep")
    r = client.patch(f"{PATH}/{a['project_id']}", json={"name": " Alpha 2 "}, headers=headers)
    assert r.status_code == 200
    b = r.json()
    assert (b["name"], b["description"], b["created_at"]) == ("Alpha 2", "keep", a["created_at"])
    assert b["updated_at"] > a["updated_at"]
    r = client.patch(f"{PATH}/{a['project_id']}", json={"description": ""}, headers=headers)
    assert r.json()["description"] == "" and r.json()["name"] == "Alpha 2"
    assert client.get(f"{PATH}/{a['project_id']}").json() == r.json()


def test_noop_patch_does_not_bump_updated_at(api: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = api
    a = create(api, name="Alpha")
    r = client.patch(f"{PATH}/{a['project_id']}", json={"name": "Alpha"}, headers=headers)
    assert r.json() == a


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"name": None},
        {"description": None},
        {"name": ""},
        {"name": "x" * 121},
        {"description": "d" * 4001},
        {"project_id": str(uuid.uuid4())},
        {"unknown": 1},
    ],
)
def test_patch_validation_keeps_prior_values(
    api: tuple[TestClient, dict[str, str]], body: dict[str, Any]
) -> None:
    client, headers = api
    a = create(api, name="Alpha", description="before")
    r = client.patch(f"{PATH}/{a['project_id']}", json=body, headers=headers)
    assert (r.status_code, error_code(r)) == (422, "VALIDATION_ERROR")
    assert client.get(f"{PATH}/{a['project_id']}").json() == a


def test_unknown_and_malformed_ids(api: tuple[TestClient, dict[str, str]]) -> None:
    client, headers = api
    missing = uuid.uuid4()
    r = client.get(f"{PATH}/{missing}")
    assert (r.status_code, error_code(r)) == (404, "NOT_FOUND")
    r = client.patch(f"{PATH}/{missing}", json={"name": "x"}, headers=headers)
    assert (r.status_code, error_code(r)) == (404, "NOT_FOUND")
    for bad in ("not-a-uuid", "123"):
        assert client.get(f"{PATH}/{bad}").status_code == 422
        assert client.patch(f"{PATH}/{bad}", json={"name": "x"}, headers=headers).status_code == 422


# --- list / pagination -------------------------------------------------------------------------


def test_cursor_pagination_is_complete_stable_and_newest_first(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api
    created = [create(api, name=f"P{i}")["project_id"] for i in range(5)]
    seen: list[str] = []
    cursor: str | None = None
    pages = 0
    while True:
        params: dict[str, Any] = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        r = client.get(PATH, params=params)
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"items", "page"} and body["page"]["limit"] == 2
        seen += [p["project_id"] for p in body["items"]]
        pages += 1
        cursor = body["page"]["next_cursor"]
        if cursor is None:
            break
    assert pages == 3 and len(seen) == len(set(seen)) == 5
    assert seen == list(reversed(created))
    default = client.get(PATH).json()
    assert default["page"]["limit"] == 50 and len(default["items"]) == 5


def test_exact_page_boundary_has_no_phantom_next_page(
    api: tuple[TestClient, dict[str, str]],
) -> None:
    client, _ = api
    create(api, name="A")
    create(api, name="B")
    assert client.get(PATH, params={"limit": 2}).json()["page"]["next_cursor"] is None


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 201},
        {"limit": -1},
        {"limit": "abc"},
        {"limit": "1.5"},
        {"limit": ""},
        {"cursor": "not-a-cursor"},
        {"cursor": "e30"},
        {"cursor": "x" * 2049},
        {"unknown": "1"},
    ],
)
def test_list_malformed_input_is_422(
    api: tuple[TestClient, dict[str, str]], params: dict[str, str | int]
) -> None:
    client, _ = api
    create(api, name="A")
    r = client.get(PATH, params=params)
    assert (r.status_code, error_code(r)) == (422, "VALIDATION_ERROR")


def test_max_limit_accepted(api: tuple[TestClient, dict[str, str]]) -> None:
    client, _ = api
    r = client.get(PATH, params={"limit": 200})
    assert r.status_code == 200 and r.json()["page"]["limit"] == 200


# --- mutation protection -----------------------------------------------------------------------


def test_mutations_are_guarded_and_write_nothing(
    migrated_url: URL, api: tuple[TestClient, dict[str, str]]
) -> None:
    client, headers = api
    a = create(api, name="Alpha")
    body = {"name": "Evil"}
    bad = [
        {},
        {"X-FieldLens-Token": "x" * 43},
        {**headers, "Origin": "https://evil.example"},
        {**headers, "Sec-Fetch-Site": "cross-site"},
    ]
    for h in bad:
        assert client.post(PATH, json=body, headers=h).status_code == 403
        assert client.patch(f"{PATH}/{a['project_id']}", json=body, headers=h).status_code == 403
    # token is checked before validation and existence: no oracle for unauthenticated callers
    assert client.patch(f"{PATH}/{uuid.uuid4()}", json=body).status_code == 403
    assert client.post(PATH, json={}).status_code == 403
    assert [p["name"] for p in client.get(PATH).json()["items"]] == ["Alpha"]
    evil = TestClient(create_app(settings_for(migrated_url)), base_url="http://evil.example:8101")
    assert evil.get(PATH).status_code == 403


def test_restart_persists_and_old_token_is_refused(migrated_url: URL) -> None:
    first, h1 = make_client(migrated_url)
    a = create((first, h1), name="Alpha", description="persisted")
    second, h2 = make_client(migrated_url)  # a new app instance = restarted API
    assert second.get(f"{PATH}/{a['project_id']}").json() == a
    r = second.patch(f"{PATH}/{a['project_id']}", json={"name": "x"}, headers=h1)
    assert r.status_code == 403 and error_code(r) == "SESSION_TOKEN_INVALID"
    assert second.get(f"{PATH}/{a['project_id']}").json() == a


# --- failure behaviour -------------------------------------------------------------------------


def test_database_unavailable_is_503_envelope_not_success() -> None:
    client, headers = make_client(None)
    for r in (
        client.get(PATH),
        client.get(f"{PATH}/{uuid.uuid4()}"),
        client.post(PATH, json={"name": "A"}, headers=headers),
    ):
        assert (r.status_code, error_code(r)) == (503, "SERVICE_UNAVAILABLE")


def test_failed_write_rolls_back_and_keeps_prior_values(
    migrated_url: URL, api: tuple[TestClient, dict[str, str]], engine: Engine
) -> None:
    client, headers = api
    a = create(api, name="Alpha", description="before")
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE project DROP CONSTRAINT ck_project_description_max_length"))
        conn.execute(
            text(
                "ALTER TABLE project ADD CONSTRAINT ck_project_description_max_length "
                "CHECK (char_length(description) <= 3) NOT VALID"
            )
        )
    safe = TestClient(
        create_app(settings_for(migrated_url)), base_url=BASE, raise_server_exceptions=False
    )
    token = safe.get("/api/v1/session").json()["csrf_token"]
    r = safe.patch(
        f"{PATH}/{a['project_id']}",
        json={"name": "Changed", "description": "toolong"},
        headers={"X-FieldLens-Token": token},
    )
    assert (r.status_code, error_code(r)) == (500, "INTERNAL_ERROR")
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name, description FROM project WHERE project_id=:i"),
            {"i": a["project_id"]},
        ).one()
    assert tuple(row) == ("Alpha", "before")  # no partial name-only update


# --- PW-2 / SC-2 (project scope) and PW-5 (name is not evidence) -------------------------------


def test_project_isolation(api: tuple[TestClient, dict[str, str]], engine: Engine) -> None:
    client, headers = api
    a = create(api, name="A", description="alpha")
    b = create(api, name="B", description="beta")
    assert client.get(f"{PATH}/{a['project_id']}").json()["description"] == "alpha"
    client.patch(f"{PATH}/{b['project_id']}", json={"description": "beta2"}, headers=headers)
    assert client.get(f"{PATH}/{a['project_id']}").json() == a  # editing B never touches A
    assert client.get(f"{PATH}/{a['project_id']}").json()["project_id"] != b["project_id"]
    # Revision pointers are project-qualified in the schema, so project B cannot point at
    # project A's revisions (composite FK from the foundation migration).
    with engine.begin() as conn:
        src = conn.execute(
            text(
                "INSERT INTO source_revision (project_id, manifest_hash, status) "
                "VALUES (:p, :h, 'ready') RETURNING source_revision_id"
            ),
            {"p": a["project_id"], "h": "0" * 64},
        ).scalar_one()
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text("UPDATE project SET latest_source_revision_id=:s WHERE project_id=:b"),
            {"s": src, "b": b["project_id"]},
        )


def test_category_is_not_evidence(api: tuple[TestClient, dict[str, str]]) -> None:
    """A name/description is opaque text: no well, CRS, date or numeric claim is derived."""
    client, headers = api
    text_ = "F-12 well, EPSG:23031, installed 2008-03-01, TD 3500 m"
    a = create(api, name="F-12 report (really F-11)", description=text_)
    assert set(a) == set(Project.model_fields)  # no inferred identity/CRS/date fields exist
    assert a["latest_source_revision_id"] is None and a["active_model_revision_id"] is None
    r = client.patch(f"{PATH}/{a['project_id']}", json={"name": "F-11"}, headers=headers)
    assert r.json()["description"] == text_ and r.json()["name"] == "F-11"
    schema = create_app(settings_for(database_url=None)).openapi()["components"]["schemas"]
    for dto in ("Project", "ProjectCreate", "ProjectUpdate"):
        assert not {"well_id", "crs", "epsg", "date"} & set(schema[dto]["properties"])


def test_openapi_documents_lifecycle_routes() -> None:
    paths = create_app(settings_for(database_url=None)).openapi()["paths"]
    assert set(paths[PATH]) == {"get", "post"}
    assert set(paths[f"{PATH}/{{project_id}}"]) == {"get", "patch"}
    schemas = create_app(settings_for(database_url=None)).openapi()["components"]["schemas"]
    assert {"ProjectCreate", "ProjectUpdate", "ProjectPage"} <= set(schemas)

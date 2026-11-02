"""Project deletion (TASK-071): completeness, isolation, triggers, drain, resume, root guard, race."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError

from fieldlens.projects.purge import PURGE_ORDER, ProjectPurger, uncovered_tables
from tests.projects.purge_support import count_rows, populate_project, project_tables
from tests.upload_support import PDF, Api, make_api, make_pdf

SPEND_TABLES = ("budget_period", "pricing_revision", "spend_reservation", "provider_attempt")


def _purger(api: Api, *, drain: float = 900.0, root_ok: bool | None = True) -> ProjectPurger:
    purger: ProjectPurger = api.client.app.state.purger  # type: ignore[attr-defined]
    purger._drain_timeout = drain
    if root_ok is not None:
        purger._guard.serves_database = lambda: root_ok  # type: ignore[method-assign]
    return purger


def _delete(api: Api, pid: str, name: str | None = "P") -> Any:
    body: dict[str, Any] = {} if name is None else {"confirm_name": name}
    return api.client.request("DELETE", f"/api/v1/projects/{pid}", json=body, headers=api.headers)


def _state(engine: Engine, pid: str) -> tuple[str, str | None] | None:
    with engine.connect() as c:
        row = c.execute(
            text("SELECT deletion_state, deletion_error FROM project WHERE project_id=:p"),
            {"p": pid},
        ).one_or_none()
    return None if row is None else (row[0], row[1])


def _spend_snapshot(engine: Engine) -> dict[str, int]:
    with engine.connect() as c:
        return {
            t: int(c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one())  # noqa: S608
            for t in SPEND_TABLES
        }


@pytest.fixture
def api(migrated_url: URL, tmp_path: Path) -> Api:
    return make_api(migrated_url, tmp_path / "storage")


def test_every_project_table_is_covered(engine: Engine) -> None:
    with engine.connect() as c:
        tables = set(project_tables(c))
    assert tables - {"project"} <= set(PURGE_ORDER), tables - {"project"} - set(PURGE_ORDER)
    assert uncovered_tables() == set()
    assert not (set(PURGE_ORDER) - tables), "PURGE_ORDER lists a table without project_id"
    assert not set(SPEND_TABLES) & tables  # ledger tables carry no project_id


def test_confirm_name_and_unknown_project(api: Api, engine: Engine) -> None:
    pid = api.project("P")
    assert _delete(api, pid, "p").status_code == 422
    assert _delete(api, pid, None).status_code == 422
    assert _state(engine, pid) == ("none", None)
    assert _delete(api, str(uuid.uuid4())).status_code == 404
    preview = api.client.get(f"/api/v1/projects/{pid}/deletion-preview")
    assert preview.status_code == 200 and preview.json()["name"] == "P"
    r = _delete(api, pid)
    assert r.status_code == 202 and r.json()["deletion_state"] == "deleting"
    assert _delete(api, pid).status_code == 202  # idempotent


def test_purge_removes_everything_and_keeps_others(api: Api, engine: Engine) -> None:
    a, b = api.project("P"), api.project("Other")
    with engine.begin() as c:
        counts_a = populate_project(c, uuid.UUID(a))
        populate_project(c, uuid.UUID(b))
        before_b = count_rows(c, uuid.UUID(b))
    assert all(n >= 1 for n in counts_a.values()), counts_a
    spend_before = _spend_snapshot(engine)
    blob_a = api.storage / "projects" / a / "blobs" / "aa"
    blob_b = api.storage / "projects" / b / "blobs" / "aa"
    for d in (blob_a, blob_b):
        d.mkdir(parents=True)
        (d / "x").write_bytes(b"x")
    assert _delete(api, a).status_code == 202
    assert api.client.post(
        f"/api/v1/projects/{a}/uploads", headers=api.headers, data={}
    ).status_code in (409, 422)
    purger = _purger(api)
    assert purger.run_once() is True
    assert _state(engine, a) is None
    with engine.connect() as c:
        assert sum(count_rows(c, uuid.UUID(a)).values()) == 0
        assert count_rows(c, uuid.UUID(b)) == before_b
    assert not (api.storage / "projects" / a).exists()
    assert (blob_b / "x").exists()
    assert _spend_snapshot(engine) == spend_before
    assert purger.run_once() is False  # nothing left; second pass is a no-op
    assert api.client.get(f"/api/v1/projects/{a}").status_code == 404


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM source_document",
        "DELETE FROM source_revision",
        "DELETE FROM source_revision_document",
        "DELETE FROM document_classification_event",
    ],
)
def test_guarded_tables_reject_delete_without_setting(api: Api, engine: Engine, sql: str) -> None:
    a, b = api.project("P"), api.project("Other")
    with engine.begin() as c:
        populate_project(c, uuid.UUID(a))
        populate_project(c, uuid.UUID(b))
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text(sql))
    # the setting names project A: project B's rows stay protected
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text("SELECT set_config('fieldlens.purge_project_id', :p, true)"), {"p": a})
        c.execute(text(f"{sql} WHERE project_id = :b"), {"b": b})


def test_in_flight_work_is_cancelled_and_mutations_conflict(api: Api, engine: Engine) -> None:
    pid = api.project("P")
    up = api.upload(pid, [("a.pdf", make_pdf("1"))])
    assert up.status_code in (200, 201, 202), up.text
    assert _delete(api, pid).status_code == 202
    with engine.connect() as c:
        states = [
            r[0]
            for r in c.execute(
                text("SELECT status FROM ingest_job WHERE project_id=:p"), {"p": pid}
            )
        ]
    assert states and all(s in ("cancelled", "running", "succeeded", "failed") for s in states)
    blocked = api.upload(pid, [("b.pdf", make_pdf("2"))])
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["reason"] == "project_deleting"
    run = api.client.post(
        "/api/v1/processing/runs/estimates", json={"project_id": pid}, headers=api.headers
    )
    assert run.status_code in (409, 404, 422)


def test_executor_waits_for_leases_then_proceeds(api: Api, engine: Engine) -> None:
    pid = api.project("P")
    with engine.begin() as c:
        populate_project(c, uuid.UUID(pid))
        c.execute(
            text(
                "UPDATE extraction_run SET lease_owner='w', "
                "lease_expires_at=now() + interval '1 hour' WHERE project_id=:p"
            ),
            {"p": pid},
        )
    assert _delete(api, pid).status_code == 202
    purger = _purger(api)
    assert purger.run_once() is False
    assert _state(engine, pid) == ("deleting", None)
    with engine.begin() as c:
        c.execute(
            text("UPDATE extraction_run SET lease_owner=NULL WHERE project_id=:p"), {"p": pid}
        )
    assert purger.run_once() is True
    assert _state(engine, pid) is None


def test_drain_timeout_fails_then_retry(api: Api, engine: Engine) -> None:
    pid = api.project("P")
    with engine.begin() as c:
        populate_project(c, uuid.UUID(pid))
        c.execute(
            text(
                "UPDATE extraction_run SET lease_owner='w', "
                "lease_expires_at=now() + interval '1 hour' WHERE project_id=:p"
            ),
            {"p": pid},
        )
    assert _delete(api, pid).status_code == 202
    purger = _purger(api, drain=-1.0)
    assert purger.run_once() is True
    state = _state(engine, pid)
    assert state is not None and state[0] == "failed" and state[1]
    # mutations stay blocked, retry is the same DELETE
    assert api.upload(pid, [("b.pdf", make_pdf("2"))]).status_code == 409
    with engine.begin() as c:
        c.execute(
            text("UPDATE extraction_run SET lease_owner=NULL WHERE project_id=:p"), {"p": pid}
        )
    assert _delete(api, pid).status_code == 202
    purger = _purger(api)
    assert purger.run_once() is True
    assert _state(engine, pid) is None


def test_crash_resume_after_disk_phase(api: Api, engine: Engine) -> None:
    pid = api.project("P")
    with engine.begin() as c:
        populate_project(c, uuid.UUID(pid))
    d = api.storage / "projects" / pid / "blobs" / "aa"
    d.mkdir(parents=True)
    (d / "x").write_bytes(b"x")
    assert _delete(api, pid).status_code == 202
    # simulate a crash right after the disk phase: files gone, marker set, rows remain
    import shutil

    shutil.rmtree(api.storage / "projects" / pid)
    with engine.begin() as c:
        c.execute(
            text("UPDATE project SET deletion_storage_purged_at=now() WHERE project_id=:p"),
            {"p": pid},
        )
    purger = _purger(api, root_ok=False)  # root check must not run again
    assert purger.run_once() is True
    assert _state(engine, pid) is None


def test_root_mismatch_pauses_without_deleting(api: Api, engine: Engine) -> None:
    pid = api.project("P")
    with engine.begin() as c:
        populate_project(c, uuid.UUID(pid))
        before = count_rows(c, uuid.UUID(pid))
    d = api.storage / "projects" / pid / "blobs" / "aa"
    d.mkdir(parents=True)
    (d / "x").write_bytes(b"x")
    assert _delete(api, pid).status_code == 202
    purger = _purger(api, root_ok=False)
    assert purger.run_once() is True
    state = _state(engine, pid)
    assert state is not None and state[0] == "failed" and "storage root" in (state[1] or "")
    assert (d / "x").exists()
    with engine.connect() as c:
        assert count_rows(c, uuid.UUID(pid)) == before


def test_upload_after_phase_one_leaves_no_orphans(api: Api, engine: Engine) -> None:
    pid = api.project("P")
    assert _delete(api, pid).status_code == 202
    r = api.upload(pid, [("a.pdf", PDF + b"late")])
    assert r.status_code == 409
    assert api.blob_files() == []
    with engine.connect() as c:
        assert (
            c.execute(
                text("SELECT count(*) FROM source_document WHERE project_id=:p"), {"p": pid}
            ).scalar_one()
            == 0
        )


def test_dto_registered() -> None:
    from fieldlens.contracts.registry import public_models

    names = {mdl.__name__ for mdl in public_models()}
    assert {"ProjectDeleteRequest", "ProjectDeletionPreview", "ProjectDeletionStatus"} <= names


def test_engine_factory_smoke(migrated_url: URL) -> None:
    eng = create_engine(migrated_url)
    try:
        with eng.connect() as c:
            assert "project" in project_tables(c)
    finally:
        eng.dispose()

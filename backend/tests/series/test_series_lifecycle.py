"""DC-10 on PostgreSQL: series commit atomically with the run, vanish when the run is interrupted
or fails, are superseded with the run, and cascade away with run/record/document."""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session

from fieldlens.extraction import runner as runner_module
from fieldlens.profiles import registry
from fieldlens.profiles.las import LasProfile
from fieldlens.series.builder import store_series
from tests.profile_support import CTX, write
from tests.series.support import Lane, las_text

ROWS = [[100.0 + i, 40.0 + i, 2.0] for i in range(25)]


@pytest.fixture
def lane(migrated_url: URL, tmp_path: Path, engine: Engine) -> Lane:
    return Lane(migrated_url, tmp_path, engine)


def _counts(lane: Lane) -> tuple[int, int]:
    return (
        lane.sql("select count(*) from series_axis")[0][0],
        lane.sql("select count(*) from series_curve")[0][0],
    )


def test_series_are_written_with_the_run_and_a_failure_after_insert_leaves_none(
    lane: Lane, monkeypatch: pytest.MonkeyPatch
) -> None:
    (doc,) = lane.upload([("a.las", las_text(ROWS).encode())])
    real = runner_module.store_series

    def insert_then_crash(*args: Any, **kwargs: Any) -> int:
        real(*args, **kwargs)
        assert lane.sql("select 1")  # rows are written inside the (uncommitted) transaction
        raise RuntimeError("crash after the series insert")

    monkeypatch.setattr(runner_module, "store_series", insert_then_crash)
    lane.drain()
    run = lane.sql("select status, error from extraction_run where document_id = :d", d=doc)[0]
    assert run.status == "failed"
    assert _counts(lane) == (0, 0), "an interrupted finalization leaves no visible series"
    assert lane.sql("select count(*) from extracted_record")[0][0] == 0
    assert lane.series() == []
    monkeypatch.setattr(runner_module, "store_series", real)
    # a retry (explicit) produces the series exactly once
    r = lane.api.client.post(
        f"/api/v1/projects/{lane.pid}/documents/{doc}/extraction?retry=true",
        headers=lane.api.headers,
    )
    assert r.json()["outcome"] == "queued"
    lane.drain()
    assert _counts(lane) == (1, 2)
    assert {i["measure"] for i in lane.series()} == {"GR", "RHOB"}


def test_lost_lease_publishes_nothing(lane: Lane, monkeypatch: pytest.MonkeyPatch) -> None:
    (doc,) = lane.upload([("a.las", las_text(ROWS).encode())])
    original = LasProfile.parse

    def parse_then_supersede(self: LasProfile, path: Path, ctx: Any) -> Any:
        out = original(self, path, ctx)
        lane.sql("update extraction_run set superseded = true where document_id = :d", d=doc)
        return out

    monkeypatch.setattr(LasProfile, "parse", parse_then_supersede)
    lane.drain()
    assert _counts(lane) == (0, 0) and lane.series() == []


def test_killed_process_mid_finalization_leaves_no_series_and_recovers(
    lane: Lane, tmp_path: Path
) -> None:
    (doc,) = lane.upload([("a.las", las_text(ROWS).encode())])
    script = tmp_path / "kill_worker.py"
    script.write_text(
        textwrap.dedent(
            """
            import os, sys
            from sqlalchemy import text
            from fieldlens.app import create_app
            from fieldlens.config import Settings
            from fieldlens.extraction import runner

            url, storage = sys.argv[1:3]
            app = create_app(
                Settings(_env_file=None, database_url=url, storage_root=storage,
                         job_worker_enabled=False, extraction_max_attempts=3)
            )

            def die(self, session, claim, state, detail):
                n = session.execute(text("select count(*) from series_curve")).scalar_one()
                sys.stderr.write(f"series_rows_in_open_transaction={n}\\n")
                sys.stderr.flush()
                os._exit(137)  # SIGKILL-style: no rollback handler, no cleanup

            runner.ExtractionRunner._set_state = die
            app.state.job_worker.extraction.run_once()
            """
        )
    )
    proc = subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(script),
            lane.url.render_as_string(hide_password=False),
            str(lane.tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 137, proc.stderr[-2000:]
    assert "series_rows_in_open_transaction=2" in proc.stderr
    run = lane.sql("select status, attempt_no from extraction_run where document_id = :d", d=doc)[0]
    assert (run.status, run.attempt_no) == ("running", 1), "the run never finalized"
    assert _counts(lane) == (0, 0), "the killed transaction left nothing behind"
    assert lane.series() == []
    lane.sql(
        "update extraction_run set lease_expires_at = now() - interval '1 second' "
        "where document_id = :d",
        d=doc,
    )
    assert lane.api.worker.extraction.recover_once() == 1
    assert lane.sql("select status from extraction_run where document_id = :d", d=doc)[0][0] == (
        "interrupted"
    )
    assert lane.series() == []
    lane.drain()
    assert lane.sql("select status from extraction_run where document_id = :d", d=doc)[0][0] == (
        "succeeded"
    )
    assert _counts(lane) == (1, 2)
    assert {i["sample_count"] for i in lane.series()} == {25}


def test_profile_bump_supersedes_series_with_the_run(
    lane: Lane, monkeypatch: pytest.MonkeyPatch
) -> None:
    (doc,) = lane.upload([("a.las", las_text(ROWS).encode())])
    lane.drain()
    first_run = lane.sql("select run_id from extraction_run where document_id = :d", d=doc)[0][0]
    first_ids = {i["series_id"] for i in lane.series()}
    assert first_ids and {i["run_id"] for i in lane.series()} == {str(first_run)}
    monkeypatch.setattr(type(registry.by_name("las_2_0")), "version", "9999.0.0")
    assert (
        lane.api.client.post(
            f"/api/v1/projects/{lane.pid}/documents/{doc}/extraction", headers=lane.api.headers
        ).json()["outcome"]
        == "queued"
    )
    assert lane.series() == [], "a superseded run's series are not visible while it is rederived"
    assert (
        lane.api.client.get(
            f"/api/v1/projects/{lane.pid}/series/{next(iter(first_ids))}"
        ).status_code
        == 404
    )
    lane.drain()
    second = lane.series()
    assert second and {i["series_id"] for i in second}.isdisjoint(first_ids)
    assert {i["evidence"]["profile_version"] for i in second} == {"9999.0.0"}
    assert lane.sql("select count(*) from series_axis where run_id = :r", r=first_run)[0][0] == 0, (
        "the superseded run's series rows are removed when the new run finalizes"
    )
    assert _counts(lane) == (1, 2)


def test_store_series_is_idempotent_for_a_retried_finalization(lane: Lane) -> None:
    (doc,) = lane.upload([("a.las", las_text(ROWS).encode())])
    lane.drain()
    before = sorted(i["series_id"] for i in lane.series())
    run = lane.sql("select run_id from extraction_run where document_id = :d", d=doc)[0][0]
    axes = LasProfile().parse(write(lane.tmp_path, "again.las", las_text(ROWS)), CTX).series
    with lane.engine.begin() as conn:
        session = Session(bind=conn)
        store_series(session, UUID(lane.pid), run, UUID(doc), axes)
        session.flush()
    assert sorted(i["series_id"] for i in lane.series()) == before
    assert _counts(lane) == (1, 2)


def test_cascades_run_record_and_document_hook(lane: Lane) -> None:
    (doc,) = lane.upload([("a.las", las_text(ROWS).encode())])
    lane.drain()
    assert _counts(lane) == (1, 2)
    fks = {
        r.conname: r.confdeltype
        for r in lane.sql(
            "select conname, confdeltype from pg_constraint where conname like 'fk_series_%'"
        )
    }
    assert fks == {
        "fk_series_axis_run_scope": "c",
        "fk_series_axis_document_scope": "c",
        "fk_series_curve_axis_scope": "c",
        "fk_series_curve_record": "c",
    }
    # the source-removal hook: deleting by document removes every series of that document
    lane.sql(
        "delete from series_axis where project_id = :p and document_id = :d", p=lane.pid, d=doc
    )
    assert _counts(lane) == (0, 0)
    # re-derive, then removing a record or the run takes the dependent series with it
    lane.sql("update extraction_run set superseded = true where document_id = :d", d=doc)
    lane.drain()
    assert _counts(lane) == (1, 2)
    lane.sql(
        "delete from extracted_record where run_id in (select run_id from extraction_run "
        "where document_id = :d and not superseded) and kind = 'las_curve' "
        "and locator->>'las_mnemonic' = 'GR'",
        d=doc,
    )
    assert _counts(lane) == (1, 1), "a series cannot outlive the record it is anchored to"
    lane.sql("delete from extraction_run where document_id = :d", d=doc)
    assert _counts(lane) == (0, 0)


def test_database_rejects_inconsistent_ranges(lane: Lane) -> None:
    from sqlalchemy.exc import IntegrityError

    lane.upload([("a.las", las_text(ROWS).encode())])
    lane.drain()
    for statement in (
        "update series_curve set min_value = max_value + 1 where measure = 'GR'",
        "update series_axis set index_min = index_max + 1",
        "update series_curve set valid_count = 0, null_count = sample_count where measure = 'GR'",
    ):
        with pytest.raises(IntegrityError):
            lane.sql(statement)
    assert _counts(lane) == (1, 2)

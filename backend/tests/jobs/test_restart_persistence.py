"""IN-4 with a real process: kill -9 the API mid-stage, restart it, observe recovery in PostgreSQL."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.engine import URL

from tests.upload_support import PDF


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def _api(
    url: URL, storage: Path, port: int, stage_delay: float
) -> Iterator[subprocess.Popen[bytes]]:
    env = dict(os.environ)
    env.update(
        FIELDLENS_DATABASE_URL=url.render_as_string(hide_password=False),
        FIELDLENS_STORAGE_ROOT=str(storage),
        FIELDLENS_PORT=str(port),
        FIELDLENS_ALLOWED_HOSTS=json.dumps([f"127.0.0.1:{port}"]),
        FIELDLENS_ALLOWED_ORIGINS=json.dumps([f"http://127.0.0.1:{port}"]),
        FIELDLENS_JOB_STAGE_DELAY_S=str(stage_delay),
        FIELDLENS_JOB_POLL_SECONDS="0.1",
    )
    proc = subprocess.Popen(  # noqa: S603 - fixed argv, test-only
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fieldlens.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                if (
                    httpx.get(f"http://127.0.0.1:{port}/api/v1/health", timeout=1).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            pytest.fail("API did not start")
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


def _wait(fn: Callable[[], Any], timeout: float = 30.0) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(0.2)
    pytest.fail("condition not met in time")


def test_kill_dash_9_mid_stage_then_restart_recovers_and_completes(
    migrated_url: URL, tmp_path: Path
) -> None:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    storage = tmp_path / "store"
    with _api(migrated_url, storage, port, stage_delay=30.0) as first:
        token = httpx.get(f"{base}/api/v1/session").json()["csrf_token"]
        headers = {"X-FieldLens-Token": token}
        project = httpx.post(f"{base}/api/v1/projects", json={"name": "R"}, headers=headers).json()
        pid = project["project_id"]
        meta = {
            "expected_parent_source_revision_id": None,
            "files": [{"categories": ["trajectory"]}],
        }
        accepted = httpx.post(
            f"{base}/api/v1/projects/{pid}/imports",
            files=[
                ("metadata", (None, json.dumps(meta).encode(), "application/json")),
                ("files", ("a.pdf", PDF, "application/pdf")),
            ],
            headers=headers,
        )
        assert accepted.status_code == 202, accepted.text
        job_id = accepted.json()["job_id"]
        job_url = f"{base}/api/v1/projects/{pid}/jobs/{job_id}"
        _wait(lambda: httpx.get(job_url).json()["status"] == "running")
        os.kill(first.pid, signal.SIGKILL)
        first.wait(timeout=10)

    sha = hashlib.sha256(PDF).hexdigest()
    with _api(migrated_url, storage, port, stage_delay=0.0):
        job = _wait(lambda: (j := httpx.get(job_url).json())["status"] == "succeeded" and j)
        assert [(a["attempt_no"], a["status"], a["fencing_token"]) for a in job["attempts"]] == [
            (1, "interrupted", 1),
            (2, "succeeded", 2),
        ]
        docs = httpx.get(f"{base}/api/v1/projects/{pid}/documents").json()["items"]
        assert [(d["sha256"], d["size_bytes"], d["storage_state"]) for d in docs] == [
            (sha, len(PDF), "stored")
        ]
        assert docs[0]["classification"]["user_categories"] == ["trajectory"]
        latest = httpx.get(f"{base}/api/v1/projects/{pid}").json()
        assert latest["latest_source_revision_id"] == accepted.json()["source_revision_id"]
        assert latest["active_model_revision_id"] is None
    assert (storage / "projects" / pid / "blobs" / sha[:2] / sha).read_bytes() == PDF

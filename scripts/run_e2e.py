"""Run browser tests against a fresh PostgreSQL database and an owned loopback API."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tests import support  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-state", choices=("down", "up"))
    args, selectors = parser.parse_known_args()
    if args.database_state:
        url = support.validate_test_database_url(os.environ.get("FIELDLENS_E2E_DATABASE_URL"))
        if args.database_state == "down":
            support.drop_database(url)
        else:
            support.create_database(url)
            support.migrate(url)
        return 0

    base = support.validate_test_database_url(os.environ.get(support.ENV_VAR))
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node 24 is required on PATH")
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise RuntimeError("Build the frontend before running E2E tests")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 8101))
    with support.temporary_database(base) as url:
        support.migrate(url)
        env = os.environ | {
            "FIELDLENS_DATABASE_URL": url.render_as_string(hide_password=False),
            "FIELDLENS_E2E_DATABASE_URL": url.render_as_string(hide_password=False),
            "FIELDLENS_FRONTEND_DIST": str(ROOT / "frontend/dist"),
            "FIELDLENS_STORAGE_ROOT": str(ROOT / ".local/fieldlens/fl-004-a-foundation/tmp/e2e"),
        }
        api = subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "-m",
                "uvicorn",
                "fieldlens.app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                "8101",
            ],
            cwd=ROOT,
            env=env,
        )
        try:
            with httpx.Client(trust_env=False, timeout=1) as client:
                deadline = time.monotonic() + 30
                while True:
                    if api.poll() is not None:
                        raise RuntimeError("E2E API exited before becoming ready")
                    try:
                        ready = client.get("http://127.0.0.1:8101/ready").status_code == 200
                    except httpx.TransportError:
                        ready = False
                    if ready:
                        break
                    if time.monotonic() >= deadline:
                        raise RuntimeError("E2E API did not become ready within 30 seconds")
                    time.sleep(0.1)
            result = subprocess.run(  # noqa: S603
                [node, str(ROOT / "frontend/node_modules/playwright/cli.js"), "test", *selectors],
                cwd=ROOT / "frontend",
                env=env,
                check=False,
                timeout=180,
            )
            return result.returncode
        finally:
            api.terminate()
            try:
                api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
                api.wait()


if __name__ == "__main__":
    raise SystemExit(main())

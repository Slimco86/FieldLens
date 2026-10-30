"""Run browser tests against a fresh PostgreSQL database and an owned loopback API."""

from __future__ import annotations

import argparse
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldlens.localenv import load_local_env  # noqa: E402
from tests import support  # noqa: E402

DEFAULT_API_PORT = 8101


def api_port() -> int:
    """E2E API port: ``FIELDLENS_E2E_API_PORT`` (lane runs) or the default 8101."""
    raw = os.environ.get("FIELDLENS_E2E_API_PORT", "").strip()
    if not raw:
        return DEFAULT_API_PORT
    if not raw.isdigit() or not 1024 <= int(raw) <= 65535:
        raise RuntimeError("FIELDLENS_E2E_API_PORT must be an integer from 1024 to 65535")
    return int(raw)


API_PORT = api_port()
RESTART_TIMEOUT_S = 60
SUITE_TIMEOUT_S = 300
# .env key -> Playwright variable for the child process (a real exported variable wins).
BROWSER_KEYS = {
    "FIELDLENS_PW_CONNECT_WS_ENDPOINT": "PW_TEST_CONNECT_WS_ENDPOINT",
    "FIELDLENS_PW_EXPOSE_NETWORK": "PW_TEST_CONNECT_EXPOSE_NETWORK",
}


def _browser_env(local: dict[str, str]) -> dict[str, str]:
    """Playwright connection variables from .env unless already set in the environment."""
    result: dict[str, str] = {}
    for key, target in BROWSER_KEYS.items():
        if os.environ.get(target):
            continue
        value = os.environ.get(key) or local.get(key)
        if value:
            result[target] = value
    return result


def _start_api(env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "fieldlens.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(API_PORT),
        ],
        cwd=ROOT,
        env=env,
    )


def _wait_ready(api: subprocess.Popen[bytes]) -> None:
    with httpx.Client(trust_env=False, timeout=1) as client:
        deadline = time.monotonic() + 30
        while True:
            if api.poll() is not None:
                raise RuntimeError("E2E API exited before becoming ready")
            try:
                ready = client.get(f"http://127.0.0.1:{API_PORT}/ready").status_code == 200
            except httpx.TransportError:
                ready = False
            if ready:
                return
            if time.monotonic() >= deadline:
                raise RuntimeError("E2E API did not become ready within 30 seconds")
            time.sleep(0.1)


def _stop_api(api: subprocess.Popen[bytes]) -> None:
    api.terminate()
    try:
        api.wait(timeout=10)
    except subprocess.TimeoutExpired:
        api.kill()
        api.wait()


def _request_api_restart() -> int:
    """Ask the runner that owns the API to restart it (a real process restart, same database).

    This is a file handshake inside the runner's private control directory, not an HTTP endpoint
    of the application.
    """
    control = os.environ.get("FIELDLENS_E2E_CONTROL_DIR")
    if not control:
        raise RuntimeError("FIELDLENS_E2E_CONTROL_DIR is not set; run through the E2E runner")
    request, done = Path(control) / "restart.request", Path(control) / "restart.done"
    done.unlink(missing_ok=True)
    request.touch()
    deadline = time.monotonic() + RESTART_TIMEOUT_S
    while not done.exists():
        if time.monotonic() >= deadline:
            request.unlink(missing_ok=True)
            raise RuntimeError("API restart was not acknowledged")
        time.sleep(0.1)
    done.unlink(missing_ok=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-state", choices=("down", "up"))
    parser.add_argument("--api-restart", action="store_true")
    args, selectors = parser.parse_known_args()
    if args.api_restart:
        return _request_api_restart()
    if args.database_state:
        url = support.validate_test_database_url(os.environ.get("FIELDLENS_E2E_DATABASE_URL"))
        if args.database_state == "down":
            support.drop_database(url)
        else:
            support.create_database(url)
            support.migrate(url)
        return 0

    base = support.resolve_test_database_url()
    local = load_local_env()
    browser_env = _browser_env(local)
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node 24 is required on PATH")
    if not (ROOT / "frontend/dist/index.html").is_file():
        raise RuntimeError("Build the frontend before running E2E tests")
    with socket.socket() as probe:
        probe.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEADDR, 1
        )  # like uvicorn: ignore TIME_WAIT
        probe.bind(("127.0.0.1", API_PORT))
    storage_base = os.environ.get("FIELDLENS_STORAGE_ROOT") or local.get("FIELDLENS_STORAGE_ROOT")
    storage = Path(storage_base) if storage_base else ROOT / ".local/fieldlens/storage"
    if not storage.is_absolute():
        storage = ROOT / storage
    storage = storage / "e2e"
    storage.mkdir(parents=True, exist_ok=True)
    with (
        support.temporary_database(base) as url,
        tempfile.TemporaryDirectory(prefix="control-", dir=storage) as control,
    ):
        support.migrate(url)
        env = (
            os.environ
            | browser_env
            | {
                "FIELDLENS_DATABASE_URL": url.render_as_string(hide_password=False),
                "FIELDLENS_E2E_DATABASE_URL": url.render_as_string(hide_password=False),
                "FIELDLENS_FRONTEND_DIST": str(ROOT / "frontend/dist"),
                "FIELDLENS_STORAGE_ROOT": str(storage),
                "FIELDLENS_E2E_CONTROL_DIR": control,
            }
        )
        api = _start_api(env)
        try:
            _wait_ready(api)
            suite = subprocess.Popen(  # noqa: S603
                [node, str(ROOT / "frontend/node_modules/playwright/cli.js"), "test", *selectors],
                cwd=ROOT / "frontend",
                env=env,
            )
            request, done = Path(control) / "restart.request", Path(control) / "restart.done"
            deadline = time.monotonic() + SUITE_TIMEOUT_S
            try:
                while suite.poll() is None:
                    if time.monotonic() >= deadline:
                        raise subprocess.TimeoutExpired("playwright", SUITE_TIMEOUT_S)
                    if request.exists():
                        request.unlink()
                        _stop_api(api)
                        api = _start_api(env)
                        _wait_ready(api)
                        done.touch()
                    time.sleep(0.05)
            finally:
                if suite.poll() is None:
                    suite.kill()
                    suite.wait()
            return int(suite.returncode)
        finally:
            _stop_api(api)


if __name__ == "__main__":
    raise SystemExit(main())

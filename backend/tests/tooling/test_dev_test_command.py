"""DV-8 ``./dev test`` gates (fakes) and one integration test against the real PostgreSQL."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest

from .test_dev_fakes import REPO, dev, make_world, run_dev

BACKEND = [
    "uv run --frozen pytest backend/tests -q",
    "uv run --frozen ruff check backend scripts",
    "uv run --frozen ruff format --check backend scripts",
    "uv run --frozen mypy backend/fieldlens scripts",
]


def _gates(world, start: int = 0) -> list[str]:  # type: ignore[no-untyped-def]
    return [c for c in world.commands()[start:] if "pytest" in c or "ruff" in c or "mypy" in c]


def test_test_command_backend_gates(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "test", "backend") == 0
    assert _gates(world) == BACKEND
    assert "gates: 4 passed, 0 failed" in world.out
    assert not any("run_e2e" in c or "browser" in c for c in world.commands())


def test_test_command_failure_exits_nonzero_and_summarizes(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.gate_rc = {"ruff check": 1}
    assert run_dev(world, root, "test", "backend") == 1
    assert _gates(world) == BACKEND  # every gate still runs
    assert "gates: 3 passed, 1 failed" in world.out
    assert "failed: ruff check" in world.out


def test_test_command_frontend_gates(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "test", "frontend") == 0
    cmds = world.commands()
    npm = [c for c in cmds if "npm --prefix frontend run" in c and "--outDir" not in c]
    assert [c.rsplit(" ", 1)[1] for c in npm] == ["typecheck", "lint", "test", "check:contracts"]
    assert any("--outDir" in c for c in cmds)  # build gate (atomic)
    assert "gates: 5 passed, 0 failed" in world.out


def test_test_command_e2e_starts_and_removes_only_browser(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    (root / "frontend/dist").mkdir()
    (root / "frontend/dist/index.html").write_text("x")
    world.gate_rc = {"run_e2e": 1}
    assert run_dev(world, root, "test", "e2e") == 1  # failing suite still cleans up
    cmds = world.commands()
    up = next(i for i, c in enumerate(cmds) if c.endswith("up -d --wait browser"))
    run = next(i for i, c in enumerate(cmds) if "scripts/run_e2e.py" in c)
    rm = next(i for i, c in enumerate(cmds) if c.endswith("rm -sf browser"))
    assert up < run < rm
    assert cmds[up] == "docker compose --profile test up -d --wait browser"
    assert cmds[rm] == "docker compose --profile test rm -sf browser"
    assert world.pg_state == "healthy"


def test_test_command_e2e_refuses_occupied_port_and_still_cleans(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    (root / "frontend/dist").mkdir()
    (root / "frontend/dist/index.html").write_text("x")
    world.busy_ports.add(8101)
    assert run_dev(world, root, "test", "e2e") == 1
    assert not any("run_e2e" in c for c in world.commands())


def test_test_command_all_runs_every_group(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "test") == 0
    assert "gates: 10 passed, 0 failed" in world.out


# ------------------------------------------------------------------ real PostgreSQL (optional)


def test_real_postgres_database_lifecycle_through_container() -> None:
    """Create/probe/reset/drop a throw-away database via the real container; never the app DB."""
    services = dev.real_services()
    ctx = dev.build_context(REPO, services)
    compose = dev.Compose(ctx, dev.child_env(services.environ, None))
    if not (ctx.main_root / ".env").is_file() or not compose.daemon_ok():
        pytest.skip("Docker or .env unavailable")
    if compose.postgres_state() != "healthy":
        pytest.skip("fieldlens-postgres is not running")
    name = f"fieldlens_dev_it_{secrets.token_hex(4)}"
    try:
        assert not compose.database_exists(name)
        compose.create_database(name)
        assert compose.database_exists(name)
        assert compose.psql(name, "CREATE TABLE t (i int)").returncode == 0
        compose.reset_schema(name)
        done = compose.psql(name, "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
        assert done.stdout.strip() == "0"
    finally:
        compose.drop_database(name)
    assert not compose.database_exists(name)

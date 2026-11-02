"""DV-4 preflight errors, DV-6 lanes, DV-9 reset-data guards, DV-10 secrets, DV-11 usage (fakes)."""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import pytest

from .test_dev_fakes import (
    REPO,
    SENTINEL_PASSWORD,
    SENTINEL_TOKEN,
    dev,
    env_names,
    make_world,
    run_dev,
)

LANE = "fl-019-x"
LANE_DB = "fieldlens_fl_019_x"


def _no_side_effects(world, root: Path) -> None:  # type: ignore[no-untyped-def]
    assert world.spawns == [] and world.procs == {}
    assert not (root / ".local/run/api.pid").exists()


# ---------------------------------------------------------------------------- DV-4


def test_preflight_errors_missing_env(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, env=False)
    assert run_dev(world, root, "up") == 1
    assert any("uv run python scripts/init_env.py" in line for line in world.err)
    _no_side_effects(world, root)
    assert world.calls == []


def test_preflight_errors_docker_down(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.docker_down = True
    assert run_dev(world, root, "up") == 1
    assert any("Docker daemon is not reachable" in line for line in world.err)
    _no_side_effects(world, root)
    assert not any("compose" in c for c in world.commands())


def test_preflight_errors_foreign_port(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.busy_ports.add(8101)
    assert run_dev(world, root, "up") == 1
    assert any("port 8101" in line and "ss -ltnp" in line for line in world.err)
    _no_side_effects(world, root)
    assert world.signals == []  # a foreign process is never killed


def test_preflight_errors_missing_node(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    for node in root.glob(".local/fieldlens/*/tools/*/bin/node"):
        node.unlink()
    assert run_dev(world, root, "up") == 1
    assert any(
        "Node 24.22.2 not found" in line and "FIELDLENS_NODE_BIN" in line for line in world.err
    )
    _no_side_effects(world, root)


def test_node_discovery_order(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    ctx = dev.build_context(root, _svc(world))
    pinned = next(root.glob(".local/fieldlens/*/tools/*/bin"))
    assert dev.find_node_bin(ctx) == pinned
    other = tmp_path / "explicit"
    other.mkdir()
    (other / "node").write_text("")
    world.environ["FIELDLENS_NODE_BIN"] = str(other)
    assert dev.find_node_bin(ctx) == other


def _svc(world):  # type: ignore[no-untyped-def]
    from .test_dev_fakes import make_services

    return make_services(world)


# ---------------------------------------------------------------------------- DV-6


def test_lane_allocation(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    main_env = (world.main_root / ".env").read_bytes()
    assert run_dev(world, root, "up") == 0
    api_port, vite_port = dev.lane_ports("fl_019_x")
    assert api_port != 8101 and api_port - 8101 == vite_port - 5174 and (api_port - 8101) % 10 == 0
    spawned = world.spawns[0][0]
    assert spawned[spawned.index("--port") + 1] == str(api_port)
    assert LANE_DB in world.dbs and "fieldlens_app" in world.dbs
    assert (root / ".local/run/api.pid").is_file()
    assert not (world.main_root / ".local/run/api.pid").exists()
    assert (world.main_root / ".env").read_bytes() == main_env  # main checkout untouched
    # compose always runs from the main checkout; migrations/API from the lane worktree
    assert any("CREATE DATABASE" in " ".join(c) and LANE_DB in " ".join(c) for c in world.calls)
    out = "\n".join(world.out)
    assert (
        LANE_DB in out and str(root / ".local/run/api.log") in out and "fieldlens_app\n" not in out
    )
    # derived .env: mode 0600, only POSTGRES_/FIELDLENS_ keys, overrides applied
    env_file = root / ".env"
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600
    text = env_file.read_text()
    assert "MODEL_API_KEY" not in text and "TELEGRAM" not in text
    values = dev.load_local_env(env_file)
    assert values["POSTGRES_DB"] == LANE_DB
    assert values["FIELDLENS_DATABASE_URL"].endswith(f"/{LANE_DB}")
    assert values["FIELDLENS_STORAGE_ROOT"] == str(root / ".local/fieldlens/storage-fl_019_x")
    assert values["POSTGRES_PASSWORD"] == SENTINEL_PASSWORD
    # re-running is idempotent for the derived file
    before = env_file.read_bytes()
    run_dev(world, root, "down")
    assert run_dev(world, root, "up") == 0
    assert env_file.read_bytes() == before


def test_lane_rejects_reserved_names_and_foreign_env(tmp_path: Path) -> None:
    for name in ("app", "app-test-1234abcd", "---"):
        with pytest.raises(dev.DevError):
            dev.make_lane(tmp_path, name)
    world, root = make_world(tmp_path, lane=LANE)
    (root / ".env").write_text("A=1\n")
    assert run_dev(world, root, "up") == 1
    assert (root / ".env").read_text() == "A=1\n"
    assert any("never overwritten" in line for line in world.err)


def test_lane_drop_requires_typed_confirmation(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    assert run_dev(world, root, "up") == 0
    storage = root / ".local/fieldlens/storage-fl_019_x"
    storage.mkdir(parents=True)
    (storage / "blob").write_text("x")
    world.answers = ["fieldlens_app"]
    assert run_dev(world, root, "down", "--drop-lane") == 1
    assert LANE_DB in world.dbs and storage.exists()
    world.answers = [LANE_DB]
    assert run_dev(world, root, "down", "--drop-lane") == 0
    assert LANE_DB not in world.dbs and "fieldlens_app" in world.dbs
    assert not storage.exists()
    assert world.main_root.joinpath(".env").exists()
    assert not any("DROP DATABASE" in c and 'fieldlens_app"' in c for c in world.commands())


def test_drop_lane_refused_in_main_checkout(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "down", "--drop-lane") == 1
    assert "fieldlens_app" in world.dbs


# ---------------------------------------------------------------------------- DV-9


def test_reset_data_guards(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.pg_state = "healthy"
    # typed confirmation mismatch: nothing happens
    world.answers = ["nope"]
    assert run_dev(world, root, "reset-data") == 1
    assert not any("DROP SCHEMA" in c for c in world.commands())
    # API running: refused without --force
    assert run_dev(world, root, "up") == 0
    assert run_dev(world, root, "reset-data") == 1
    assert any("API is running" in line for line in world.err)
    assert not any("DROP SCHEMA" in c for c in world.commands())
    # --force stops the API, drops/recreates schema public, re-runs migrations
    world.answers = ["fieldlens_app"]
    world.out.clear()
    assert run_dev(world, root, "reset-data", "--force") == 0
    cmds = world.commands()
    drop = next(i for i, c in enumerate(cmds) if "DROP SCHEMA IF EXISTS public CASCADE" in c)
    assert any("upgrade head" in c for c in cmds[drop:])
    assert world.procs == {}
    assert any(line.startswith("deleted:") for line in world.out)
    assert not [c for c in cmds if c.startswith(("docker compose down", "docker compose rm"))]


@pytest.mark.parametrize(
    ("target", "configured"),
    [
        ("fieldlens_app_test_0123abcd", "fieldlens_app_test_0123abcd"),
        ("fieldlens_other", "fieldlens_app"),
        ("postgres", "postgres"),
        ("fieldlens_app", "fieldlens_x"),
        ('fieldlens_app"; drop', 'fieldlens_app"; drop'),
        (None, "fieldlens_app"),
    ],
)
def test_reset_data_refuses_other_databases(target: str | None, configured: str) -> None:
    with pytest.raises(dev.DevError):
        dev.check_reset_target(target, configured)
    assert dev.check_reset_target("fieldlens_app", "fieldlens_app") == "fieldlens_app"


def test_reset_data_refuses_url_pointing_elsewhere(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.pg_state = "healthy"
    env = (
        (root / ".env")
        .read_text()
        .replace("55432/fieldlens_app", "55432/fieldlens_app_test_0123abcd")
    )
    (root / ".env").write_text(env)
    world.answers = ["fieldlens_app_test_0123abcd"]
    assert run_dev(world, root, "reset-data") == 1
    assert not any("DROP SCHEMA" in c for c in world.commands())


def test_reset_data_in_lane_never_targets_main_db(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    world.pg_state = "healthy"
    # no derived lane .env yet: the main URL would be used -> refused
    world.answers = ["fieldlens_app"]
    assert run_dev(world, root, "reset-data") == 1
    assert not any("DROP SCHEMA" in c for c in world.commands())


# ---------------------------------------------------------------------------- DV-10


def test_no_secrets_in_output(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    for argv in (("up", "--dev"), ("status",), ("env-check",), ("down",), ("down", "--db")):
        run_dev(world, root, *argv)
    secrets = (SENTINEL_PASSWORD, SENTINEL_TOKEN, "sk-SENTINEL")
    haystack = "\n".join(world.out + world.err + world.commands() + world.prompts)
    for secret in secrets:
        assert secret not in haystack
    for path in (root / ".local/run").glob("*.log"):
        for secret in secrets:
            assert secret not in path.read_text()
    # children get only the environment they need
    assert not {"MODEL_API_KEY", "TELEGRAM_BOT_TOKEN"} & env_names(world)
    for _, env in world.spawns:
        assert "PATH" in env and not any(SENTINEL_TOKEN in v for v in env.values())
    status = [line for line in world.out if line.startswith(".env:")]
    assert status and all("set" in line or "missing" in line for line in status)


def test_status_shows_presence_only(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "status") == 0
    line = next(line for line in world.out if line.startswith(".env:"))
    assert "POSTGRES_PASSWORD=set" in line and SENTINEL_PASSWORD not in line


def test_status_and_restart_warn_about_unmanaged_api_connections(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.pg_state = "healthy"
    world.activity = ["fieldlens:main:777|3", "|2"]
    assert run_dev(world, root, "status") == 0
    text = "\n".join(world.out)
    assert "not managed by this lane" in text
    assert "fieldlens:main:777 x3" in text and "unidentified client" in text
    assert run_dev(world, root, "restart") in (0, 1)
    assert sum("not managed by this lane" in line for line in world.out) >= 2
    assert world.signals == [], "other processes are never signalled"
    quiet, qroot = make_world(tmp_path / "q")
    assert run_dev(quiet, qroot, "status") == 0
    assert not any("not managed" in line for line in quiet.out)


def test_status_excludes_own_api_child_but_warns_for_foreign(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up") == 0
    wrapper = next(pid for pid, argv in world.procs.items() if "uvicorn" in argv or "uv" in argv)
    world.children[wrapper] = [wrapper + 1000]
    world.pg_state = "healthy"
    world.activity = [f"fieldlens:main:{wrapper + 1000}|4", "fieldlens:main:12345|1"]
    world.out.clear()
    assert run_dev(world, root, "status") == 0
    text = "\n".join(world.out)
    assert f"{wrapper + 1000}" not in text
    assert "fieldlens:main:12345 x1" in text
    world.activity = [f"fieldlens:main:{wrapper + 1000}|4"]
    world.out.clear()
    assert run_dev(world, root, "status") == 0
    assert "not managed by this lane" not in "\n".join(world.out)


# ---------------------------------------------------------------------------- DV-11


def test_cli_usage(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root) == 0
    text = "\n".join(world.out)
    for word in ("up", "down", "restart", "status", "logs", "test", "reset-data", "env-check"):
        assert word in text
    assert world.calls == []


def test_shim_prints_usage_from_subdirectory_under_set_u() -> None:
    shim = REPO / "dev"
    assert shim.is_file() and shim.stat().st_mode & 0o111
    done = subprocess.run(  # noqa: S603
        ["/usr/bin/env", "bash", "-u", str(shim)],
        cwd=REPO / "backend",
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "usage: ./dev" in done.stdout and "env-check" in done.stdout


def test_logs_command(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "logs") == 1  # no log yet, actionable
    assert run_dev(world, root, "up") == 0
    world.out.clear()
    assert run_dev(world, root, "logs", "api") == 0
    assert world.out == ["started"]
    services = _svc(world)

    class Stop:
        def monotonic(self) -> float:
            return 0.0

        def sleep(self, seconds: float) -> None:
            (root / ".local/run/api.log").write_text("rotated\n")
            raise KeyboardInterrupt

    services.clock = Stop()
    world.out.clear()
    assert dev.main(["logs", "-f"], services, root) == 0
    assert world.out == ["started"]
    _ = json

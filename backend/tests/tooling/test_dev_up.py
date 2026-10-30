"""DV-1/DV-2/DV-3/DV-5/DV-7: up sequence, idempotency, down scope, staleness, stale state (fakes)."""

from __future__ import annotations

import json
import signal
from pathlib import Path

from .test_dev_fakes import dev, make_world, run_dev


def _index(commands: list[str], needle: str) -> int:
    return next(i for i, c in enumerate(commands) if needle in c)


def test_up_sequence(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up") == 0
    cmds = world.commands()
    order = [
        _index(cmds, "docker info"),
        _index(cmds, "docker compose up -d --wait postgres"),
        _index(cmds, "alembic -c backend/alembic.ini upgrade head"),
        _index(cmds, "--outDir"),
        _index(cmds, "SPAWN uv run --frozen uvicorn fieldlens.app:create_app --factory"),
    ]
    assert order == sorted(order) and len(set(order)) == len(order)
    text = "\n".join(world.out)
    assert "http://127.0.0.1:8101/" in text
    assert "fieldlens_app" in text and "0.9.0" in text and "0003_example" in text
    assert str(root / ".local/run/api.log") in text
    assert (root / "frontend/dist/index.html").is_file()
    assert (root / ".local/run/api.pid").is_file()
    argv, _ = world.spawns[0]
    assert "--host" in argv and argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--port") + 1] == "8101"


def test_up_idempotent(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up") == 0
    calls_before, spawns_before, signals_before = (
        len(world.calls),
        len(world.spawns),
        world.signals[:],
    )
    world.out.clear()
    assert run_dev(world, root, "up") == 0
    assert len(world.spawns) == spawns_before and world.signals == signals_before
    new = world.commands()[calls_before:]
    assert not any(
        "--outDir" in c or "compose" in c or "upgrade" in c or "sync" in c for c in new
    ), new
    assert any("already running" in line and "nothing changed" in line for line in world.out)


def test_up_second_run_builds_nothing_when_sources_unchanged(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up") == 0
    world.procs.clear()  # API gone, state unchanged: restart without rebuilding
    (root / ".local/run/api.pid").unlink()
    builds = sum("--outDir" in c for c in world.commands())
    assert run_dev(world, root, "up") == 0
    assert sum("--outDir" in c for c in world.commands()) == builds == 1


def test_up_dev_starts_vite_and_second_up_keeps_it(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up", "--dev") == 0
    assert (root / ".local/run/vite.pid").is_file()
    vite_argv = world.spawns[1][0]
    assert "5174" in vite_argv and "--strictPort" in vite_argv
    n = len(world.spawns)
    assert run_dev(world, root, "up", "--dev") == 0
    assert len(world.spawns) == n


def test_down_scope(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up", "--dev") == 0
    api_pid = json.loads((root / ".local/run/api.pid").read_text())["pid"]
    calls_before = len(world.calls)
    assert run_dev(world, root, "down") == 0
    assert not (root / ".local/run/api.pid").exists()
    assert not (root / ".local/run/vite.pid").exists()
    assert world.procs == {}
    assert (api_pid, signal.SIGTERM) in world.signals
    assert world.calls[calls_before:] == []  # postgres untouched
    assert world.pg_state == "healthy"
    assert run_dev(world, root, "down", "--db") == 0
    assert world.pg_state == "exited"
    for command in world.commands():
        assert " down" not in command and " -v" not in command
        assert "rm " not in command or "--profile test rm -sf browser" in command
    stop = [c for c in world.commands() if "compose stop" in c]
    assert stop == ["docker compose stop postgres"]


def test_down_never_signals_a_reused_pid(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    run_dir = root / ".local/run"
    run_dir.mkdir(parents=True)
    world.procs[777] = ["vim", "notes.txt"]
    (run_dir / "api.pid").write_text(json.dumps({"pid": 777}), encoding="utf-8")
    assert run_dev(world, root, "down") == 0
    assert world.signals == [] and 777 in world.procs
    assert not (run_dir / "api.pid").exists()
    assert any("stale pid file removed" in line for line in world.out)


def test_stale_state(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    run_dir = root / ".local/run"
    run_dir.mkdir(parents=True)
    # dead pid and garbage pid file are both classified as stale and removed by status
    (run_dir / "api.pid").write_text(json.dumps({"pid": 99999}), encoding="utf-8")
    (run_dir / "vite.pid").write_text("not json", encoding="utf-8")
    assert run_dev(world, root, "status") == 0
    assert not (run_dir / "api.pid").exists() and not (run_dir / "vite.pid").exists()
    assert sum("removed stale pid file" in line for line in world.out) == 2
    # killed script mid-up: pid file present, process gone; up continues and starts cleanly
    (run_dir / "api.pid").write_text(json.dumps({"pid": 4242}), encoding="utf-8")
    assert run_dev(world, root, "up") == 0
    assert len(world.spawns) == 1 and any("removed stale api.pid" in line for line in world.out)
    # crashed API: process alive but not ready -> restarted, not left half-alive
    world.api_ready = False
    spawns = len(world.spawns)
    assert run_dev(world, root, "up") == 1  # still never ready: failure reported, api stopped
    assert len(world.spawns) == spawns + 1
    assert world.procs == {}
    assert not (run_dir / "api.pid").exists()


def test_api_exits_during_startup_is_reported(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.api_dies = True
    assert run_dev(world, root, "up") == 1
    assert any("exited during startup" in line for line in world.err)
    assert any(str(root / ".local/run/api.log") in line for line in world.err)
    assert world.pg_state == "healthy"  # postgres left running
    assert not (root / ".local/run/api.pid").exists()


def test_build_staleness(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up") == 0
    builds = lambda: sum("--outDir" in c for c in world.commands())  # noqa: E731
    assert builds() == 1
    ctx = dev.build_context(root, _services(world))
    frontend = dev.Frontend(ctx)
    assert not frontend.stale()
    hash_file = root / ".local/run/frontend-build.hash"
    assert hash_file.read_text().strip() == frontend.digest()

    def restart() -> int:
        run_dev(world, root, "down")
        return run_dev(world, root, "up")

    assert restart() == 0 and builds() == 1  # unchanged -> no rebuild
    (root / "frontend/src/main.tsx").write_text("// changed\n", encoding="utf-8")
    assert frontend.stale()
    assert restart() == 0 and builds() == 2
    (root / "VERSION").write_text("0.9.1\n", encoding="utf-8")  # VERSION is a build input
    assert frontend.stale()
    assert restart() == 0 and builds() == 3
    (root / "frontend/package-lock.json").write_text("changed", encoding="utf-8")
    assert frontend.stale()


def test_build_failure_keeps_previous_dist(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    assert run_dev(world, root, "up") == 0
    run_dev(world, root, "down")
    dist = root / "frontend/dist/index.html"
    good = dist.read_text()
    old_hash = (root / ".local/run/frontend-build.hash").read_text()
    (root / "frontend/src/main.tsx").write_text("// broken\n", encoding="utf-8")
    world.build_fails = True
    spawns = len(world.spawns)
    assert run_dev(world, root, "up") == 1
    assert dist.read_text() == good
    assert (root / ".local/run/frontend-build.hash").read_text() == old_hash
    assert not (root / ".local/run/dist-build").exists()
    assert len(world.spawns) == spawns  # no API with a broken build
    assert any("previous dist kept" in line for line in world.err)


def test_missing_node_modules_suggests_ci(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    (root / "frontend/node_modules/vite/bin/vite.js").unlink()
    assert run_dev(world, root, "up") == 1
    assert any("npm --prefix frontend ci" in line for line in world.err)
    assert world.spawns == [] and not any("compose" in c for c in world.commands())


def test_interrupt_stops_only_started_children(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    services = _services(world)

    def interrupt(url: str) -> int | None:
        raise KeyboardInterrupt

    services.http = type("H", (), {"status": staticmethod(interrupt)})()
    assert dev.main(["up"], services, root) == 130
    assert world.procs == {} and world.pg_state == "healthy"
    assert not (root / ".local/run/api.pid").exists()


def _services(world):  # type: ignore[no-untyped-def]
    from .test_dev_fakes import make_services

    return make_services(world)


def test_log_rotation_truncates(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    run_dir = root / ".local/run"
    run_dir.mkdir(parents=True)
    (run_dir / "api.log").write_bytes(b"x" * (dev.LOG_MAX_BYTES + 1))
    assert run_dev(world, root, "up") == 0
    assert (run_dir / "api.log").stat().st_size < 100

"""FL-019-A repair: lane hosts/origins, operation lock, EOF prompts, env allowlist, holders."""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
from pathlib import Path

from .test_dev_fakes import REPO, dev, make_world, run_dev

LANE = "fl-019-x"
LANE_DB = "fieldlens_fl_019_x"


def test_lane_child_env_and_env_file_carry_offset_hosts_and_origins(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    # an inherited main-checkout value must not leak into the lane API
    world.environ["FIELDLENS_ALLOWED_HOSTS"] = '["127.0.0.1:8101"]'
    assert run_dev(world, root, "up") == 0
    api, vite = dev.lane_ports("fl_019_x")
    hosts = [f"{h}:{p}" for p in (api, vite) for h in ("127.0.0.1", "localhost")]
    spawn_env = world.spawns[0][1]
    assert json.loads(spawn_env["FIELDLENS_ALLOWED_HOSTS"]) == hosts
    assert json.loads(spawn_env["FIELDLENS_ALLOWED_ORIGINS"]) == [f"http://{h}" for h in hosts]
    assert spawn_env["FIELDLENS_PORT"] == str(api)
    values = dev.load_local_env(root / ".env")
    assert json.loads(values["FIELDLENS_ALLOWED_HOSTS"]) == hosts
    assert json.loads(values["FIELDLENS_ALLOWED_ORIGINS"]) == [f"http://{h}" for h in hosts]


def test_lane_env_copies_only_allowlisted_keys(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    main_env = world.main_root / ".env"
    main_env.write_text(
        main_env.read_text() + "FIELDLENS_JOB_STAGE_DELAY_S=5\nFIELDLENS_PW_EXPOSE_NETWORK=1\n"
    )
    assert run_dev(world, root, "up") == 0
    keys = set(dev.load_local_env(root / ".env"))
    assert keys <= dev.LANE_ENV_COPY | {
        "POSTGRES_DB",
        "FIELDLENS_DATABASE_URL",
        "FIELDLENS_STORAGE_ROOT",
        "FIELDLENS_PORT",
        "FIELDLENS_ALLOWED_HOSTS",
        "FIELDLENS_ALLOWED_ORIGINS",
    }
    assert "FIELDLENS_JOB_STAGE_DELAY_S" not in keys and "FIELDLENS_PW_EXPOSE_NETWORK" not in keys


def test_failed_lane_up_prints_drop_lane_cleanup(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    world.build_fails = True
    (root / "frontend/src/main.tsx").write_text("// changed\n")
    assert run_dev(world, root, "up") == 1
    assert LANE_DB in world.dbs  # kept, documented
    assert any("down --drop-lane" in line and LANE_DB in line for line in world.err)


def test_dead_child_with_foreign_listener_fails_up(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    world.api_dies = True
    api_port = dev.BASE_API_PORT
    # a foreign process answers 200 on the port while our child died at bind
    world.procs[1] = ["python", "--port", str(api_port), "uvicorn"]
    ctx = dev.build_context(root, _svc(world))
    api = dev.api_process(ctx)
    try:
        dev._start_api(ctx, api, {})
    except dev.DevError as exc:
        assert "exited during startup" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("up must fail when the recorded pid is dead")


def _svc(world):  # type: ignore[no-untyped-def]
    from .test_dev_fakes import make_services

    return make_services(world)


def test_eof_on_confirmation_is_one_line_error(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    assert run_dev(world, root, "up") == 0
    run_dev(world, root, "down")
    services = _svc(world)

    def eof(_: str) -> str:
        raise EOFError

    services.prompt = eof
    for argv in (("down", "--drop-lane"), ("reset-data",)):
        world.err.clear()
        assert int(dev.main(list(argv), services, root)) == 1
        assert len(world.err) == 1 and world.err[0].startswith("dev: ")
        assert LANE_DB in world.dbs


def test_second_operation_is_refused_while_lock_held(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    run_dir = root / ".local/run"
    run_dir.mkdir(parents=True)
    fd = os.open(run_dir / "up.lock", os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        for cmd in ("up", "down", "restart", "reset-data"):
            world.err.clear()
            assert run_dev(world, root, cmd) == 1
            assert world.err == ["dev: another ./dev operation is running"]
        assert world.spawns == [] and world.dbs == {"fieldlens_app"}
        assert run_dev(world, root, "status") == 0  # read-only commands are not locked
    finally:
        os.close(fd)
    assert run_dev(world, root, "up") == 0  # released


def test_real_flock_across_processes(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    code = (
        "import fcntl,os,sys,time;"
        "p=sys.argv[1];os.makedirs(os.path.dirname(p),exist_ok=True);"
        "fd=os.open(p,os.O_RDWR|os.O_CREAT,0o600);fcntl.flock(fd,fcntl.LOCK_EX);"
        "print('held',flush=True);time.sleep(30)"
    )
    holder = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", code, str(root / ".local/run/up.lock")],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout is not None and holder.stdout.readline().strip() == "held"
        assert run_dev(world, root, "up") == 1
        assert world.err == ["dev: another ./dev operation is running"]
    finally:
        holder.kill()
        holder.wait()
    world.err.clear()
    assert run_dev(world, root, "up") == 0


def test_frontend_hash_covers_extra_inputs(tmp_path: Path) -> None:
    world, root = make_world(tmp_path)
    ctx = dev.build_context(root, _svc(world))
    frontend = dev.Frontend(ctx)
    for rel in (".npmrc", "eslint.config.js", "scripts/gen.mjs"):
        path = root / "frontend" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a")
        before = frontend.digest()
        path.write_text("b")
        assert frontend.digest() != before, rel


def test_port_collision_names_the_holder(tmp_path: Path) -> None:
    world, root = make_world(tmp_path, lane=LANE)
    api, _ = dev.lane_ports("fl_019_x")
    other = tmp_path / "other-lane"
    (other / ".local/run").mkdir(parents=True)
    world.procs[777] = ["x", "--port", str(api)]
    (other / ".local/run/api.pid").write_text(json.dumps({"pid": 777, "port": api}))
    ctx = dev.build_context(root, _svc(world))
    ctx.services.runner.run = lambda argv, **kw: dev.Result(  # type: ignore[method-assign]
        0, f"worktree {other}\n"
    )
    try:
        dev._preflight_port(ctx, api, "api")
    except dev.DevError as exc:
        assert str(other) in str(exc) and "pid 777" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected a collision")
    assert REPO.exists()

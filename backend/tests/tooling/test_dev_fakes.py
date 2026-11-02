"""Fakes for the ``scripts/dev.py`` tests: no real Docker, processes, ports or HTTP."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

REPO = Path(__file__).resolve().parents[3]
SENTINEL_PASSWORD = "pw-SENTINEL-4f9c1d7a"
SENTINEL_TOKEN = "123456789:SENTINEL-tg-token"


def load_dev() -> ModuleType:
    name = "fieldlens_dev_script"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / "dev.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses resolve string annotations through sys.modules
    spec.loader.exec_module(module)
    return module


dev = load_dev()


@dataclass
class World:
    """The simulated host. Tests inspect ``calls``, ``procs``, ``dbs`` and ``out``."""

    root: Path
    main_root: Path
    pg_state: str = "exited"
    docker_down: bool = False
    dbs: set[str] = field(default_factory=lambda: {"fieldlens_app"})
    busy_ports: set[int] = field(default_factory=set)
    activity: list[str] = field(default_factory=list)
    children: dict[int, list[int]] = field(default_factory=dict)
    procs: dict[int, list[str]] = field(default_factory=dict)
    calls: list[list[str]] = field(default_factory=list)
    spawns: list[tuple[list[str], dict[str, str]]] = field(default_factory=list)
    envs: list[Mapping[str, str] | None] = field(default_factory=list)
    signals: list[tuple[int, int]] = field(default_factory=list)
    out: list[str] = field(default_factory=list)
    err: list[str] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)
    prompts: list[str] = field(default_factory=list)
    build_fails: bool = False
    gate_rc: dict[str, int] = field(default_factory=dict)
    api_ready: bool = True
    api_dies: bool = False
    ignore_term: bool = False
    now: float = 0.0
    next_pid: int = 4000
    environ: dict[str, str] = field(default_factory=dict)

    def commands(self) -> list[str]:
        return [" ".join(c) for c in self.calls]


class FakeRunner:
    def __init__(self, world: World) -> None:
        self.w = world

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> object:
        w = self.w
        args = list(argv)
        w.calls.append(args)
        w.envs.append(env)
        result = dev.Result
        text = " ".join(args)
        if args[:2] == ["docker", "info"]:
            return result(1 if w.docker_down else 0)
        if args[:2] == ["docker", "inspect"]:
            return result(0, w.pg_state + "\n") if w.pg_state != "absent" else result(1)
        if text.startswith("docker compose up -d --wait postgres"):
            w.pg_state = "healthy"
            return result(0)
        if text.startswith("docker compose stop postgres"):
            w.pg_state = "exited"
            return result(0)
        if args[:3] == ["docker", "compose", "exec"]:
            return self._psql(args[-2], args[-1])
        if args[:2] == ["git", "rev-parse"]:
            return result(0, str(w.main_root / ".git") + "\n")
        if args[-1:] == ["--version"]:
            return result(0, "v24.22.2\n")
        if "alembic" in args and "heads" in args:
            return result(0, "0003_example (head)\n")
        if "--outDir" in args:
            if w.build_fails:
                return result(1, "", "boom")
            out = Path(args[args.index("--outDir") + 1])
            out.mkdir(parents=True, exist_ok=True)
            (out / "index.html").write_text(f"built {w.now}", encoding="utf-8")
            return result(0)
        for key, rc in w.gate_rc.items():
            if key in text:
                return result(rc)
        return result(0)

    def _psql(self, db: str, sql: str) -> object:
        w, result = self.w, dev.Result
        if sql.startswith("SELECT 1 FROM pg_database"):
            name = sql.split("'")[1]
            return result(0, "1\n" if name in w.dbs else "")
        if "pg_stat_activity" in sql:
            return result(0, "".join(line + "\n" for line in w.activity))
        if sql.startswith("CREATE DATABASE"):
            w.dbs.add(sql.split('"')[1])
        elif sql.startswith("DROP DATABASE"):
            w.dbs.discard(sql.split('"')[1])
        return result(0)

    def spawn(self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], log: Path) -> int:
        w = self.w
        w.next_pid += 1
        args = list(argv)
        w.spawns.append((args, dict(env)))
        w.calls.append(["SPAWN", *args])
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("started\n", encoding="utf-8")
        if not (w.api_dies and "uvicorn" in args):
            w.procs[w.next_pid] = args
        return w.next_pid


class FakeClock:
    def __init__(self, world: World) -> None:
        self.w = world

    def monotonic(self) -> float:
        return self.w.now

    def sleep(self, seconds: float) -> None:
        self.w.now += seconds


class FakePorts:
    def __init__(self, world: World) -> None:
        self.w = world

    def is_free(self, port: int) -> bool:
        if port in self.w.busy_ports:
            return False
        return not any(
            "--port" in cmd and cmd[cmd.index("--port") + 1] == str(port)
            for cmd in self.w.procs.values()
        )


class FakeProcs:
    def __init__(self, world: World) -> None:
        self.w = world

    def cmdline(self, pid: int) -> list[str] | None:
        return self.w.procs.get(pid)

    def descendants(self, pid: int) -> set[int]:
        found: set[int] = set()
        todo = [pid]
        while todo:
            for child in self.w.children.get(todo.pop(), []):
                if child not in found:
                    found.add(child)
                    todo.append(child)
        return found

    def signal_group(self, pid: int, sig: int) -> None:
        self.w.signals.append((pid, sig))
        if sig == 9 or not self.w.ignore_term:
            self.w.procs.pop(pid, None)


class FakeHttp:
    def __init__(self, world: World) -> None:
        self.w = world

    def status(self, url: str) -> int | None:
        port = url.split(":")[2].split("/")[0]
        for cmd in self.w.procs.values():
            if "--port" in cmd and cmd[cmd.index("--port") + 1] == port:
                if "uvicorn" in cmd:
                    return 200 if self.w.api_ready else 503
                return 200
        return None


ENV_TEXT = (
    f"POSTGRES_USER=fieldlens\nPOSTGRES_PASSWORD={SENTINEL_PASSWORD}\nPOSTGRES_DB=fieldlens_app\n"
    "FIELDLENS_DB_PORT=55432\n"
    f"FIELDLENS_DATABASE_URL=postgresql+psycopg://fieldlens:{SENTINEL_PASSWORD}"
    "@127.0.0.1:55432/fieldlens_app\n"
    "FIELDLENS_STORAGE_ROOT=.local/fieldlens/storage\n"
    "MODEL_API_KEY=sk-SENTINEL-model\n"
    f"TELEGRAM_BOT_TOKEN={SENTINEL_TOKEN}\n"
)


def make_checkout(root: Path, *, git_file: bool = False, env: bool = True) -> None:
    (root / "frontend/src").mkdir(parents=True)
    (root / "frontend/src/main.tsx").write_text("// app\n", encoding="utf-8")
    (root / "frontend/node_modules/vite/bin").mkdir(parents=True)
    (root / "frontend/node_modules/vite/bin/vite.js").write_text("", encoding="utf-8")
    for name in ("index.html", "package.json", "package-lock.json", "vite.config.ts"):
        (root / "frontend" / name).write_text(name, encoding="utf-8")
    for name, text in (
        ("VERSION", "0.9.0\n"),
        (".node-version", "24.22.2\n"),
        ("uv.lock", "lock"),
        ("pyproject.toml", "[project]\n"),
    ):
        (root / name).write_text(text, encoding="utf-8")
    node = root / ".local/fieldlens/x/tools/node-v24.22.2-linux-x64/bin"
    node.mkdir(parents=True)
    (node / "node").write_text("", encoding="utf-8")
    (node / "npm").write_text("", encoding="utf-8")
    if git_file:
        (root / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
    else:
        (root / ".git").mkdir()
    if env:
        path = root / ".env"
        path.write_text(ENV_TEXT, encoding="utf-8")
        path.chmod(0o600)


def make_world(tmp_path: Path, *, lane: str | None = None, env: bool = True) -> tuple[World, Path]:
    """A main checkout, or a linked-worktree lane named after ``lane``. Returns (world, root)."""
    main = tmp_path / "main"
    make_checkout(main, env=env)
    root = main
    if lane:
        root = tmp_path / lane
        make_checkout(root, git_file=True, env=False)
    world = World(root=root, main_root=main)
    world.environ = {
        "PATH": "/usr/bin",
        "HOME": str(tmp_path),
        "MODEL_API_KEY": "sk-SENTINEL-env",
        "TELEGRAM_BOT_TOKEN": SENTINEL_TOKEN,
    }
    return world, root


def make_services(world: World) -> object:
    return dev.Services(
        runner=FakeRunner(world),
        clock=FakeClock(world),
        ports=FakePorts(world),
        procs=FakeProcs(world),
        http=FakeHttp(world),
        out=world.out.append,
        err=world.err.append,
        prompt=lambda text: (world.prompts.append(text), world.answers.pop(0))[1],
        environ=world.environ,
        which=lambda name: None,
        load_env=lambda path: dev.load_local_env(path),
    )


def run_dev(world: World, root: Path, *argv: str) -> int:
    return int(dev.main(list(argv), make_services(world), root))


def env_names(world: World) -> set[str]:
    names: set[str] = set()
    for env in world.envs:
        if env:
            names |= set(env)
    return names

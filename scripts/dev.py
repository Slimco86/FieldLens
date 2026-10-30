"""One-command local stack: ``./dev up|down|restart|status|logs|test|reset-data|env-check``.

Spec: docs/specs/DEV_TOOLING.md. Standard library plus the repository's existing dependencies.
Every side effect goes through an injected service (subprocess runner, clock, port probe,
/proc reader, HTTP getter, prompt) so the unit tests use fakes. Secret values (database
password, ``DATABASE_URL``, tokens) are never printed, logged or placed on a command line.

What ``./dev up`` automates (the manual equivalent):
``uv run python scripts/init_env.py``; ``docker compose up -d --wait postgres``;
``uv run alembic -c backend/alembic.ini upgrade head``; ``npm --prefix frontend run build``;
``uv run uvicorn fieldlens.app:create_app --factory --host 127.0.0.1 --port 8101``.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldlens.localenv import load_local_env  # noqa: E402

BASE_API_PORT = 8101
BASE_VITE_PORT = 5174
READY_PATH = "/api/v1/ready"
READY_TIMEOUT_S = 60.0
VITE_TIMEOUT_S = 30.0
STOP_GRACE_S = 10.0
LOG_MAX_BYTES = 5 * 1024 * 1024
POSTGRES_CONTAINER = "fieldlens-postgres"
DB_NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
TEST_DB_PREFIX = "fieldlens_app_test_"
REQUIRED_KEYS = ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB")
LANE_ENV_MARKER = "# derived by scripts/dev.py for this linked worktree; do not edit\n"
INIT_ENV_FIX = "uv run python scripts/init_env.py"
NODE_FIX = (
    "set FIELDLENS_NODE_BIN to the bin directory of Node {version}, or install it "
    "(README 'Run the foundation locally')"
)
# Environment names that children may inherit (no tokens, no provider keys).
ENV_ALLOW = re.compile(
    r"^(PATH|HOME|USER|LOGNAME|LANG|LC_.*|TERM|TMPDIR|SHELL|XDG_.*|UV_.*|DOCKER_.*|COMPOSE_.*|"
    r"SSL_CERT_.*|NO_PROXY|no_proxy|CI|FIELDLENS_.*|POSTGRES_.*|PG(HOST|PORT|USER|DATABASE)?)$"
)


class DevError(Exception):
    """One actionable message; the CLI prints it and exits with ``code``."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


# --------------------------------------------------------------------------- injected services


@dataclass(frozen=True)
class Result:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class Runner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> Result: ...

    def spawn(
        self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], log: Path
    ) -> int: ...


class Clock(Protocol):
    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...


class Ports(Protocol):
    def is_free(self, port: int) -> bool: ...


class Procs(Protocol):
    def cmdline(self, pid: int) -> list[str] | None: ...

    def signal_group(self, pid: int, sig: int) -> None: ...


class Http(Protocol):
    def status(self, url: str) -> int | None: ...


class RealRunner:
    def __init__(self) -> None:
        self._children: list[subprocess.Popen[bytes]] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
        capture: bool = True,
    ) -> Result:
        try:
            done = subprocess.run(  # noqa: S603
                list(argv),
                cwd=cwd,
                env=None if env is None else dict(env),
                capture_output=capture,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except FileNotFoundError as exc:
            return Result(127, "", f"{exc.filename or argv[0]}: not found")
        except PermissionError as exc:
            return Result(126, "", f"{exc.filename or argv[0]}: permission denied")
        except subprocess.TimeoutExpired:
            return Result(124, "", "timed out")
        return Result(done.returncode, done.stdout or "", done.stderr or "")

    def spawn(self, argv: Sequence[str], *, cwd: Path, env: Mapping[str, str], log: Path) -> int:
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            child = subprocess.Popen(  # noqa: S603
                list(argv),
                cwd=cwd,
                env=dict(env),
                stdin=subprocess.DEVNULL,
                stdout=fd,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )
        finally:
            os.close(fd)
        self._children.append(child)
        return child.pid


class RealClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class RealPorts:
    def is_free(self, port: int) -> bool:
        with socket.socket() as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # like uvicorn
            try:
                probe.bind(("127.0.0.1", port))
            except OSError:
                return False
        return True


class RealProcs:
    def cmdline(self, pid: int) -> list[str] | None:
        try:
            raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        except OSError:
            return None
        return [part.decode("utf-8", "replace") for part in raw.split(b"\0") if part]

    def signal_group(self, pid: int, sig: int) -> None:
        try:
            if os.getpgid(pid) == pid:  # started in its own session by spawn()
                os.killpg(pid, sig)
            else:
                os.kill(pid, sig)
        except ProcessLookupError:
            pass


class RealHttp:
    def __init__(self) -> None:
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def status(self, url: str) -> int | None:
        try:
            with self._opener.open(url, timeout=2) as response:  # noqa: S310
                return int(response.status)
        except urllib.error.HTTPError as exc:
            return int(exc.code)
        except (urllib.error.URLError, OSError, ValueError):
            return None


@dataclass
class Services:
    runner: Runner
    clock: Clock
    ports: Ports
    procs: Procs
    http: Http
    out: Callable[[str], None]
    err: Callable[[str], None]
    prompt: Callable[[str], str]
    environ: Mapping[str, str]
    which: Callable[[str], str | None]
    load_env: Callable[[Path], dict[str, str]]


def real_services() -> Services:
    return Services(
        runner=RealRunner(),
        clock=RealClock(),
        ports=RealPorts(),
        procs=RealProcs(),
        http=RealHttp(),
        out=lambda text: print(text, flush=True),
        err=lambda text: print(text, file=sys.stderr, flush=True),
        prompt=input,
        environ=os.environ,
        which=shutil.which,
        load_env=lambda path: load_local_env(path),
    )


# --------------------------------------------------------------------------------- lane/context


@dataclass(frozen=True)
class Lane:
    name: str
    database: str
    api_port: int
    vite_port: int
    storage: Path


def lane_ports(name: str) -> tuple[int, int]:
    offset = (zlib.crc32(name.encode()) % 20) * 10
    offset = offset or 200  # never the main checkout's base ports
    return BASE_API_PORT + offset, BASE_VITE_PORT + offset


def make_lane(root: Path, directory_name: str) -> Lane:
    name = re.sub(r"[^a-z0-9]+", "_", directory_name.lower()).strip("_")[:40].strip("_")
    if not name or name == "app" or name.startswith("app_test"):
        raise DevError(
            f"worktree directory {directory_name!r} cannot be used as a lane name; "
            "rename the worktree directory (it must not reduce to 'app' or 'app_test*')"
        )
    api, vite = lane_ports(name)
    return Lane(name, f"fieldlens_{name}", api, vite, root / f".local/fieldlens/storage-{name}")


def resolve_main_root(root: Path, runner: Runner, environ: Mapping[str, str]) -> Path:
    git = root / ".git"
    if git.is_dir() or not git.exists():
        return root
    done = runner.run(
        ["git", "rev-parse", "--git-common-dir"], cwd=root, env=_git_env(environ), timeout=20
    )
    if done.returncode != 0 or not done.stdout.strip():
        raise DevError("cannot locate the main checkout (git rev-parse --git-common-dir failed)")
    common = Path(done.stdout.strip())
    common = common if common.is_absolute() else root / common
    return common.resolve().parent


def _git_env(environ: Mapping[str, str]) -> dict[str, str]:
    return {k: v for k, v in environ.items() if k in ("PATH", "HOME", "LANG")}


@dataclass
class Context:
    root: Path
    main_root: Path
    services: Services
    lane: Lane | None = None
    started: list[str] = field(default_factory=list)

    @property
    def run_dir(self) -> Path:
        return self.root / ".local/run"

    @property
    def api_port(self) -> int:
        return self.lane.api_port if self.lane else BASE_API_PORT

    @property
    def vite_port(self) -> int:
        return self.lane.vite_port if self.lane else BASE_VITE_PORT

    @property
    def env_path(self) -> Path:
        return self.root / ".env"

    @property
    def ready_url(self) -> str:
        return f"http://127.0.0.1:{self.api_port}{READY_PATH}"

    def say(self, text: str) -> None:
        self.services.out(text)

    def values(self) -> dict[str, str]:
        return self.services.load_env(self.env_path)

    def database(self, values: Mapping[str, str] | None = None) -> str | None:
        if self.lane:
            return self.lane.database
        return database_from_values(self.values() if values is None else values)

    def version(self) -> str:
        path = self.root / "VERSION"
        return path.read_text(encoding="utf-8").strip() if path.is_file() else "unknown"

    def storage(self, values: Mapping[str, str]) -> Path | None:
        if self.lane:
            return self.lane.storage
        raw = values.get("FIELDLENS_STORAGE_ROOT")
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_absolute() else self.root / path

    def ensure_run_dir(self) -> Path:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        return self.run_dir


def database_from_values(values: Mapping[str, str]) -> str | None:
    url = values.get("FIELDLENS_DATABASE_URL")
    if url:
        name = urlsplit(url).path.lstrip("/")
        return name or None
    return values.get("POSTGRES_DB") or None


def build_context(root: Path, services: Services) -> Context:
    main = resolve_main_root(root, services.runner, services.environ)
    lane = make_lane(root, root.name) if main != root else None
    return Context(root, main, services, lane)


def child_env(environ: Mapping[str, str], node_bin: Path | None) -> dict[str, str]:
    env = {k: v for k, v in environ.items() if ENV_ALLOW.match(k)}
    if node_bin is not None:
        env["PATH"] = f"{node_bin}{os.pathsep}{env.get('PATH', '')}".rstrip(os.pathsep)
    return env


# ---------------------------------------------------------------------------------------- node


def node_version(root: Path) -> str:
    return (root / ".node-version").read_text(encoding="utf-8").strip()


def find_node_bin(ctx: Context) -> Path:
    """FIELDLENS_NODE_BIN -> PATH node equal to .node-version -> pinned local installs."""
    svc = ctx.services
    version = node_version(ctx.root)
    fix = NODE_FIX.format(version=version)
    explicit = svc.environ.get("FIELDLENS_NODE_BIN")
    if explicit:
        path = Path(explicit)
        if (path / "node").exists():
            return path
        raise DevError(f"FIELDLENS_NODE_BIN={explicit} has no node executable; {fix}")
    on_path = svc.which("node")
    if on_path:
        done = svc.runner.run([on_path, "--version"], cwd=ctx.root, env=None, timeout=20)
        if done.returncode == 0 and done.stdout.strip() == f"v{version}":
            return Path(on_path).parent
    pattern = f".local/fieldlens/*/tools/node-v{version}-linux-x64/bin"
    seen: list[Path] = []
    for base in (ctx.root, ctx.main_root):
        if base in seen:
            continue
        seen.append(base)
        for candidate in sorted(base.glob(pattern)):
            if (candidate / "node").exists():
                return candidate
    raise DevError(f"Node {version} not found; {fix}")


# ----------------------------------------------------------------------------------- processes


@dataclass
class Managed:
    """A background process recorded by pid file and verified through /proc/<pid>/cmdline."""

    ctx: Context
    name: str
    port: int
    markers: tuple[str, ...]

    @property
    def pid_path(self) -> Path:
        return self.ctx.run_dir / f"{self.name}.pid"

    @property
    def log_path(self) -> Path:
        return self.ctx.run_dir / f"{self.name}.log"

    def _recorded_pid(self) -> int | None:
        try:
            data = json.loads(self.pid_path.read_text(encoding="utf-8"))
            return int(data["pid"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _matches(self, pid: int) -> bool:
        cmd = self.ctx.services.procs.cmdline(pid)
        if not cmd:
            return False
        return all(any(t == m or t.endswith("/" + m) for t in cmd) for m in self.markers)

    def pid(self) -> int | None:
        """The recorded pid only if the live command line still matches (never a reused pid)."""
        pid = self._recorded_pid()
        return pid if pid is not None and self._matches(pid) else None

    def clean_stale(self) -> bool:
        """Remove the pid file if it is not trusted. Returns whether a file was removed."""
        if self.pid_path.exists() and self.pid() is None:
            self.pid_path.unlink(missing_ok=True)
            return True
        return False

    def start(self, argv: Sequence[str], env: Mapping[str, str]) -> int:
        ctx = self.ctx
        ctx.ensure_run_dir()
        if self.log_path.exists() and self.log_path.stat().st_size > LOG_MAX_BYTES:
            self.log_path.write_bytes(b"")  # rotate by truncation
        pid = ctx.services.runner.spawn(argv, cwd=ctx.root, env=env, log=self.log_path)
        record = {"pid": pid, "markers": list(self.markers), "port": self.port}
        fd = os.open(self.pid_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle)
        ctx.started.append(self.name)
        return pid

    def stop(self) -> str:
        svc = self.ctx.services
        pid = self.pid()
        if pid is None:
            return "stale pid file removed" if self.clean_stale() else "not running"
        svc.procs.signal_group(pid, signal.SIGTERM)
        deadline = svc.clock.monotonic() + STOP_GRACE_S
        while self._matches(pid) and svc.clock.monotonic() < deadline:
            svc.clock.sleep(0.2)
        if self._matches(pid):  # re-verified immediately before the signal
            svc.procs.signal_group(pid, signal.SIGKILL)
            svc.clock.sleep(0.2)
        self.pid_path.unlink(missing_ok=True)
        return f"stopped (pid {pid})"


def api_process(ctx: Context) -> Managed:
    return Managed(
        ctx, "api", ctx.api_port, ("fieldlens.app:create_app", "--port", str(ctx.api_port))
    )


def vite_process(ctx: Context) -> Managed:
    return Managed(ctx, "vite", ctx.vite_port, ("vite.js", "--port", str(ctx.vite_port)))


def wait_ready(ctx: Context, url: str, timeout: float, alive: Callable[[], bool]) -> bool:
    svc = ctx.services
    deadline = svc.clock.monotonic() + timeout
    while True:
        if svc.http.status(url) == 200 and alive():
            return True  # a 200 from some other process on the port does not count
        if not alive() or svc.clock.monotonic() >= deadline:
            return False
        svc.clock.sleep(0.5)


# ----------------------------------------------------------------------------- compose/docker


@dataclass
class Compose:
    ctx: Context
    env: Mapping[str, str]

    def _run(self, argv: Sequence[str], timeout: float = 300) -> Result:
        # Always from the main checkout: it owns compose.yaml and the real .env.
        return self.ctx.services.runner.run(
            argv, cwd=self.ctx.main_root, env=self.env, timeout=timeout
        )

    def daemon_ok(self) -> bool:
        return self._run(["docker", "info"], timeout=30).returncode == 0

    def postgres_state(self) -> str:
        done = self._run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", POSTGRES_CONTAINER], 30
        )
        return done.stdout.strip() if done.returncode == 0 and done.stdout.strip() else "absent"

    def up_postgres(self) -> Result:
        return self._run(["docker", "compose", "up", "-d", "--wait", "postgres"])

    def stop_postgres(self) -> Result:
        return self._run(["docker", "compose", "stop", "postgres"])

    def up_browser(self) -> Result:
        return self._run(
            ["docker", "compose", "--profile", "test", "up", "-d", "--wait", "browser"]
        )

    def remove_browser(self) -> Result:
        return self._run(["docker", "compose", "--profile", "test", "rm", "-sf", "browser"])

    def psql(self, database: str, sql: str) -> Result:
        """Run SQL inside the container as the server role (read from the container's env)."""
        _ident(database)
        script = 'exec psql -X -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1 -tA -c "$2"'
        return self._run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postgres",
                "sh",
                "-c",
                script,
                "psql",
                database,
                sql,
            ],
            timeout=120,
        )

    def database_exists(self, name: str) -> bool:
        query = "SELECT 1 FROM pg_database WHERE datname = '" + _ident(name) + "'"  # noqa: S608
        done = self.psql("postgres", query)
        if done.returncode != 0:
            raise DevError("cannot query PostgreSQL through the postgres container")
        return done.stdout.strip() == "1"

    def create_database(self, name: str) -> None:
        if self.psql("postgres", f'CREATE DATABASE "{_ident(name)}"').returncode != 0:
            raise DevError(f"could not create database {name}")

    def drop_database(self, name: str) -> None:
        sql = f'DROP DATABASE IF EXISTS "{_ident(name)}" WITH (FORCE)'
        if self.psql("postgres", sql).returncode != 0:
            raise DevError(f"could not drop database {name}")

    def reset_schema(self, name: str) -> None:
        sql = "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public"
        if self.psql(_ident(name), sql).returncode != 0:
            raise DevError(f"could not reset schema public in {name}")


def _ident(name: str) -> str:
    if not DB_NAME.fullmatch(name):
        raise DevError(f"refusing unsafe database name {name!r}")
    return name


# ---------------------------------------------------------------------------------- lane env


def _quote_env(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def lane_database_url(values: Mapping[str, str], database: str) -> str:
    url = values.get("FIELDLENS_DATABASE_URL")
    if url:
        parts = urlsplit(url)
        return urlunsplit(parts._replace(path=f"/{database}"))
    user, password = values.get("POSTGRES_USER"), values.get("POSTGRES_PASSWORD")
    if not (user and password):
        raise DevError(f"main .env lacks POSTGRES_USER/POSTGRES_PASSWORD; run `{INIT_ENV_FIX}`")
    port = values.get("FIELDLENS_DB_PORT") or "55432"
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@127.0.0.1:{port}/{database}"
    )


# Only these main-.env keys are copied into a lane .env (never provider/bot/other FIELDLENS_*).
LANE_ENV_COPY = frozenset(
    {
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_PORT",
        "FIELDLENS_DB_PORT",
    }
)


def lane_server_env(lane: Lane) -> dict[str, str]:
    """Port, allowed Host values and CORS origins for the lane's offset ports (JSON lists)."""
    hosts = [
        f"{h}:{p}" for p in (lane.api_port, lane.vite_port) for h in ("127.0.0.1", "localhost")
    ]
    return {
        "FIELDLENS_PORT": str(lane.api_port),
        "FIELDLENS_ALLOWED_HOSTS": json.dumps(hosts),
        "FIELDLENS_ALLOWED_ORIGINS": json.dumps([f"http://{h}" for h in hosts]),
    }


def write_lane_env(ctx: Context, main_values: Mapping[str, str]) -> bool:
    """Create/refresh the derived lane ``.env`` (mode 0600). Returns whether it changed."""
    lane = ctx.lane
    assert lane is not None
    target = ctx.env_path
    if target.exists() and LANE_ENV_MARKER not in target.read_text(encoding="utf-8"):
        raise DevError(
            f"{target.name} exists in this worktree and was not derived by ./dev; "
            "move it away (it is never overwritten)"
        )
    values = {k: v for k, v in main_values.items() if k in LANE_ENV_COPY and v}
    values["POSTGRES_DB"] = lane.database
    values.update(lane_server_env(lane))
    values["FIELDLENS_DATABASE_URL"] = lane_database_url(main_values, lane.database)
    values["FIELDLENS_STORAGE_ROOT"] = str(lane.storage)
    body = LANE_ENV_MARKER + "".join(f"{k}={_quote_env(v)}\n" for k, v in sorted(values.items()))
    if target.exists() and target.read_text(encoding="utf-8") == body:
        if (target.stat().st_mode & 0o777) != 0o600:
            target.chmod(0o600)
        return False
    tmp = target.with_name(target.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(body)
    os.replace(tmp, target)
    return True


# ------------------------------------------------------------------------------------ frontend


class Frontend:
    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.dist = ctx.root / "frontend/dist"
        self.hash_path = ctx.run_dir / "frontend-build.hash"

    def _inputs(self) -> list[Path]:
        root = self.ctx.root
        files: list[Path] = []
        for sub in ("frontend/src", "frontend/public"):
            base = root / sub
            if base.is_dir():
                files += [p for p in base.rglob("*") if p.is_file()]
        for sub in ("frontend/scripts",):
            base = root / sub
            if base.is_dir():
                files += [p for p in base.rglob("*") if p.is_file()]
        for name in (
            "index.html",
            "package.json",
            "package-lock.json",
            "vite.config.ts",
            ".npmrc",
            "eslint.config.js",
        ):
            files.append(root / "frontend" / name)
        files += list((root / "frontend").glob("tsconfig*.json"))
        files.append(root / "VERSION")
        return sorted({p for p in files if p.is_file()})

    def digest(self) -> str:
        sha = hashlib.sha256()
        for path in self._inputs():
            sha.update(path.relative_to(self.ctx.root).as_posix().encode() + b"\0")
            sha.update(hashlib.sha256(path.read_bytes()).digest())
        return sha.hexdigest()

    def stale(self) -> bool:
        if not (self.dist / "index.html").is_file():
            return True
        try:
            return self.hash_path.read_text(encoding="utf-8").strip() != self.digest()
        except OSError:
            return True

    def deps_present(self) -> bool:
        return (self.ctx.root / "frontend/node_modules/vite/bin/vite.js").is_file()

    def build(self, node_bin: Path, env: Mapping[str, str]) -> None:
        """Build into a temp directory, then swap; a failed build leaves ``dist`` untouched."""
        ctx = self.ctx
        run_dir = ctx.ensure_run_dir()
        tmp, prev = run_dir / "dist-build", run_dir / "dist-prev"
        digest = self.digest()  # taken before the build so a concurrent edit stays stale
        shutil.rmtree(tmp, ignore_errors=True)
        out = ["--outDir", str(tmp), "--emptyOutDir"]
        attempts: list[list[str]] = []
        if (node_bin / "npm").exists():
            attempts.append(
                [str(node_bin / "npm"), "--prefix", "frontend", "run", "build", "--", *out]
            )
        attempts.append(
            [
                str(node_bin / "node"),
                "frontend/node_modules/vite/bin/vite.js",
                "build",
                "frontend",
                *out,
            ]
        )
        result = Result(1)
        for argv in attempts:
            result = run_logged(ctx, "build", argv, env, timeout=600)
            if result.returncode not in (126, 127):  # fall back only if npm cannot be launched
                break
            shutil.rmtree(tmp, ignore_errors=True)
        if result.returncode != 0 or not (tmp / "index.html").is_file():
            shutil.rmtree(tmp, ignore_errors=True)
            raise DevError(
                f"frontend build failed (exit {result.returncode}); previous dist kept; "
                f"see {run_dir / 'build.log'}"
            )
        shutil.rmtree(prev, ignore_errors=True)
        if self.dist.exists():
            os.replace(self.dist, prev)
        try:
            os.replace(tmp, self.dist)
        except OSError:
            if prev.exists():
                os.replace(prev, self.dist)
            raise
        shutil.rmtree(prev, ignore_errors=True)
        self.hash_path.write_text(digest + "\n", encoding="utf-8")


def run_logged(
    ctx: Context,
    name: str,
    argv: Sequence[str],
    env: Mapping[str, str],
    timeout: float | None = 600,
) -> Result:
    """Run a command; its output goes to ``.local/run/<name>.log`` (mode 0600), not the terminal."""
    result = ctx.services.runner.run(argv, cwd=ctx.root, env=env, timeout=timeout)
    run_dir = ctx.ensure_run_dir()
    fd = os.open(run_dir / f"{name}.log", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(result.stdout + result.stderr)
    return result


# ----------------------------------------------------------------------------------- helpers


def _uv(*args: str) -> list[str]:
    return ["uv", "run", "--frozen", *args]


def alembic_head(ctx: Context, env: Mapping[str, str]) -> str:
    done = ctx.services.runner.run(
        _uv("alembic", "-c", "backend/alembic.ini", "heads"), cwd=ctx.root, env=env, timeout=120
    )
    for line in done.stdout.splitlines():
        if line.strip():
            return line.split()[0]
    return "unknown"


def sync_python(ctx: Context, env: Mapping[str, str]) -> None:
    """``uv sync --frozen`` when uv.lock/pyproject changed; reinstall the package on VERSION change."""
    run_dir = ctx.ensure_run_dir()
    state_path = run_dir / "uv-sync.json"
    lock = hashlib.sha256()
    for name in ("uv.lock", "pyproject.toml"):
        path = ctx.root / name
        lock.update(path.read_bytes() if path.is_file() else b"")
    current = {"lock": lock.hexdigest(), "version": ctx.version()}
    try:
        previous = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = None
    if previous == current:
        return
    argv = ["uv", "sync", "--frozen"]
    if previous is not None and previous.get("version") != current["version"]:
        argv += ["--reinstall-package", "fieldlens"]
    done = run_logged(ctx, "uv-sync", argv, env)
    if done.returncode != 0:
        raise DevError(f"uv sync --frozen failed; see {run_dir / 'uv-sync.log'}")
    state_path.write_text(json.dumps(current), encoding="utf-8")


def migrate(ctx: Context, env: Mapping[str, str]) -> None:
    done = run_logged(
        ctx, "migrate", _uv("alembic", "-c", "backend/alembic.ini", "upgrade", "head"), env
    )
    if done.returncode != 0:
        raise DevError(
            f"alembic upgrade head failed (exit {done.returncode}); see {ctx.run_dir / 'migrate.log'}"
        )


def require_env(ctx: Context) -> dict[str, str]:
    """The main checkout's .env must exist and name the database settings (names only)."""
    main_env = ctx.main_root / ".env"
    if not main_env.is_file():
        raise DevError(f"{main_env} is missing; run `{INIT_ENV_FIX}` in the main checkout")
    values = ctx.services.load_env(main_env)
    missing = [k for k in REQUIRED_KEYS if not values.get(k)]
    if missing:
        raise DevError(f".env lacks {', '.join(missing)}; run `{INIT_ENV_FIX}`")
    return values


def require_docker(compose: Compose) -> None:
    if not compose.daemon_ok():
        raise DevError(
            "Docker daemon is not reachable; start Docker Desktop (or the docker service) "
            "and rerun the command"
        )


def ensure_postgres(ctx: Context, compose: Compose) -> None:
    if compose.postgres_state() == "healthy":
        return
    ctx.say("starting postgres (docker compose up -d --wait postgres)")
    if compose.up_postgres().returncode != 0:
        raise DevError(
            "postgres did not become healthy; run `docker compose ps postgres` "
            "and `docker compose logs postgres`"
        )


def summary(ctx: Context, env: Mapping[str, str], vite: bool) -> None:
    values = ctx.values()
    ctx.say(f"URL:       http://127.0.0.1:{ctx.api_port}/")
    if vite:
        ctx.say(f"Vite:      http://127.0.0.1:{ctx.vite_port}/")
    ctx.say(f"Database:  {ctx.database(values) or 'unknown'}")
    ctx.say(f"Version:   {ctx.version()}")
    ctx.say(f"Migration: {alembic_head(ctx, env)}")
    ctx.say(f"API log:   {ctx.run_dir / 'api.log'}")
    if vite:
        ctx.say(f"Vite log:  {ctx.run_dir / 'vite.log'}")
    if ctx.lane:
        ctx.say(f"Lane:      {ctx.lane.name} (storage {ctx.lane.storage})")


# ------------------------------------------------------------------------------------ commands


def cmd_up(
    ctx: Context, *, dev: bool = False, no_build: bool = False, install: bool = False
) -> int:
    svc = ctx.services
    api, vite = api_process(ctx), vite_process(ctx)
    for proc in (api, vite):
        if proc.clean_stale():
            ctx.say(f"removed stale {proc.name}.pid")

    main_values = require_env(ctx)
    node_bin = find_node_bin(ctx)
    env = child_env(svc.environ, node_bin)
    compose = Compose(ctx, env)
    frontend = Frontend(ctx)

    api_pid = api.pid()
    vite_pid = vite.pid()
    if api_pid is not None and svc.http.status(ctx.ready_url) == 200:
        # DV-2: healthy already; nothing to start, rebuild or restart.
        ctx.say(f"already running: api (pid {api_pid}); nothing changed")
        if frontend.stale() and not no_build:
            ctx.say("note: frontend sources changed; run `./dev restart` to rebuild and reload")
        if dev and vite_pid is None:
            _preflight_port(ctx, ctx.vite_port, "vite")
            _start_vite(ctx, vite, env, frontend, node_bin)
        elif vite_pid is not None:
            ctx.say(f"already running: vite (pid {vite_pid})")
        summary(ctx, env, dev or vite_pid is not None)
        return 0

    # ---- preflight: no side effects beyond a derived lane .env
    require_docker(compose)
    if api_pid is not None:
        ctx.say(f"api (pid {api_pid}) is not ready; restarting it")
        api.stop()
    _preflight_port(ctx, ctx.api_port, "api")
    if dev and vite_pid is None:
        _preflight_port(ctx, ctx.vite_port, "vite")
    needs_build = not no_build and frontend.stale()
    if (needs_build or dev) and not frontend.deps_present() and not install:
        raise DevError(
            "frontend dependencies are missing; run `npm --prefix frontend ci` "
            "(or rerun `./dev up --install`)"
        )
    if ctx.lane:
        write_lane_env(ctx, main_values)
    elif not ctx.env_path.is_file():
        raise DevError(f"{ctx.env_path} is missing; run `{INIT_ENV_FIX}`")

    created_db = False
    try:
        if not ctx.lane:
            run_logged(ctx, "init-env", _uv("python", "scripts/init_env.py"), env)
        sync_python(ctx, env)
        ensure_postgres(ctx, compose)
        if ctx.lane and not compose.database_exists(ctx.lane.database):
            ctx.say(f"creating lane database {ctx.lane.database}")
            compose.create_database(ctx.lane.database)
            created_db = True
        migrate(ctx, env)
        if install and not frontend.deps_present():
            ctx.say("installing frontend dependencies (npm --prefix frontend ci)")
            done = run_logged(
                ctx, "npm-ci", [str(node_bin / "npm"), "--prefix", "frontend", "ci"], env
            )
            if done.returncode != 0:
                raise DevError(f"npm ci failed; see {ctx.run_dir / 'npm-ci.log'}")
        if needs_build:
            ctx.say("building frontend (sources changed)")
            frontend.build(node_bin, env)
        elif not no_build:
            ctx.say("frontend build is current")
        _start_api(ctx, api, env)
        if dev and vite_pid is None:
            _start_vite(ctx, vite, env, frontend, node_bin)
    except KeyboardInterrupt:
        _stop_started(ctx, api, vite)
        _lane_db_kept(ctx, created_db)
        raise DevError(
            "interrupted; stopped what this run started (postgres left running)", 130
        ) from None
    except DevError:
        _stop_started(ctx, api, vite)
        _lane_db_kept(ctx, created_db)
        raise
    summary(ctx, env, dev)
    return 0


def _lane_db_kept(ctx: Context, created: bool) -> None:
    if ctx.lane and created:
        ctx.services.err(
            f"dev: lane database {ctx.lane.database} was created by this run and is kept; "
            f"remove it with: uv run python scripts/dev.py down --drop-lane"
        )


def _stop_started(ctx: Context, api: Managed, vite: Managed) -> None:
    for proc in (vite, api):
        if proc.name in ctx.started:
            proc.stop()


def worktree_roots(ctx: Context) -> list[Path]:
    roots = [ctx.main_root]
    done = ctx.services.runner.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=ctx.main_root,
        env=_git_env(ctx.services.environ),
        timeout=20,
    )
    if done.returncode == 0:
        for line in done.stdout.splitlines():
            if line.startswith("worktree "):
                roots.append(Path(line[len("worktree ") :].strip()))
    return list(dict.fromkeys(roots))


def other_holder(ctx: Context, port: int) -> str | None:
    """A live ./dev-managed process (any checkout) recorded on ``port``, if detectable."""
    for root in worktree_roots(ctx):
        for name in ("api", "vite"):
            try:
                data = json.loads((root / ".local/run" / f"{name}.pid").read_text(encoding="utf-8"))
                pid, recorded = int(data["pid"]), int(data["port"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            cmd = ctx.services.procs.cmdline(pid)
            if recorded == port and cmd and not (root == ctx.root and name in ctx.started):
                return f"the ./dev {name} of {root} (pid {pid})"
    return None


def _preflight_port(ctx: Context, port: int, what: str) -> None:
    if not ctx.services.ports.is_free(port):
        holder = other_holder(ctx, port)
        who = holder or "a foreign process ./dev did not start"
        raise DevError(
            f"port {port} ({what}) is in use by {who}; stop it or free "
            f"the port (find it with `ss -ltnp 'sport = :{port}'`) and rerun"
        )


def _start_api(ctx: Context, api: Managed, env: Mapping[str, str]) -> None:
    argv = _uv(
        "uvicorn",
        "fieldlens.app:create_app",
        "--factory",
        "--host",
        "127.0.0.1",
        "--port",
        str(ctx.api_port),
    )
    if ctx.lane:  # explicit env wins over any inherited FIELDLENS_* value or file
        env = {**env, **lane_server_env(ctx.lane)}
    pid = api.start(argv, env)
    ctx.say(f"started api (pid {pid}); waiting for {READY_PATH}")
    alive = lambda: api.pid() is not None  # noqa: E731
    if not wait_ready(ctx, ctx.ready_url, READY_TIMEOUT_S, alive):
        reason = "exited during startup" if api.pid() is None else "did not become ready in 60 s"
        api.stop()
        raise DevError(f"api {reason}; postgres left running; see {api.log_path}")


def _start_vite(
    ctx: Context, vite: Managed, env: Mapping[str, str], frontend: Frontend, node_bin: Path
) -> None:
    if not frontend.deps_present():
        raise DevError("frontend dependencies are missing; run `npm --prefix frontend ci`")
    if ctx.lane:
        ctx.say(
            f"note: frontend/vite.config.ts hardcodes the /api proxy to port {BASE_API_PORT} "
            f"(no env hook), so Vite in a lane proxies to the main checkout's API; use the "
            f"lane API directly at http://127.0.0.1:{ctx.api_port}/"
        )
    argv = [
        str(node_bin / "node"),
        "frontend/node_modules/vite/bin/vite.js",
        "frontend",
        "--host",
        "127.0.0.1",
        "--port",
        str(ctx.vite_port),
        "--strictPort",
    ]
    pid = vite.start(argv, env)
    ctx.say(f"started vite (pid {pid})")
    url = f"http://127.0.0.1:{ctx.vite_port}/"
    alive = lambda: vite.pid() is not None  # noqa: E731
    if not wait_ready(ctx, url, VITE_TIMEOUT_S, alive):
        vite.stop()
        raise DevError(f"vite did not start; see {vite.log_path}")


def confirm(ctx: Context, expected: str, what: str) -> None:
    try:
        answer = ctx.services.prompt(f"Type {expected} to {what}: ").strip()
    except EOFError:
        raise DevError(
            "no confirmation could be read (stdin closed); nothing was changed"
        ) from None
    if answer != expected:
        raise DevError("confirmation did not match; nothing was changed")


def cmd_down(ctx: Context, *, db: bool = False, drop_lane: bool = False) -> int:
    for proc in (vite_process(ctx), api_process(ctx)):
        ctx.say(f"{proc.name}: {proc.stop()}")
    if drop_lane:
        _drop_lane(ctx)
    if db:
        env = child_env(ctx.services.environ, None)
        compose = Compose(ctx, env)
        require_docker(compose)
        ctx.say("note: the postgres server is shared by every checkout")
        done = compose.stop_postgres()
        if done.returncode != 0:
            raise DevError("docker compose stop postgres failed")
        ctx.say("postgres: stopped (volume kept)")
    else:
        ctx.say("postgres: left running")
    return 0


def _drop_lane(ctx: Context) -> None:
    lane = ctx.lane
    if lane is None:
        raise DevError("--drop-lane only applies inside a linked worktree (a lane)")
    main_db = database_from_values(ctx.services.load_env(ctx.main_root / ".env"))
    if lane.database == main_db or not lane.database.startswith("fieldlens_"):
        raise DevError(f"refusing to drop {lane.database}: it is the main application database")
    env = child_env(ctx.services.environ, None)
    compose = Compose(ctx, env)
    require_docker(compose)
    if compose.postgres_state() != "healthy":
        raise DevError(
            "postgres is not running; run `./dev up` first (or start the postgres service)"
        )
    confirm(ctx, lane.database, f"drop this lane's database and delete {lane.storage}")
    compose.drop_database(lane.database)
    ctx.say(f"dropped database {lane.database}")
    storage = lane.storage
    if storage.name == f"storage-{lane.name}" and storage.parent == ctx.root / ".local/fieldlens":
        if storage.exists():
            shutil.rmtree(storage)
            ctx.say(f"deleted {storage}")
    ctx.say("the derived .env was left in place")


def cmd_restart(ctx: Context) -> int:
    was_vite = vite_process(ctx).pid() is not None
    cmd_down(ctx)
    return cmd_up(ctx, dev=was_vite)


def cmd_status(ctx: Context) -> int:
    svc = ctx.services
    values = ctx.values()
    if ctx.lane:
        ctx.say(f"lane:      {ctx.lane.name} (database {ctx.lane.database})")
    else:
        ctx.say("lane:      main checkout")
    ctx.say(f"version:   {ctx.version()}")
    ctx.say(f"database:  {ctx.database(values) or 'unknown'}")
    present = ", ".join(
        f"{k}={'set' if values.get(k) else 'missing'}"
        for k in (*REQUIRED_KEYS, "FIELDLENS_DATABASE_URL", "FIELDLENS_STORAGE_ROOT")
    )
    ctx.say(f".env:      {'present' if ctx.env_path.is_file() else 'missing'} ({present})")
    for proc in (api_process(ctx), vite_process(ctx)):
        if proc.clean_stale():
            ctx.say(f"{proc.name}: removed stale pid file")
        pid = proc.pid()
        if pid is None:
            busy = not svc.ports.is_free(proc.port)
            note = f"stopped; port {proc.port} {'in use by another process' if busy else 'free'}"
            ctx.say(f"{proc.name}:{' ' * (10 - len(proc.name))}{note}")
        else:
            health = ""
            if proc.name == "api":
                health = ", ready" if svc.http.status(ctx.ready_url) == 200 else ", NOT ready"
            ctx.say(
                f"{proc.name}:{' ' * (10 - len(proc.name))}running (pid {pid}, port {proc.port}{health})"
            )
    compose = Compose(ctx, child_env(svc.environ, None))
    ctx.say(
        f"postgres:  {compose.postgres_state() if compose.daemon_ok() else 'docker unavailable'}"
    )
    ctx.say(f"frontend:  {'build stale or missing' if Frontend(ctx).stale() else 'build current'}")
    ctx.say(f"logs:      {ctx.run_dir}")
    return 0


def cmd_logs(ctx: Context, which: str = "api", follow: bool = False) -> int:
    path = ctx.run_dir / f"{which}.log"
    if not path.is_file():
        raise DevError(f"no {which} log yet ({path}); run `./dev up`")
    data = path.read_bytes()
    for line in data.decode("utf-8", "replace").splitlines()[-200:]:
        ctx.say(line)
    if not follow:
        return 0
    offset = len(data)
    try:
        while True:
            ctx.services.clock.sleep(0.5)
            size = path.stat().st_size
            if size < offset:
                offset = 0  # truncated by rotation
            if size > offset:
                with path.open("rb") as handle:
                    handle.seek(offset)
                    chunk = handle.read()
                offset += len(chunk)
                for line in chunk.decode("utf-8", "replace").splitlines():
                    ctx.say(line)
    except KeyboardInterrupt:
        return 0


# --- tests (DV-8)

BACKEND_GATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pytest", ("pytest", "backend/tests", "-q")),
    ("ruff check", ("ruff", "check", "backend", "scripts")),
    ("ruff format", ("ruff", "format", "--check", "backend", "scripts")),
    ("mypy", ("mypy", "backend/fieldlens", "scripts")),
)
FRONTEND_GATES = ("typecheck", "lint", "test", "check:contracts")


def cmd_test(ctx: Context, target: str = "all") -> int:
    svc = ctx.services
    targets = ["backend", "frontend", "e2e"] if target == "all" else [target]
    node_bin: Path | None = None
    if target != "backend":
        node_bin = find_node_bin(ctx)
    else:
        try:
            node_bin = find_node_bin(ctx)
        except DevError:
            node_bin = None
    env = child_env(svc.environ, node_bin)
    compose = Compose(ctx, env)
    require_env(ctx)
    require_docker(compose)
    if "frontend" in targets or "e2e" in targets:
        if not Frontend(ctx).deps_present():
            raise DevError("frontend dependencies are missing; run `npm --prefix frontend ci`")
    ensure_postgres(ctx, compose)

    results: list[tuple[str, bool]] = []

    def gate(name: str, argv: Sequence[str]) -> None:
        ctx.say(f"== {name}")
        ok = (
            svc.runner.run(argv, cwd=ctx.root, env=env, timeout=1800, capture=False).returncode == 0
        )
        results.append((name, ok))
        ctx.say(f"-- {name}: {'PASS' if ok else 'FAIL'}")

    if "backend" in targets:
        for name, args in BACKEND_GATES:
            gate(name, _uv(*args))
    if "frontend" in targets and node_bin is not None:
        npm = str(node_bin / "npm")
        for script in FRONTEND_GATES:
            gate(f"frontend {script}", [npm, "--prefix", "frontend", "run", script])
        ctx.say("== frontend build")
        try:
            Frontend(ctx).build(node_bin, env)
            results.append(("frontend build", True))
            ctx.say("-- frontend build: PASS")
        except DevError as exc:
            results.append(("frontend build", False))
            ctx.say(f"-- frontend build: FAIL ({exc})")
    if "e2e" in targets:
        _gate_e2e(ctx, compose, env, results)
    failed = [name for name, ok in results if not ok]
    ctx.say(f"gates: {len(results) - len(failed)} passed, {len(failed)} failed")
    if failed:
        ctx.say("failed: " + ", ".join(failed))
    return 1 if failed or not results else 0


def _gate_e2e(
    ctx: Context, compose: Compose, env: Mapping[str, str], results: list[tuple[str, bool]]
) -> None:
    svc = ctx.services
    ctx.say("== e2e")
    if not (ctx.root / "frontend/dist/index.html").is_file():
        results.append(("e2e", False))
        ctx.say("-- e2e: FAIL (no frontend build; run `./dev test frontend` or `./dev up`)")
        return
    if not svc.ports.is_free(BASE_API_PORT):
        results.append(("e2e", False))
        ctx.say(f"-- e2e: FAIL (port {BASE_API_PORT} is in use; run `./dev down` first)")
        return
    try:
        started = compose.up_browser()
        if started.returncode != 0:
            results.append(("e2e", False))
            ctx.say("-- e2e: FAIL (browser service did not become healthy)")
            return
        ok = (
            svc.runner.run(
                _uv("python", "scripts/run_e2e.py"),
                cwd=ctx.root,
                env=env,
                timeout=1800,
                capture=False,
            ).returncode
            == 0
        )
        results.append(("e2e", ok))
        ctx.say(f"-- e2e: {'PASS' if ok else 'FAIL'}")
    finally:
        compose.remove_browser()  # service-named: only the browser container


def check_reset_target(target: str | None, configured: str | None) -> str:
    """DV-9: only the configured app/lane database; never a test database."""
    if not target or not configured:
        raise DevError(
            "database configuration is incomplete; run `uv run python scripts/init_env.py`"
        )
    if target.startswith(TEST_DB_PREFIX) or configured.startswith(TEST_DB_PREFIX):
        raise DevError(f"refusing to reset test database {target}")
    if not DB_NAME.fullmatch(target) or not target.startswith("fieldlens_"):
        raise DevError(f"refusing to reset {target!r}: not a fieldlens_* database name")
    if target != configured:
        raise DevError(
            f"refusing to reset {target}: it is not the configured database {configured}"
        )
    return target


def cmd_reset_data(ctx: Context, *, force: bool = False) -> int:
    svc = ctx.services
    main_values = require_env(ctx)
    values = ctx.values() if ctx.env_path.is_file() else main_values
    configured = ctx.lane.database if ctx.lane else main_values.get("POSTGRES_DB")
    target = check_reset_target(database_from_values(values), configured)
    api = api_process(ctx)
    api.clean_stale()
    if api.pid() is not None and not force:
        raise DevError("the API is running; run `./dev down` first (or pass --force to stop it)")
    node_bin = None
    try:
        node_bin = find_node_bin(ctx)
    except DevError:
        pass
    env = child_env(svc.environ, node_bin)
    compose = Compose(ctx, env)
    require_docker(compose)
    if compose.postgres_state() != "healthy":
        raise DevError("postgres is not running; run `./dev up` first")
    if not compose.database_exists(target):
        raise DevError(f"database {target} does not exist; run `./dev up` to create it")
    confirm(ctx, target, f"erase ALL data in database {target}")
    if api.pid() is not None:
        ctx.say(f"api: {api.stop()}")
    compose.reset_schema(target)
    ctx.say(f"deleted: every table/object in schema public of {target} (schema recreated)")
    migrate(ctx, env)
    ctx.say(f"re-applied migrations to {alembic_head(ctx, env)}")
    storage = ctx.storage(values)
    ctx.say(f"kept: uploaded originals under {storage} are not touched; the volume is untouched")
    return 0


def cmd_env_check(ctx: Context) -> int:
    svc = ctx.services
    problems = 0

    def line(ok: bool, text: str) -> None:
        nonlocal problems
        problems += 0 if ok else 1
        ctx.say(f"{'ok  ' if ok else 'FAIL'} {text}")

    main_env = ctx.main_root / ".env"
    values = svc.load_env(main_env) if main_env.is_file() else {}
    line(
        main_env.is_file(),
        f".env present ({main_env})"
        if main_env.is_file()
        else f".env missing; run `{INIT_ENV_FIX}`",
    )
    if main_env.is_file():
        mode = main_env.stat().st_mode & 0o777
        line(mode == 0o600, f".env mode {oct(mode)[2:]}")
        for key in (*REQUIRED_KEYS, "FIELDLENS_DATABASE_URL", "FIELDLENS_STORAGE_ROOT"):
            line(bool(values.get(key)), f"{key}: {'set' if values.get(key) else 'missing'}")
    try:
        node_bin: Path | None = find_node_bin(ctx)
        line(True, f"node {node_version(ctx.root)} at {node_bin}")
    except DevError as exc:
        node_bin = None
        line(False, str(exc))
    line(svc.which("uv") is not None, "uv on PATH" if svc.which("uv") else "uv not on PATH")
    compose = Compose(ctx, child_env(svc.environ, node_bin))
    docker_ok = compose.daemon_ok()
    line(docker_ok, "docker daemon reachable" if docker_ok else "docker daemon unreachable")
    if docker_ok:
        ctx.say(f"info postgres container: {compose.postgres_state()}")
    frontend = Frontend(ctx)
    line(
        frontend.deps_present(),
        "frontend dependencies installed"
        if frontend.deps_present()
        else "frontend dependencies missing; run `npm --prefix frontend ci`",
    )
    for proc in (api_process(ctx), vite_process(ctx)):
        pid = proc.pid()
        free = svc.ports.is_free(proc.port)
        if pid is not None:
            ctx.say(f"info {proc.name}: running (pid {pid}) on port {proc.port}")
        else:
            line(
                free,
                f"{proc.name} port {proc.port} free"
                if free
                else f"{proc.name} port {proc.port} used by another process",
            )
    ctx.say(
        f"info lane: {ctx.lane.name if ctx.lane else 'main checkout'}; "
        f"database {ctx.database(values) or 'unknown'}"
    )
    return 1 if problems else 0


# ---------------------------------------------------------------------------------------- CLI

USAGE = """usage: ./dev <command> [options]

commands:
  up [--dev] [--no-build] [--install]   start postgres, migrate, build if stale, start the API
  down [--db] [--drop-lane]             stop the API/Vite (--db: also postgres; --drop-lane: lane DB)
  restart                               down + up (Vite is kept if it was running)
  status                                what is running, never secret values
  logs [api|vite] [-f]                  show (and follow) a log
  test [backend|frontend|e2e|all]       run the documented gates
  reset-data [--force]                  erase the configured database after typed confirmation
  env-check                             verify prerequisites without changing anything
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="./dev", usage=USAGE, add_help=False)
    parser.add_argument("-h", "--help", action="store_true")
    sub = parser.add_subparsers(dest="command")
    up = sub.add_parser("up")
    up.add_argument("--dev", action="store_true")
    up.add_argument("--no-build", action="store_true")
    up.add_argument("--install", action="store_true")
    down = sub.add_parser("down")
    down.add_argument("--db", action="store_true")
    down.add_argument("--drop-lane", action="store_true")
    sub.add_parser("restart")
    sub.add_parser("status")
    logs = sub.add_parser("logs")
    logs.add_argument("which", nargs="?", choices=("api", "vite"), default="api")
    logs.add_argument("-f", "--follow", action="store_true")
    test = sub.add_parser("test")
    test.add_argument(
        "target", nargs="?", choices=("backend", "frontend", "e2e", "all"), default="all"
    )
    reset = sub.add_parser("reset-data")
    reset.add_argument("--force", action="store_true")
    sub.add_parser("env-check")
    return parser


@contextlib.contextmanager
def operation_lock(ctx: Context) -> Iterator[None]:
    """Exclusive non-blocking flock for the whole mutating command."""
    path = ctx.ensure_run_dir() / "up.lock"
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise DevError("another ./dev operation is running") from None
        yield
    finally:
        os.close(fd)  # closing releases the lock


def main(
    argv: Sequence[str] | None = None,
    services: Services | None = None,
    root: Path = ROOT,
) -> int:
    svc = services or real_services()
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    if args.help or args.command is None:
        svc.out(USAGE.rstrip())
        return 0
    try:
        ctx = build_context(root, svc)
        with contextlib.ExitStack() as stack:
            if args.command in ("up", "down", "restart", "reset-data"):
                stack.enter_context(operation_lock(ctx))
            return dispatch(ctx, args)
    except DevError as exc:
        svc.err(f"dev: {exc}")
        return exc.code
    except KeyboardInterrupt:
        svc.err("dev: interrupted")
        return 130


def dispatch(ctx: Context, args: argparse.Namespace) -> int:
    match args.command:
        case "up":
            return cmd_up(ctx, dev=args.dev, no_build=args.no_build, install=args.install)
        case "down":
            return cmd_down(ctx, db=args.db, drop_lane=args.drop_lane)
        case "restart":
            return cmd_restart(ctx)
        case "status":
            return cmd_status(ctx)
        case "logs":
            return cmd_logs(ctx, args.which, args.follow)
        case "test":
            return cmd_test(ctx, args.target)
        case "reset-data":
            return cmd_reset_data(ctx, force=args.force)
        case "env-check":
            return cmd_env_check(ctx)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

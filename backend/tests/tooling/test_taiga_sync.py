"""TG-1..TG-6 against a loopback fake Taiga server; no external network."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from .test_ledger import FEATURE, block, ledger_text
from .test_toolenv import load_script

track = load_script("track")
USER = "slimco86"
PASSWORD = "pw-Sup3r-secret-value"
STORY_STATUSES = ["New", "Ready", "In progress", "Ready for test", "Done", "Archived"]
TASK_STATUSES = ["New", "In progress", "Ready for test", "Closed", "Needs Info"]
STORY_FIELDS = {
    "project",
    "subject",
    "description",
    "status",
    "tags",
    "milestone",
    "assigned_to",
    "due_date",
    "is_blocked",
    "blocked_note",
    "version",
}
TASK_FIELDS = STORY_FIELDS | {"user_story"}
# real Taiga list endpoints omit these (detail endpoints return them)
LIST_OMITS = {"description", "description_html", "blocked_note_html", "neighbors"}
TASK_LIST_OMITS = {"comment", "generated_user_stories"}


class Fake:
    def __init__(self) -> None:
        self.private = True
        self.objects: dict[str, dict[int, dict[str, Any]]] = {"userstories": {}, "tasks": {}}
        self.ref = 0
        self.next_id = 100
        self.token = "tok-0"
        self.logins = 0
        self.writes = 0  # POST/PATCH on userstories/tasks
        self.requests: list[tuple[str, str]] = []
        self.failures: dict[tuple[str, str], list[int]] = {}
        self.tag_pairs_only = False
        self.conflict_once = False
        self.base = ""

    def add_raw(self, kind: str, subject: str) -> dict[str, Any]:
        return self._create(kind, {"subject": subject, "tags": []})

    def _create(self, kind: str, body: dict[str, Any]) -> dict[str, Any]:
        self.ref += 1
        self.next_id += 1
        obj = {
            "id": self.next_id,
            "ref": self.ref,
            "version": 1,
            "is_blocked": False,
            "blocked_note": "",
            "assigned_to": None,
            "due_date": None,
            "milestone": None,
            "description": "",
            "description_html": "",
            "blocked_note_html": "",
            "status": None,
            **body,
        }
        obj["tags"] = [[t, None] if isinstance(t, str) else t for t in obj.get("tags", [])]
        self.objects[kind][obj["id"]] = obj
        return obj

    def by_subject(self, kind: str, prefix: str) -> dict[str, Any]:
        found = [o for o in self.objects[kind].values() if o["subject"].startswith(prefix)]
        assert len(found) == 1
        return found[0]


@pytest.fixture
def fake() -> Iterator[Fake]:
    state = Fake()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, status: int, payload: Any, headers: dict[str, str] | None = None) -> None:
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def _handle(self, method: str) -> None:
            url = urlparse(self.path)
            path = url.path.removeprefix("/api/v1")
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"null")
            state.requests.append((method, path))
            queue = state.failures.get((method, path.split("/")[1] if path != "/" else ""))
            if queue:
                code = queue.pop(0)
                headers = {"Retry-After": "0"} if code == 429 else {}
                self._send(code, {"_error_message": "injected"}, headers)
                return
            if method == "POST" and path == "/auth":
                if body.get("username") != USER or body.get("password") != PASSWORD:
                    self._send(401, {"_error_message": "bad credentials"})
                    return
                state.logins += 1
                if state.logins > 1:
                    state.token = f"tok-{state.logins}"
                self._send(200, {"auth_token": state.token, "id": 7})
                return
            if self.headers.get("Authorization") != f"Bearer {state.token}":
                self._send(401, {"_error_message": "unauthorized"})
                return
            self._route(method, path, query, body)

        def _route(self, method: str, path: str, query: dict[str, str], body: Any) -> None:
            parts = path.strip("/").split("/")
            if path == "/users/me":
                self._send(200, {"id": 7, "username": USER})
            elif path == "/projects/by_slug":
                self._send(200, {"id": 1, "slug": query["slug"], "is_private": state.private})
            elif path == "/userstory-statuses":
                self._send(200, [{"id": 10 + i, "name": n} for i, n in enumerate(STORY_STATUSES)])
            elif path == "/task-statuses":
                self._send(200, [{"id": 50 + i, "name": n} for i, n in enumerate(TASK_STATUSES)])
            elif path == "/milestones":
                self._send(200, [{"id": 5, "name": "Hackathon"}])
            elif path == "/memberships":
                self._send(200, [{"id": 1, "user": 7}])
            elif parts[0] in state.objects:
                self._objects(method, parts, query, body)
            else:
                self._send(404, {"_error_message": "not found"})

        def _objects(self, method: str, parts: list[str], query: dict[str, str], body: Any) -> None:
            kind = parts[0]
            store = state.objects[kind]
            allowed = STORY_FIELDS if kind == "userstories" else TASK_FIELDS
            if method == "GET" and len(parts) == 1:
                assert self.headers.get("x-disable-pagination") == "True"
                omit = LIST_OMITS if kind == "userstories" else LIST_OMITS | TASK_LIST_OMITS
                self._send(
                    200, [{k: v for k, v in o.items() if k not in omit} for o in store.values()]
                )
            elif method == "GET":
                self._send(200, store[int(parts[1])])
            elif method == "POST":
                state.writes += 1
                bad = set(body) - (allowed - {"version"})
                if bad or not body.get("subject"):
                    self._send(400, {"_error_message": f"unknown fields {sorted(bad)}"})
                elif state.tag_pairs_only and any(isinstance(t, str) for t in body["tags"]):
                    self._send(400, {"tags": ["Invalid tag format"]})
                else:
                    self._send(201, state._create(kind, body))
            elif method == "PATCH":
                state.writes += 1
                obj = store.get(int(parts[1]))
                if obj is None:
                    self._send(404, {})
                    return
                if state.conflict_once:
                    state.conflict_once = False
                    obj["version"] += 1  # concurrent edit in the Taiga UI
                bad = set(body) - allowed
                if bad or "version" not in body:
                    self._send(400, {"_error_message": f"bad fields {sorted(bad)} or no version"})
                    return
                if body["version"] != obj["version"]:
                    self._send(400, {"version": ["The version doesn't match with the current one"]})
                    return
                if state.tag_pairs_only and any(isinstance(t, str) for t in body.get("tags", [])):
                    self._send(400, {"tags": ["Invalid tag format"]})
                    return
                body.pop("version")
                if "tags" in body:
                    body["tags"] = [[t, None] if isinstance(t, str) else t for t in body["tags"]]
                obj.update(body)
                obj["version"] += 1
                self._send(200, obj)

        def do_GET(self) -> None:
            self._handle("GET")

        def do_POST(self) -> None:
            self._handle("POST")

        def do_PATCH(self) -> None:
            self._handle("PATCH")

    server = HTTPServer(("127.0.0.1", 0), Handler)
    state.base = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state
    server.shutdown()
    server.server_close()


FEATURES = block("FL-001", "First feature", Tags="backend, ingestion") + block(
    "FL-002", "Second feature", Depends_on="FL-001", Due="2026-11-02", Assignee="unassigned"
)
TASKS = block("TASK-001", "First task", Slice="FL-001-A") + block(
    "TASK-002",
    "Second task",
    Depends_on="TASK-001",
    Assignee="agent:fieldlens-backend",
    Priority="P1",
    Due="2026-11-02",
)


class Env:
    def __init__(self, tmp: Path, fake: Fake) -> None:
        self.tmp = tmp
        self.fake = fake
        self.path = tmp / "BACKLOG.md"
        self.path.write_text(ledger_text(FEATURES, TASKS), encoding="utf-8")
        self.environ = {
            "TAIGA_USERNAME": USER,
            "TAIGA_PASSWORD": PASSWORD,
            "TAIGA_URL": fake.base,
            "TAIGA_ALLOW_PUBLIC": "1",
        }
        self.sleeps: list[float] = []

    def set_text(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    def run(self, **kwargs: Any) -> int:
        return int(
            track.cmd_sync(
                self.path,
                root=self.tmp,
                environ=self.environ,
                sleep=self.sleeps.append,
                **kwargs,
            )
        )


@pytest.fixture
def env(tmp_path: Path, fake: Fake) -> Env:
    return Env(tmp_path, fake)


def test_plan_diff(env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    assert env.run() == 0
    out = capsys.readouterr().out
    assert out.count("create  ") == 4
    assert "dry-run: created=4 updated=0 unchanged=0" in out
    assert fake.writes == 0
    assert {m for m, _ in fake.requests} == {"GET", "POST"}  # POST only /auth
    assert not (env.tmp / ".local").exists()  # dry-run writes no state
    assert env.run(apply=True) == 0
    capsys.readouterr()
    env.set_text(
        env.path.read_text(encoding="utf-8").replace(
            "| Status | in_progress |", "| Status | testing |", 1
        )
    )
    writes = fake.writes
    assert env.run() == 0
    out = capsys.readouterr().out
    assert re.search(r"update  FL-001\s+story\s+changed: status", out)
    assert out.count("no-op") == 2  # FL-002 note changes too
    assert fake.writes == writes
    # offline CLI path of plan keeps working without credentials
    assert track.main(["--file", str(env.path), "plan", "--offline"]) == 0


def test_apply_mapping(env: Env, fake: Fake) -> None:
    assert env.run(apply=True) == 0
    s1 = fake.by_subject("userstories", "[FL-001] ")
    s2 = fake.by_subject("userstories", "[FL-002] ")
    t1 = fake.by_subject("tasks", "[TASK-001] ")
    t2 = fake.by_subject("tasks", "[TASK-002] ")
    assert s1["subject"] == "[FL-001] First feature"
    assert s1["status"] == 12  # In progress
    assert sorted(t[0] for t in s1["tags"]) == ["backend", "ingestion", "p0"]
    assert s1["assigned_to"] == 7 and s1["milestone"] == 5 and s1["due_date"] == "2026-11-01"
    assert s1["is_blocked"] is False and s1["blocked_note"] == ""
    assert s2["is_blocked"] is True and s2["blocked_note"] == "Waiting for FL-001 (in_progress)"
    assert s2["assigned_to"] is None
    assert f"- FL-001 (in_progress) #{s1['ref']}" in s2["description"]
    assert "**Outcome.** Does a thing." in s1["description"]
    assert t1["user_story"] == s1["id"] and t2["user_story"] == s1["id"]
    assert t1["milestone"] == 5 and t1["status"] == 51  # In progress
    assert t2["is_blocked"] is True and t2["assigned_to"] is None
    assert "agent-fieldlens-backend" in [t[0] for t in t2["tags"]] and "p1" in [
        t[0] for t in t2["tags"]
    ]
    assert f"#{t1['ref']}" in t2["description"]
    # stories created first, then tasks
    assert s1["ref"] < s2["ref"] < t1["ref"] < t2["ref"]


def test_status_mapping_done_and_cancelled(env: Env, fake: Fake) -> None:
    done = block("FL-001", Status="done", Version="0.1.0", Due="2026-10-30").replace(
        "none yet", "Done in `abc1234`."
    )
    done_task = block("TASK-001", Status="done", Version="0.1.0", Due="2026-10-30").replace(
        "none yet", "Done in `abc1234`."
    )
    cancelled = block("TASK-002", Status="cancelled", Due="2026-11-02")
    env.set_text(ledger_text(done, done_task + cancelled))
    assert env.run(apply=True) == 0
    assert fake.by_subject("userstories", "[FL-001]")["status"] == 14  # Done
    assert fake.by_subject("tasks", "[TASK-001]")["status"] == 53  # Closed
    t2 = fake.by_subject("tasks", "[TASK-002]")
    assert t2["status"] == 53 and "cancelled" in [t[0] for t in t2["tags"]]


def test_idempotent_apply(env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    fake.add_raw("userstories", "Hand-made story")
    fake.add_raw("tasks", "[FL-009] foreign prefix")
    assert env.run(apply=True) == 0
    out = capsys.readouterr().out
    assert "untouched 1 unprefixed user story" in out and "FL-009" in out
    assert fake.writes == 4  # stories and tasks created with links already resolved
    writes = fake.writes
    gets = len(fake.requests)
    assert env.run(apply=True) == 0
    assert fake.writes == writes
    assert "writes=0" in capsys.readouterr().out
    second = fake.requests[gets:]
    assert [r for r in second if r[0] != "GET" and r[1] != "/auth"] == []
    details = [r for r in second if r[1].startswith(("/userstories/", "/tasks/"))]
    assert len(details) == 4  # one detail GET per matched item, O(n)
    assert len(second) <= 4 + 12
    state_path = env.tmp / ".local" / "run" / "taiga-state.json"
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    state_text = state_path.read_text(encoding="utf-8")
    assert "First feature" not in state_text and PASSWORD not in state_text
    # Matching uses live state: a missing state file changes nothing.
    state_path.unlink()
    assert env.run(apply=True) == 0 and fake.writes == writes
    # A deleted tracker item is re-created.
    gone = fake.by_subject("tasks", "[TASK-001]")
    del fake.objects["tasks"][gone["id"]]
    assert env.run(apply=True) == 0
    assert fake.by_subject("tasks", "[TASK-001]")["id"] != gone["id"]
    assert fake.by_subject("userstories", "Hand-made")["subject"] == "Hand-made story"


def test_duplicates_abort(env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    fake.add_raw("userstories", "[FL-001] one")
    fake.add_raw("userstories", "[FL-001] two")
    assert env.run(apply=True) == 2
    assert "duplicate" in capsys.readouterr().err
    assert fake.writes == 0


def test_only_scope(env: Env, fake: Fake) -> None:
    assert env.run(apply=True, only="FL-001,TASK-001") == 0
    assert len(fake.objects["userstories"]) == 1 and len(fake.objects["tasks"]) == 1
    assert env.run(apply=True, only="TASK-002") == 0  # parent already live
    assert len(fake.objects["tasks"]) == 2
    assert env.run(only="NOPE-001") == 2


def test_drift_and_retry(env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    assert env.run(apply=True) == 0
    capsys.readouterr()
    s1 = fake.by_subject("userstories", "[FL-001]")
    s1["status"] = 10  # owner moved it in the Taiga UI
    s1["version"] += 1
    assert env.run(apply=True, keep_drift=True) == 0
    out = capsys.readouterr().out
    assert "drift   FL-001" in out and "kept" in out
    assert s1["status"] == 10
    assert env.run(apply=True) == 0
    out = capsys.readouterr().out
    assert "drift   FL-001" in out and "overwritten" in out
    assert s1["status"] == 12
    assert env.run(apply=True) == 0 and "writes=0" in capsys.readouterr().out
    # 429/5xx retried with Retry-After; 401 triggers one re-auth
    s1["status"] = 10
    s1["version"] += 1
    fake.failures[("GET", "userstories")] = [429, 500]
    fake.failures[("PATCH", "userstories")] = [503]
    fake.token = "tok-expired"  # server forgets the token -> client re-auths once
    assert env.run(apply=True) == 0
    assert s1["status"] == 12
    assert len(env.sleeps) >= 3 and fake.logins >= 2


def test_retry_exhausted_and_partial_state(env: Env, fake: Fake) -> None:
    fake.failures[("GET", "tasks")] = [500, 500, 500, 500]
    assert env.run(apply=True) == 2
    assert fake.writes == 0
    # mid-run failure: creating tasks fails after stories exist; next run completes
    fake.failures[("POST", "tasks")] = [400]
    assert env.run(apply=True) == 2
    assert len(fake.objects["userstories"]) == 2 and len(fake.objects["tasks"]) == 0
    assert env.run(apply=True) == 0
    assert len(fake.objects["userstories"]) == 2 and len(fake.objects["tasks"]) == 2
    writes = fake.writes
    assert env.run(apply=True) == 0 and fake.writes == writes


def test_tag_pair_fallback_and_version_conflict(env: Env, fake: Fake) -> None:
    fake.tag_pairs_only = True
    assert env.run(apply=True) == 0
    assert len(fake.objects["userstories"]) == 2
    s1 = fake.by_subject("userstories", "[FL-001]")
    s1["status"] = 10
    fake.conflict_once = True
    assert env.run(apply=True) == 0 and s1["status"] == 12
    assert not fake.conflict_once


def test_privacy_guards(env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    fake.private = False
    del env.environ["TAIGA_ALLOW_PUBLIC"]
    assert env.run(apply=True) == 3
    assert fake.writes == 0 and not fake.objects["userstories"]
    assert "TAIGA_ALLOW_PUBLIC" in capsys.readouterr().err
    env.environ["TAIGA_ALLOW_PUBLIC"] = "1"
    assert env.run(apply=True) == 0
    # secret-like text is already a ledger violation (exit 1), before any network call
    fake.requests.clear()
    secret = "pass" + "word=" + "abcdefghijk123"
    env.set_text(ledger_text(FEATURES.replace("First feature", f"First {secret}"), TASKS))
    assert env.run(apply=True) == 1
    assert fake.requests == []
    # configured credential value in ledger text is refused too
    env.set_text(ledger_text(FEATURES.replace("First feature", f"x {PASSWORD}"), TASKS))
    assert env.run(apply=True) == 3 and fake.requests == []
    err = capsys.readouterr()
    assert PASSWORD not in err.out + err.err
    assert "abcdefghijk123" not in err.out + err.err
    # parse errors abort before the network
    env.set_text("# nothing\n")
    assert env.run(apply=True) == 1 and fake.requests == []
    # missing credentials name keys only
    env.set_text(ledger_text(FEATURES, TASKS))
    env.environ.pop("TAIGA_PASSWORD")
    assert env.run() == 2
    assert "TAIGA_PASSWORD" in capsys.readouterr().err
    # wrong password: failure text never echoes credentials or token
    env.environ["TAIGA_PASSWORD"] = "wrong-pass-value"
    assert env.run() == 2
    err = capsys.readouterr()
    assert "wrong-pass-value" not in err.out + err.err and fake.token not in err.out + err.err


def test_plain_http_requires_loopback() -> None:
    client_mod = load_script("taiga_client")
    with pytest.raises(client_mod.TaigaError):
        client_mod.TaigaClient("http://example.com", "u", "p")
    client_mod.TaigaClient("https://api.taiga.io", "u", "p")


def test_sync_notify(
    env: Env, fake: Fake, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_notify(event: str, text: str, **kwargs: Any) -> int:
        calls.append({"event": event, "text": text, **kwargs})
        return 0

    monkeypatch.setattr(track.notify_mod, "notify", fake_notify)
    assert env.run(notify=True) == 0  # dry-run sends nothing
    assert calls == []
    assert env.run(apply=True, notify=True) == 0
    assert len(calls) == 1
    text = calls[0]["text"]
    assert "created 4" in text and "FL-001" in text and "TASK-002" in text
    assert calls[0]["best_effort"] is True and PASSWORD not in text
    assert env.run(apply=True, notify=True) == 0
    assert len(calls) == 2 and "created 0, updated 0" in calls[1]["text"]
    assert "Changed" not in calls[1]["text"]
    capsys.readouterr()


def test_feature_fixture_sanity() -> None:
    assert FEATURE["Sprint"] == "Hackathon"


def test_only_empty_is_usage_error(
    env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    for bad in ("", " ", ",", " , ,"):
        assert env.run(apply=True, only=bad) == 2
        assert env.run(only=bad) == 2
    assert fake.requests == [] and fake.writes == 0
    assert "--only" in capsys.readouterr().err


def test_only_scope_skips_other_details(env: Env, fake: Fake) -> None:
    assert env.run(apply=True) == 0
    fake.requests.clear()
    assert env.run(apply=True, only="FL-001") == 0
    details = [r for r in fake.requests if r[1].startswith(("/userstories/", "/tasks/"))]
    assert len(details) == 1


def test_stale_list_version_uses_detail_version(env: Env, fake: Fake) -> None:
    assert env.run(apply=True) == 0
    s1 = fake.by_subject("userstories", "[FL-001]")
    s1["status"] = 10
    s1["version"] += 5
    assert env.run(apply=True) == 0 and s1["status"] == 12


def test_concurrent_apply_is_refused(
    env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    fd = track._acquire_lock(env.tmp)
    assert fd is not None
    try:
        assert (
            track._acquire_lock(env.tmp) is None
        )  # second fd, same process: flock is per-open-file
        assert env.run(apply=True) == 2
        assert "another sync is running" in capsys.readouterr().err
        assert fake.requests == [] and fake.writes == 0
        assert env.run() == 0  # read-only plan does not need the lock
    finally:
        os.close(fd)
    assert env.run(apply=True) == 0  # lock released


def test_lock_across_processes(env: Env, tmp_path: Path) -> None:
    code = (
        "import fcntl,os,sys,time\n"
        "fd=os.open(sys.argv[1],os.O_RDWR|os.O_CREAT,0o600)\n"
        "fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
        "print('held',flush=True);time.sleep(30)\n"
    )
    lock = env.tmp / ".local" / "run" / "taiga-sync.lock"
    lock.parent.mkdir(parents=True)
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", code, str(lock)], stdout=subprocess.PIPE, text=True
    )
    try:
        assert proc.stdout is not None and proc.stdout.readline().strip() == "held"
        assert env.run(apply=True) == 2
    finally:
        proc.kill()
        proc.wait()
    assert env.run(apply=True) == 0


def test_state_atomic_and_corrupt(env: Env, fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    assert env.run(apply=True) == 0
    run_dir = env.tmp / ".local" / "run"
    assert sorted(p.name for p in run_dir.iterdir()) == ["taiga-state.json", "taiga-sync.lock"]
    state_path = run_dir / "taiga-state.json"
    capsys.readouterr()
    for junk in ('{"project": 1, "items": ', "[]", "\x00\xff", '{"project": 1}'):
        state_path.write_bytes(junk.encode("latin-1"))
        writes = fake.writes
        assert env.run(apply=True) == 0 and fake.writes == writes
        assert "state file" in capsys.readouterr().err
    state_path.write_text(
        json.dumps({"project": 1, "items": {"FL-001": {"hashes": "bad"}}}), encoding="utf-8"
    )
    assert env.run(apply=True) == 0
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    json.loads(state_path.read_text(encoding="utf-8"))

"""NT-1..NT-6 against a loopback fake Telegram server; no external network."""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import pytest

from .test_toolenv import load_script

notify = load_script("notify")
TOKEN = "123456789:" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
CHAT = "424242"
BASE_ENV = {"TELEGRAM_BOT_TOKEN": TOKEN, "TELEGRAM_CHAT_ID": CHAT}


class Fake:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict[str, str]]] = []
        self.statuses: list[int] = []  # popped per request; empty -> 200
        self.updates: list[dict[str, Any]] = []
        self.base = ""


@pytest.fixture
def fake() -> Iterator[Fake]:
    state = Fake()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            state.requests.append((self.path, form))
            status = state.statuses.pop(0) if state.statuses else 200
            result: Any = state.updates if self.path.endswith("/getUpdates") else {}
            body = json.dumps({"ok": status == 200, "result": result}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.base = f"http://127.0.0.1:{server.server_port}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def send(tmp_path: Path, fake: Fake, event: str = "info", text: str = "hi", **kw: Any) -> int:
    env = kw.pop("environ", BASE_ENV)
    return int(
        notify.notify(
            event, text, root=tmp_path, environ=env, api_base=fake.base, sleep=lambda _: None, **kw
        )
    )


def test_send_success_and_failure(
    tmp_path: Path, fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    assert send(tmp_path, fake, "qa_pass", "all green", ref="TASK-006") == 0
    assert capsys.readouterr().out.strip() == "sent"
    path, form = fake.requests[0]
    assert path == f"/bot{TOKEN}/sendMessage"
    assert form["chat_id"] == CHAT and "parse_mode" not in form
    assert form["text"] == "🟢 qa_pass · TASK-006\nall green"
    # failure: two attempts then exit 2; best-effort exits 0 with a warning
    fake.statuses = [500, 500]
    assert send(tmp_path, fake, "info", "other") == 2
    assert len(fake.requests) == 3
    fake.statuses = [500, 500]
    assert send(tmp_path, fake, "info", "other2", best_effort=True) == 0
    assert "warning" in capsys.readouterr().err
    # one retry that succeeds
    fake.statuses = [503]
    assert send(tmp_path, fake, "info", "third") == 0
    assert capsys.readouterr().out.strip() == "sent"


def test_no_secret_leak(tmp_path: Path, fake: Fake, capsys: pytest.CaptureFixture[str]) -> None:
    env = {**BASE_ENV, "TAIGA_PASSWORD": "hunter2-hunter2", "TAIGA_USERNAME": "owner-login"}
    # refused: secret value, token shape, bearer, password=
    for text in (
        "x hunter2-hunter2 y",
        f"token {TOKEN}",
        "Authorization: Bearer abc.def",
        "password=foo",
    ):
        assert send(tmp_path, fake, "info", text, environ=env) == 3
    assert fake.requests == []
    # transport failure with the token embedded in the URL of the exception
    fake.base = f"http://127.0.0.1:1/{TOKEN}"
    assert send(tmp_path, fake, "info", "hello", environ=env) == 2
    out = capsys.readouterr()
    combined = out.out + out.err
    for secret in (TOKEN, CHAT, "hunter2-hunter2", "owner-login", "AbCdEfGhIjKl"):
        assert secret not in combined
    assert "refused" in combined and "x hunter2" not in combined
    state = tmp_path / ".local" / "run"
    for file in state.glob("*"):
        content = file.read_text()
        assert TOKEN not in content and CHAT not in content and "hello" not in content


def test_dry_run_and_missing_config(
    tmp_path: Path, fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    assert send(tmp_path, fake, "blocked", "need input", ref="FL-020", dry_run=True) == 0
    assert capsys.readouterr().out == "🔴 ACTION NEEDED · blocked · FL-020\nneed input\n"
    assert send(tmp_path, fake, "info", "x", environ={**BASE_ENV, "NOTIFY_DRY_RUN": "1"}) == 0
    assert fake.requests == []
    capsys.readouterr()
    assert send(tmp_path, fake, "info", "x", environ={"TELEGRAM_BOT_TOKEN": TOKEN}) == 2
    err = capsys.readouterr().err
    assert err.strip() == "error: missing configuration keys: TELEGRAM_CHAT_ID"
    assert send(tmp_path, fake, "info", "x", environ={}, best_effort=True) == 0
    assert "TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID" in capsys.readouterr().err


def test_dedupe_limits_vocabulary(
    tmp_path: Path, fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    now = [1000.0]

    def go(text: str, event: str = "info") -> int:
        return send(tmp_path, fake, event, text, ref="FL-020", clock=lambda: now[0])

    assert go("same") == 0 and go("same") == 0
    assert len(fake.requests) == 1
    assert "suppressed" in capsys.readouterr().out
    assert go("different") == 0 and len(fake.requests) == 2
    now[0] += 61
    assert go("same") == 0 and len(fake.requests) == 3
    state = tmp_path / ".local" / "run" / "notify.json"
    assert (state.stat().st_mode & 0o777) == 0o600
    assert "same" not in state.read_text()
    # truncation, control characters, vocabulary
    assert go("a\x00b\x1b[31m\nc" + "z" * 2000) == 0
    sent = fake.requests[-1][1]["text"].split("\n", 1)[1]
    assert len(sent) == 1000 and sent.endswith("…")
    assert not re.search(r"[\x00-\x1f\x7f]", sent)
    assert send(tmp_path, fake, "bogus", "x") == 2
    assert "unknown event" in capsys.readouterr().err
    assert set(notify.EVENTS) == {
        "started", "progress", "handoff", "qa_pass", "qa_fail", "repair",
        "blocked", "decision_needed", "merged", "released", "cleanup", "info",
    }  # fmt: skip


def test_icons_and_action_marker() -> None:
    fmt = notify.format_message
    for event in ("started", "qa_pass", "merged", "released"):
        assert fmt(event, "t", "FL-1").startswith(f"🟢 {event} · FL-1\n")
    for event in ("progress", "handoff", "repair", "cleanup"):
        assert fmt(event, "t").startswith(f"🔵 {event}\n")
    assert fmt("info", "t").startswith("⚪ info\n")
    for event in ("decision_needed", "blocked", "qa_fail"):
        assert fmt(event, "t", "TASK-006").startswith(f"🔴 ACTION NEEDED · {event} · TASK-006\n")
    assert fmt("info", "t", "FL-020", action=True).startswith("🔴 ACTION NEEDED · info · FL-020")


def test_inbox_filters_chat_and_commands(
    tmp_path: Path, fake: Fake, capsys: pytest.CaptureFixture[str]
) -> None:
    def upd(uid: int, chat: int, text: str) -> dict[str, Any]:
        return {"update_id": uid, "message": {"chat": {"id": chat}, "text": text}}

    def run(env: dict[str, str]) -> int:
        return int(
            notify.inbox_once(
                root=tmp_path,
                environ=env,
                api_base=fake.base,
                sleep=lambda _: None,
                clock=lambda: 5.0,
            )
        )

    assert run(BASE_ENV) == 3  # disabled by default
    assert "TELEGRAM_INBOX=1" in capsys.readouterr().err
    assert fake.requests == []
    env = {**BASE_ENV, "TELEGRAM_INBOX": "1"}
    fake.updates = [
        upd(10, int(CHAT), "/status"),
        upd(11, 999, "/approve FL-020"),  # other chat
        upd(12, int(CHAT), "/approve FL-020"),
        upd(13, int(CHAT), "/approve rm -rf"),  # bad id
        upd(14, int(CHAT), "/note " + "n" * 900 + "\x07"),
        upd(15, int(CHAT), "run ls"),  # free text, not a command
        upd(16, int(CHAT), "/reject TASK-006"),
    ]
    assert run(env) == 0
    inbox = tmp_path / ".local/run/inbox.jsonl"
    lines = [json.loads(x) for x in inbox.read_text().splitlines()]
    assert [x["command"] for x in lines] == ["status", "approve", "note", "reject"]
    assert lines[1]["id"] == "FL-020" and len(lines[2]["note"]) == 500
    assert [x["update_id"] for x in lines] == [10, 12, 14, 16]  # chat 999 never logged
    replies = [r for r in fake.requests if r[0].endswith("/sendMessage")]
    assert len(replies) == 4 and all(r[1]["chat_id"] == CHAT for r in replies)
    offset = json.loads((tmp_path / ".local/run/notify-offset.json").read_text())
    assert offset == {"offset": 17}
    # second poll sends the persisted offset
    fake.updates = []
    assert run(env) == 0
    assert fake.requests[-1][1]["offset"] == "17"
    assert inbox.stat().st_mode & 0o777 == 0o600

"""Send short Telegram status messages and (optionally) collect owner commands.

    python scripts/notify.py --event qa_pass --ref TASK-006 "QA passed"
    python scripts/notify.py --event decision_needed --ref FL-020 "Pick option A or B"
    python scripts/notify.py inbox --once

Stdlib only. Configuration comes from ``scripts/toolenv.py`` (TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID, optional TELEGRAM_INBOX). Secret values never reach stdout, stderr, error text
or saved state. Exit codes: 0 ok, 2 send/config failure, 3 refused or disabled.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import toolenv  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
API_BASE = "https://api.telegram.org"
EVENTS = (
    "started",
    "progress",
    "handoff",
    "qa_pass",
    "qa_fail",
    "repair",
    "blocked",
    "decision_needed",
    "merged",
    "released",
    "cleanup",
    "info",
)
ACTION_EVENTS = frozenset({"decision_needed", "blocked", "qa_fail"})
ICONS = {
    "started": "🟢",
    "qa_pass": "🟢",
    "merged": "🟢",
    "released": "🟢",
    "progress": "🔵",
    "handoff": "🔵",
    "repair": "🔵",
    "cleanup": "🔵",
    "info": "⚪",
}
ACTION_LABEL = "🔴 ACTION NEEDED"
MAX_TEXT = 1000
MAX_NOTE = 500
DEDUPE_SECONDS = 60
TIMEOUT = 10
ATTEMPTS = 2
MAX_RETRY_AFTER = 5.0
MIN_REFUSE_LEN = 6  # shorter credential values (e.g. a small chat id) are redacted, not refused
SECRET_PATTERNS = (
    re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}"),
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"password\s*=", re.IGNORECASE),
)
_ID = re.compile(r"^(?:FL|TASK)-\d{3}$")
_REF = re.compile(r"^[A-Za-z0-9._-]{1,40}$")
_TOKEN_SHAPE = re.compile(r"\d{5,}:[A-Za-z0-9_-]{30,}")

Sleep = Callable[[float], None]
Clock = Callable[[], float]


class NotifyError(Exception):
    """Transport failure; message is already redacted."""


def _retry_after(data: Any) -> float | None:
    params = data.get("parameters") if isinstance(data, dict) else None
    value = params.get("retry_after") if isinstance(params, dict) else None
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return min(float(value), MAX_RETRY_AFTER)
    return None


def sanitize(text: str, limit: int = MAX_TEXT) -> str:
    """Strip control characters (newlines/tabs become spaces), collapse space, truncate."""
    cleaned = "".join(
        " " if ch in "\r\n\t" else ch
        for ch in text
        if ch in "\r\n\t" or unicodedata.category(ch) not in {"Cc", "Cf", "Cs", "Co", "Cn"}
    )
    cleaned = re.sub(r" {2,}", " ", cleaned).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


def redact(text: str, secrets: Sequence[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "[redacted]")
    return _TOKEN_SHAPE.sub("[redacted]", text)


def is_action(event: str, action: bool) -> bool:
    return action or event in ACTION_EVENTS


def format_message(event: str, text: str, ref: str | None = None, action: bool = False) -> str:
    if event not in EVENTS:
        raise ValueError(f"unknown event (allowed: {', '.join(EVENTS)})")
    head = f"{ACTION_LABEL} · {event}" if is_action(event, action) else f"{ICONS[event]} {event}"
    head += f" · {ref}" if ref else ""
    return f"{head}\n{sanitize(text)}"


def refusal_reason(message: str, secrets: Sequence[str]) -> str | None:
    if any(len(s) >= MIN_REFUSE_LEN and s in message for s in secrets):
        return "message contains a configured secret value"
    if any(p.search(message) for p in SECRET_PATTERNS):
        return "message contains a secret-like pattern"
    return None


def _write_private(path: Path, data: str, append: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if append else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "a" if append else "w", encoding="utf-8") as handle:
        handle.write(data)
    path.chmod(0o600)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _is_duplicate(state: Path, key: str, now: float) -> bool:
    data = _read_json(state)
    seen: dict[str, float] = {}
    if isinstance(data, dict):
        seen = {k: v for k, v in data.items() if isinstance(v, (int, float))}
    return key in seen and now - seen[key] < DEDUPE_SECONDS


def _record(state: Path, key: str, now: float) -> None:
    data = _read_json(state)
    seen: dict[str, float] = {}
    if isinstance(data, dict):
        seen = {
            k: float(v)
            for k, v in data.items()
            if isinstance(v, (int, float)) and now - v < DEDUPE_SECONDS
        }
    seen[key] = now
    _write_private(state, json.dumps(seen))


def _call(
    api_base: str,
    token: str,
    method: str,
    params: Mapping[str, str],
    secrets: Sequence[str],
    sleep: Sleep,
    attempts: int = ATTEMPTS,
) -> dict[str, Any]:
    if not api_base.startswith(("https://", "http://")):
        raise NotifyError("api base must be http(s)")
    url = f"{api_base.rstrip('/')}/bot{token}/{method}"
    body = urllib.parse.urlencode(params).encode("utf-8")
    last = "unknown error"
    delay: float | None = None
    for attempt in range(attempts):
        if attempt:
            sleep(delay if delay is not None else 1.0 * attempt)
        delay = None
        try:
            request = urllib.request.Request(url, data=body, method="POST")  # noqa: S310
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, dict) and payload.get("ok") is True:
                return payload
            last = "Telegram API rejected the request"
            delay = _retry_after(payload)
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
            if exc.code == 429:
                try:
                    delay = _retry_after(json.loads(exc.read().decode("utf-8")))
                except (OSError, ValueError):
                    delay = None
        except (urllib.error.URLError, OSError, ValueError, http.client.HTTPException) as exc:
            last = f"{type(exc).__name__}: {exc}"
        except Exception as exc:  # noqa: BLE001 - never leak a traceback with the token
            last = type(exc).__name__
    raise NotifyError(redact(last, [*secrets, token]))


def _missing(values: Mapping[str, str], keys: Sequence[str]) -> list[str]:
    return [k for k in keys if not values.get(k)]


def notify(
    event: str,
    text: str,
    ref: str | None = None,
    action: bool = False,
    best_effort: bool = False,
    *,
    dry_run: bool = False,
    root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
    api_base: str = API_BASE,
    sleep: Sleep = time.sleep,
    clock: Clock = time.time,
) -> int:
    """Send one message. Returns the process exit code; prints only redacted output."""
    env = os.environ if environ is None else environ
    values = toolenv.load(root, env)
    secrets = toolenv.secret_values(values)
    fail = 0 if best_effort else 2

    def report(msg: str, code: int) -> int:
        stream = sys.stdout if code == 0 and msg.startswith(("sent", "suppressed")) else sys.stderr
        print(redact(msg, secrets), file=stream)
        return code

    if ref is not None and not _REF.match(ref):
        return report("error: invalid --ref (use letters, digits, . _ -; max 40)", 2)
    try:
        message = format_message(event, text, ref, action)
    except ValueError as exc:
        return report(f"error: {exc}", 2)
    reason = refusal_reason(message, secrets)
    if reason:
        return report(f"refused: {reason}", 3)
    if dry_run or env.get("NOTIFY_DRY_RUN") == "1":
        print(message)
        return 0
    missing = _missing(values, ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))
    if missing:
        label = "warning" if best_effort else "error"
        return report(f"{label}: missing configuration keys: {', '.join(missing)}", fail)
    state = root / ".local" / "run" / "notify.json"
    digest = hashlib.sha256(f"{event}\0{ref or ''}\0{message}".encode()).hexdigest()
    now = clock()
    if _is_duplicate(state, digest, now):
        return report("suppressed (duplicate within 60 s)", 0)
    try:
        _call(
            api_base,
            values["TELEGRAM_BOT_TOKEN"],
            "sendMessage",
            {"chat_id": values["TELEGRAM_CHAT_ID"], "text": message},
            secrets,
            sleep,
        )
    except NotifyError as exc:
        label = "warning" if best_effort else "error"
        return report(f"{label}: send failed: {exc}", fail)
    try:
        _record(state, digest, now)
    except OSError:
        pass  # dedupe is best effort; the message was sent
    return report("sent", 0)


def _parse_command(text: str, secrets: Sequence[str] = ()) -> dict[str, str] | None:
    parts = text.strip().split(None, 1)
    if not parts:
        return None
    if parts[0].startswith("/"):
        parts[0] = parts[0].split("@", 1)[0]
    cmd, arg = parts[0], (parts[1].strip() if len(parts) > 1 else "")
    if cmd in ("/status", "/pause", "/resume") and not arg:
        return {"command": cmd[1:]}
    if cmd in ("/approve", "/reject") and _ID.match(arg):
        return {"command": cmd[1:], "id": arg}
    if cmd == "/note":
        note = sanitize(arg, MAX_NOTE)
        if note and refusal_reason(note, secrets) is None:
            return {"command": "note", "note": note}
    return None


def inbox_once(
    *,
    root: Path = ROOT,
    environ: Mapping[str, str] | None = None,
    api_base: str = API_BASE,
    sleep: Sleep = time.sleep,
    clock: Clock = time.time,
) -> int:
    """Poll once. Stores accepted commands only; never executes anything."""
    env = os.environ if environ is None else environ
    values = toolenv.load(root, env)
    secrets = toolenv.secret_values(values)

    def err(msg: str, code: int) -> int:
        print(redact(msg, secrets), file=sys.stderr)
        return code

    if values.get("TELEGRAM_INBOX") != "1":
        return err("inbox disabled: set TELEGRAM_INBOX=1", 3)
    missing = _missing(values, ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"))
    if missing:
        return err(f"error: missing configuration keys: {', '.join(missing)}", 2)
    token, chat = values["TELEGRAM_BOT_TOKEN"], values["TELEGRAM_CHAT_ID"]
    run = root / ".local" / "run"
    offset_file = run / "notify-offset.json"
    stored = _read_json(offset_file)
    offset = stored.get("offset") if isinstance(stored, dict) else None
    params = {"timeout": "0", "allowed_updates": '["message"]'}
    if isinstance(offset, int):
        params["offset"] = str(offset)
    try:
        payload = _call(api_base, token, "getUpdates", params, secrets, sleep)
    except NotifyError as exc:
        return err(f"error: getUpdates failed: {exc}", 2)
    updates = payload.get("result")
    if not isinstance(updates, list):
        return err("error: unexpected getUpdates response", 2)
    accepted = 0
    next_offset: int | None = None
    for update in updates:
        if not isinstance(update, dict) or not isinstance(update.get("update_id"), int):
            continue
        uid: int = update["update_id"]
        next_offset = max(next_offset or 0, uid + 1)
        message = update.get("message")
        if not isinstance(message, dict):
            continue
        chat_obj = message.get("chat")
        if not isinstance(chat_obj, dict) or str(chat_obj.get("id")) != chat:
            continue  # other chats: skipped, not logged, no reply
        text = message.get("text")
        parsed = _parse_command(text, secrets) if isinstance(text, str) else None
        if parsed is None:
            continue
        record = {"ts": int(clock()), "update_id": uid, **parsed}
        _write_private(run / "inbox.jsonl", json.dumps(record, ensure_ascii=False) + "\n", True)
        accepted += 1
        try:
            _call(
                api_base,
                token,
                "sendMessage",
                {
                    "chat_id": chat,
                    "text": f"⚪ received /{parsed['command']} (stored, not executed)",
                },
                secrets,
                sleep,
            )
        except NotifyError as exc:
            print(redact(f"warning: reply failed: {exc}", secrets), file=sys.stderr)
    if next_offset is not None:
        _write_private(offset_file, json.dumps({"offset": next_offset}))
    print(f"inbox: {accepted} command(s) stored")
    return 0


def _fatal(exc: Exception, code: int) -> None:
    secrets: list[str] = []
    try:
        secrets = toolenv.secret_values(toolenv.load(ROOT, os.environ))
    except Exception:  # noqa: BLE001, S110
        pass
    secrets += [v for k, v in os.environ.items() if k == "TELEGRAM_BOT_TOKEN" and v]
    line = redact(f"{'warning' if code == 0 else 'error'}: {type(exc).__name__}", secrets)
    print(line, file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    if args_in and args_in[0] == "inbox":
        sub = argparse.ArgumentParser(prog="notify.py inbox")
        sub.add_argument("--once", action="store_true", required=True)
        sub.parse_args(args_in[1:])
        try:
            return inbox_once()
        except Exception as exc:  # noqa: BLE001 - last resort, one redacted line
            _fatal(exc, 2)
            return 2
    parser = argparse.ArgumentParser(
        prog="notify.py", description="Send a Telegram status message."
    )
    parser.add_argument("--event", choices=EVENTS, default="info")
    parser.add_argument("--ref")
    parser.add_argument("--action", action="store_true", help="mark as action required")
    parser.add_argument("--dry-run", action="store_true", help="print the text, no network")
    parser.add_argument("--best-effort", action="store_true", help="warn instead of failing")
    parser.add_argument("text", nargs="+", metavar="TEXT")
    args = parser.parse_args(args_in)
    try:
        return notify(
            args.event,
            " ".join(args.text),
            ref=args.ref,
            action=args.action,
            best_effort=args.best_effort,
            dry_run=args.dry_run,
        )
    except Exception as exc:  # noqa: BLE001 - last resort, one redacted line
        _fatal(exc, 0 if args.best_effort else 2)
        return 0 if args.best_effort else 2


if __name__ == "__main__":
    raise SystemExit(main())

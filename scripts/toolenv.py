"""Credential loader for repository tooling (notify, Taiga sync).

Reads the untracked repo-root ``.env`` (in a linked Git worktree: the main checkout's ``.env``)
and returns only keys that start with ``TELEGRAM_`` or ``TAIGA_``. Real environment variables
override file values. Values are never printed by this module; ``secret_values`` lists the
values that every output path must redact.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PREFIXES = ("TELEGRAM_", "TAIGA_")
# Keys whose values are credentials or identifiers that must never be echoed or transmitted.
SECRET_MARKERS = ("TOKEN", "PASSWORD", "CHAT_ID", "USERNAME")
_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_INLINE_COMMENT = re.compile(r"\s+#.*$")
_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\"}


def _parse_value(raw: str) -> str:
    text = raw.strip()
    if text[:1] in ("'", '"'):
        quote = text[0]
        out: list[str] = []
        i = 1
        while i < len(text):
            ch = text[i]
            if ch == "\\" and quote == '"' and i + 1 < len(text) and text[i + 1] in _ESCAPES:
                out.append(_ESCAPES[text[i + 1]])
                i += 2
                continue
            if ch == "\\" and quote == "'" and i + 1 < len(text) and text[i + 1] in "\\'":
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                return "".join(out)  # anything after the closing quote is ignored
            out.append(ch)
            i += 1
        return text[1:]  # unterminated quote: keep the rest verbatim
    return _INLINE_COMMENT.sub("", text).strip()


def parse_env_text(text: str) -> dict[str, str]:
    """Parse dotenv text into the tooling-prefixed keys only."""
    values: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = _LINE.match(line)
        if match and match.group(1).startswith(PREFIXES):
            values[match.group(1)] = _parse_value(match.group(2))
    return values


def env_file_path(root: Path = ROOT) -> Path:
    """``root/.env``, else the main checkout's ``.env`` when ``root`` is a linked worktree."""
    own = root / ".env"
    if own.is_file():
        return own
    try:
        result = subprocess.run(  # noqa: S603
            ["git", "rev-parse", "--git-common-dir"],  # noqa: S607
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return own
    common = result.stdout.strip()
    if result.returncode != 0 or not common:
        return own
    common_dir = Path(common)
    if not common_dir.is_absolute():
        common_dir = root / common_dir
    candidate = common_dir.resolve().parent / ".env"
    return candidate if candidate.is_file() else own


def load(root: Path = ROOT, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Tooling keys from the ``.env`` file, overridden by the real environment."""
    path = env_file_path(root)
    values: dict[str, str] = {}
    if path.is_file():
        values = parse_env_text(path.read_text(encoding="utf-8", errors="replace"))
    env = os.environ if environ is None else environ
    for key, value in env.items():
        if key.startswith(PREFIXES):
            values[key] = value
    return values


def secret_values(values: Mapping[str, str]) -> list[str]:
    """Non-empty credential values, longest first, for redaction and refusal checks."""
    found = {v for k, v in values.items() if v and any(m in k for m in SECRET_MARKERS)}
    return sorted(found, key=len, reverse=True)

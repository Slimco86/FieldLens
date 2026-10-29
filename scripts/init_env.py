"""Create or extend the untracked repository-root ``.env`` for local development.

    uv run python scripts/init_env.py

Idempotent: a missing ``.env`` is created with mode 0600 from ``.env.example``; an existing one
only receives the keys it lacks, appended after its unchanged bytes. The database password is
generated (URL-safe) only when ``POSTGRES_PASSWORD`` is absent and is never overwritten.
Output names added keys only. Values (including any existing ``MODEL_API_KEY``) are never
printed, logged, parsed for output or transmitted.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_KEY = "POSTGRES_PASSWORD"
_KEY_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_MARKER = "# --- added by scripts/init_env.py ---\n"


def _example_blocks(example: str) -> list[tuple[str, list[str], str]]:
    """(key, comment lines directly above it, key line) for every key in the example."""
    blocks: list[tuple[str, list[str], str]] = []
    comments: list[str] = []
    for line in example.splitlines():
        if line.startswith("#"):
            comments.append(line)
            continue
        match = _KEY_LINE.match(line)
        if match:
            blocks.append((match.group(1), comments, line))
        comments = []
    return blocks


def _present_keys(data: bytes) -> set[str]:
    keys: set[str] = set()
    for raw in data.decode("utf-8", errors="replace").splitlines():
        match = _KEY_LINE.match(raw)
        if match:
            keys.add(match.group(1))
    return keys


def bootstrap(env_path: Path, example_path: Path) -> tuple[list[str], bool]:
    """Add missing keys. Returns (added key names, whether an existing file mode was tightened)."""
    blocks = _example_blocks(example_path.read_text(encoding="utf-8"))
    created = not env_path.exists()
    existing = b"" if created else env_path.read_bytes()
    present = _present_keys(existing)
    missing = [block for block in blocks if block[0] not in present]
    if created:
        os.close(os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    tightened = False
    if stat.S_IMODE(env_path.stat().st_mode) != 0o600:
        env_path.chmod(0o600)
        tightened = not created
    if not missing:
        return [], tightened
    addition = _MARKER
    for key, comments, line in missing:
        if key == GENERATED_KEY:
            line = f"{GENERATED_KEY}={secrets.token_urlsafe(32)}"
        addition += "".join(f"{c}\n" for c in comments) + line + "\n"
    with env_path.open("ab") as handle:  # append only: existing bytes are never rewritten
        if existing and not existing.endswith(b"\n"):
            handle.write(b"\n")
        handle.write(addition.encode("utf-8"))
    return [key for key, _, _ in missing], tightened


def main(root: Path = ROOT) -> int:
    example = root / ".env.example"
    if not example.is_file():
        print(f"{example} not found", file=sys.stderr)
        return 1
    added, tightened = bootstrap(root / ".env", example)
    if tightened:
        print(".env permissions tightened to 0600")
    if added:
        print("added keys to .env: " + ", ".join(added))
    else:
        print(".env already has every key; nothing changed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

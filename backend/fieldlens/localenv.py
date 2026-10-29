"""Repository-root ``.env`` discovery, independent of the current working directory.

Only ``FIELDLENS_*`` and ``POSTGRES_*`` keys are ever parsed for scripts and tests; any other
key in the file (for example the provider credential) is skipped before parsing and never
enters a process environment, log or message.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
BOOTSTRAP_COMMAND = "uv run python scripts/init_env.py"
ALLOWED_PREFIXES = ("FIELDLENS_", "POSTGRES_")

_KEY_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def load_local_env(path: Path | None = None) -> dict[str, str]:
    """``FIELDLENS_*``/``POSTGRES_*`` values (with ``${VAR}`` interpolation) from ``.env``.

    Returns an empty mapping when the file is absent. Callers decide whether a missing
    key is an error and must name :data:`BOOTSTRAP_COMMAND`.
    """
    env_path = ENV_FILE if path is None else path
    if not env_path.is_file():
        return {}
    kept: list[str] = []
    for line in env_path.read_text(encoding="utf-8").splitlines():
        match = _KEY_LINE.match(line)
        if match and match.group(1).startswith(ALLOWED_PREFIXES):
            kept.append(line)
    values = dotenv_values(stream=io.StringIO("\n".join(kept)), interpolate=True)
    return {k: v for k, v in values.items() if v is not None}

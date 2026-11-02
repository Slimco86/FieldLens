"""Operator tool for the storage root identity (TASK-070).

    uv run python scripts/storage_root.py status
    uv run python scripts/storage_root.py adopt            # prompts for a typed confirmation
    uv run python scripts/storage_root.py adopt --confirm <database-name>

``adopt`` binds the configured database and the configured storage root to one identity. It is
the only way to re-point a database at a different root. It never moves, deletes or rewrites
original files. Database passwords are never printed.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from fieldlens.config import get_settings
from fieldlens.evidence import root_guard
from fieldlens.evidence.storage import BlobStore
from fieldlens.persistence.session import create_db_engine, create_session_factory


def _database_name(url: str) -> str:
    return url.rsplit("/", 1)[-1].split("?", 1)[0]


def run(
    argv: list[str],
    *,
    prompt: Callable[[str], str] = input,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(prog="storage_root")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show whether this root matches the database")
    adopt = sub.add_parser("adopt", help="bind this database and storage root to one identity")
    adopt.add_argument("--confirm", help="the database name, typed non-interactively")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = create_db_engine(settings)
    if engine is None:
        out("error: no database configured")
        return 2
    factory = create_session_factory(engine)
    store = BlobStore(Path(settings.storage_root))
    try:
        if args.command == "status":
            st = root_guard.evaluate(factory, store)
            out(f"storage root: {store.root}")
            out("match: yes" if st.ok else f"match: NO ({st.reason})")
            return 0 if st.ok else 1
        database = _database_name(engine.url.render_as_string(hide_password=True))
        typed = args.confirm
        if typed is None:
            out(f"This binds database {database} to storage root {store.root}.")
            out("Originals are not moved or deleted. Files stored under another root stay there.")
            try:
                typed = prompt(f"Type the database name ({database}) to continue: ")
            except EOFError:
                out("aborted: no confirmation was entered")
                return 1
        if typed != database:
            out("aborted: confirmation did not match the database name")
            return 1
        root_id = root_guard.adopt(factory, store)
        out(f"adopted: root identity {root_id}")
        return 0
    finally:
        engine.dispose()


def main() -> int:
    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())

"""Export the deterministic OpenAPI document (routes + every registered public DTO).

    uv run python scripts/export_contracts.py --out frontend/.contracts/openapi.json

The frontend turns this into ``frontend/src/api/generated.ts`` with ``openapi-typescript``.
The app is built with an explicit, database-less configuration; no secrets are read.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from fieldlens.app import create_app  # noqa: E402
from fieldlens.config import Settings  # noqa: E402


def build_openapi() -> str:
    settings = Settings(
        _env_file=None, database_url=None, frontend_dist=REPO / ".local" / "no-frontend-dist"
    )
    return json.dumps(create_app(settings).openapi(), indent=2, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="write here instead of stdout")
    args = parser.parse_args()
    document = build_openapi()
    if args.out is None:
        sys.stdout.write(document)
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(document, encoding="utf-8")


if __name__ == "__main__":
    main()

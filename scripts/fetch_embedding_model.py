"""One-off, explicit download of the pinned local embedding model (never run by tests).

    uv run python scripts/fetch_embedding_model.py [--dir PATH]

Downloads only the files pinned in ``fieldlens.retrieval.model_manifest`` from the public
model host at the pinned revision, verifies every SHA-256 and moves them into place only when
all match. No project data, identifier or credential is sent; the requests are plain GETs of
public files. The target defaults to the gitignored ``.local/fieldlens/models``.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fieldlens.retrieval import model_manifest as mm  # noqa: E402

BASE = "https://huggingface.co/{repo}/resolve/{rev}/{name}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=mm.DEFAULT_DIR)
    args = parser.parse_args()
    target: Path = args.dir
    if mm.verify_model_dir(target) is None:
        print(f"model already present and verified: {target}")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".fetch-") as tmp:
        staging = Path(tmp)
        for name, expected in mm.FILES.items():
            url = BASE.format(repo=mm.SOURCE_REPO, rev=mm.SOURCE_REVISION, name=name)
            if not url.startswith("https://huggingface.co/"):
                raise SystemExit("refusing a non-pinned host")
            dest = staging / name
            with urllib.request.urlopen(url, timeout=120) as resp, open(dest, "wb") as out:  # noqa: S310
                while block := resp.read(1024 * 1024):
                    out.write(block)
            actual = mm.sha256_of(dest)
            if actual != expected:
                print(f"HASH MISMATCH {name}: expected {expected}, got {actual}", file=sys.stderr)
                return 1
            print(f"ok {name} {dest.stat().st_size} bytes sha256 {actual}")
        target.mkdir(parents=True, exist_ok=True)
        for name in mm.FILES:
            (staging / name).replace(target / name)
    reason = mm.verify_model_dir(target)
    if reason is not None:
        print(reason, file=sys.stderr)
        return 1
    print(f"installed {mm.MODEL_ID} ({mm.SOURCE_REPO}@{mm.SOURCE_REVISION}) -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

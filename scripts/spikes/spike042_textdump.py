"""Dump per-page text layers to gitignored scratch (offline)."""

from __future__ import annotations

import json
import sys

from pypdf import PdfReader
from spike042_common import SCRATCH, doc_path


def main(pv: str) -> None:
    rd = PdfReader(str(doc_path(pv)))
    texts = [(p.extract_text() or "") for p in rd.pages]
    (SCRATCH / f"text_{pv}.json").write_text(json.dumps(texts))


if __name__ == "__main__":
    main(sys.argv[1])

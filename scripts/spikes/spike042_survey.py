"""Offline survey (no model, no network): pages, text layer, images, keyword triage."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

from pypdf import PdfReader
from spike042_common import DOCS, SCRATCH, doc_path

KEYWORDS = (
    "tubing|packer|esp|pump|gas lift|completion string|liner|casing|nipple|sssv|perforat|"
    "schematic|x-over|crossover|mandrel|wellhead|christmas|tree|bearing|motor|seal section|"
    "sleeve|plug|polished bore|pbr|hanger|screen|gravel|safety valve|dhsv|tailpipe|wireline entry"
)
KW = re.compile(KEYWORDS, re.I)


def main() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out: dict[str, object] = {}
    for pv in DOCS:
        rd = PdfReader(str(doc_path(pv)))
        pages: list[dict[str, Any]] = []
        for i, page in enumerate(rd.pages, 1):
            try:
                text = page.extract_text() or ""
            except Exception as exc:  # noqa: BLE001 - survey only
                text = ""
                err = type(exc).__name__
            else:
                err = ""
            try:
                n_img = len(page.images)
            except Exception:  # noqa: BLE001
                n_img = -1
            hits = sorted({m.group(0).lower() for m in KW.finditer(text)})
            w, h = float(page.mediabox.width), float(page.mediabox.height)
            pages.append(
                {
                    "page": i,
                    "w": round(w),
                    "h": round(h),
                    "rot": int(page.get("/Rotate", 0) or 0),
                    "text_chars": len(text.strip()),
                    "images": n_img,
                    "kw": hits,
                    "err": err,
                }
            )
        out[pv] = {"file": DOCS[pv][1], "well": DOCS[pv][0], "n_pages": len(pages), "pages": pages}
        n = len(pages)
        txt = sum(1 for p in pages if p["text_chars"] > 50)
        img = sum(1 for p in pages if p["images"] > 0)
        print(f"{pv} {DOCS[pv][0]} pages={n} text_pages={txt} image_pages={img}", file=sys.stderr)
    (SCRATCH / "survey.json").write_text(json.dumps(out))


if __name__ == "__main__":
    main()

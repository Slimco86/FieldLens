"""OCR the raster pictures extracted from a legacy .doc (TASK-030 phase A; counts only).

Reads PNG/JPEG blips written by ocr_doc_inspect.py (gitignored scratch), runs RapidOCR locally
and prints per-picture counts: tokens, mean confidence, equipment keyword hits, numeric tokens and
how many F-5 as-installed reference numbers (PV-21 p.49/48) appear. Never prints picture text.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ocr_common import numbers_in, reference_tokens
from ocr_run import make_rapid3
from PIL import Image  # type: ignore[import-not-found,unused-ignore]

KEYWORDS = ("tubing", "packer", "casing", "liner", "hanger", "pump", "perf", "mandrel", "valve")


def main(folder: str) -> None:
    eng = make_rapid3("def")
    ref = set(reference_tokens("PV-21:49")["numbers"]) | set(
        reference_tokens("PV-21:48")["numbers"]
    )
    for p in sorted(Path(folder).iterdir()):
        img = Image.open(p).convert("RGB")
        scale = 2 if max(img.size) < 900 else 1  # small pictures are upscaled for the detector
        if scale > 1:
            img = img.resize((img.width * scale, img.height * scale))
        toks = eng(img)
        text = " ".join(t["t"].lower() for t in toks)
        nums = {n for t in toks for n in numbers_in(t["t"])}
        mean_c = sum(t["c"] for t in toks) / max(len(toks), 1)
        kw = {k: text.count(k) for k in KEYWORDS if text.count(k)}
        print(
            f"{p.name} px={Image.open(p).size} tokens={len(toks)} mean_conf={mean_c:.0f} "
            f"numbers={len(nums)} ref_hits={len(nums & ref)} keywords={kw}"
        )


if __name__ == "__main__":
    main(sys.argv[1])

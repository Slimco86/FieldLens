"""Bounding-box usability check: can an accepted token be located back on the page? (TASK-030 A)

For every reference number that an OCR configuration found, crop the page render at the box
(with padding), rotate it upright by the pass angle and re-read the crop alone with the same
engine family (RapidOCR crops: RapidOCR; Tesseract crops: Tesseract single-line). Pass = the
number is read again from the crop. Line-level engines (RapidOCR) return one box per text line, so
the token's sub-box is interpolated along the line by character offsets for horizontal lines and
checked the same way. This is a self-consistency check, not an independent ground truth.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from collections.abc import Callable
from typing import Any

from ocr_common import REFERENCE_PAGES, SCRATCH, numbers_in, reference_tokens, render
from ocr_score import load, merge


def tess_reader(dpi: int) -> Callable[[Any], str]:
    from tesserocr import PSM, PyTessBaseAPI  # type: ignore[import-not-found,unused-ignore]

    api = PyTessBaseAPI(path=str(SCRATCH / "tessdata" / "fast"), lang="eng", psm=PSM.SINGLE_LINE)
    api.SetVariable("user_defined_dpi", str(dpi))

    def read(img: Any) -> str:
        api.SetImage(img.convert("L"))
        return str(api.GetUTF8Text() or "")

    return read


def rapid_reader() -> Callable[[Any], str]:
    from ocr_run import make_rapid3

    eng = make_rapid3("def")

    def read(img: Any) -> str:
        return " ".join(t["t"] for t in eng(img))

    return read


def sub_box(box: list[float], text: str, number: str) -> list[float]:
    """Interpolate the sub-box of ``number`` inside a horizontal line box by character offsets."""
    m = None
    for cand in re.finditer(r"\d[\d.,/\- ]*\d|\d", text):
        if number in numbers_in(cand.group(0)):
            m = cand
            break
    x0, y0, x1, y1 = box
    if m is None or (y1 - y0) > 1.5 * (x1 - x0) or len(text) < 2:
        return box
    w = (x1 - x0) / len(text)
    return [x0 + w * m.start(), y0, x0 + w * m.end(), y1]


def main() -> None:
    tag, dpi, angles, mc = (
        sys.argv[1],
        int(sys.argv[2]),
        [int(a) for a in sys.argv[3].split(",")],
        float(sys.argv[4]),
    )
    read = rapid_reader() if tag.startswith("rapid") else tess_reader(dpi)
    res: Counter[str] = Counter()
    for pv, page in REFERENCE_PAGES:
        key = f"{pv}:{page}"
        refs = set(reference_tokens(key)["numbers"])
        img = render(pv, page, dpi)
        toks, _ = load(tag, dpi, pv, page, angles)
        seen: set[str] = set()
        for t in merge(toks, mc):
            for n in numbers_in(t["t"]):
                if n not in refs or n in seen:
                    continue
                seen.add(n)
                multi = len(t["t"].split()) > 1
                for label, box in (("line_box", t["b"]), ("token_box", sub_box(t["b"], t["t"], n))):
                    if label == "token_box" and not multi:
                        continue
                    x0, y0, x1, y1 = (int(v) for v in box)
                    pad = 6
                    crop = img.crop(
                        (
                            max(0, x0 - pad),
                            max(0, y0 - pad),
                            min(img.width, x1 + pad),
                            min(img.height, y1 + pad),
                        )
                    )
                    if t["a"]:
                        crop = crop.rotate(t["a"], expand=True)
                    ok = n in set(numbers_in(read(crop)))
                    res[f"{label}_{'ok' if ok else 'fail'}"] += 1
    print(f"{tag} dpi={dpi} angles={angles}:", dict(sorted(res.items())))


if __name__ == "__main__":
    main()

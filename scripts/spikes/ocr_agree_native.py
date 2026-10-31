"""Agreement rule against native text-layer ground truth (TASK-030 phase A; offline).

Pages that have a native text layer AND a saved TASK-042 model image read give a ground truth
that is not agent-read: the numbers printed in the text layer. The page is rendered, OCR'd with
the chosen engine, and each model-read number is classified:
  supported   - the number occurs in the native text layer of that page
  unsupported - it does not (model misread, or the model reformatted/derived it)
and whether OCR confirms it. Rendered text pages are clean, so OCR recall here is an upper bound
for scans; the value of this check is the exact truth for the model-vs-OCR disagreement.
"""

from __future__ import annotations

import glob
import json
import sys
from collections import Counter
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-not-found,unused-ignore]
from ocr_agree import model_values
from ocr_common import SPIKE042_RUNS, num_class, numbers_in, render
from ocr_run import make_rapid3, make_tess
from spike042_common import doc_path

PAGES = [
    ("PV-11", 136),
    ("PV-12", 17),
    ("PV-12", 39),
    ("PV-13", 4),
    ("PV-13", 14),
    ("PV-13", 17),
    ("PV-13", 18),
    ("PV-13", 19),
    ("PV-13", 58),
    ("PV-14", 1),
]


def native_numbers(pv: str, page: int) -> set[str]:
    pdf = pdfium.PdfDocument(str(doc_path(pv)))
    try:
        text = pdf[page - 1].get_textpage().get_text_bounded() or ""
    finally:
        pdf.close()
    return set(numbers_in(text))


def main() -> None:
    engine, variant, dpi = sys.argv[1], sys.argv[2], int(sys.argv[3])
    eng = make_rapid3(variant) if engine == "rapid3" else make_tess("fast", variant, dpi)
    ocr: dict[str, set[str]] = {}
    truth: dict[str, set[str]] = {}
    for pv, page in PAGES:
        key = f"{pv}:{page}"
        truth[key] = native_numbers(pv, page)
        toks = eng(render(pv, page, dpi))
        ocr[key] = {n for t in toks for n in numbers_in(t["t"])}
    # OCR recall of the native numbers, by class
    rec: Counter[str] = Counter()
    tot: Counter[str] = Counter()
    for key, tn in truth.items():
        for n in tn:
            tot[num_class(n)] += 1
            rec[num_class(n)] += n in ocr[key]
    print(
        f"{engine}/{variant} dpi={dpi} OCR recall of native-text numbers:",
        {c: f"{rec[c]}/{tot[c]}" for c in sorted(tot)},
    )
    cm: Counter[str] = Counter()
    rows = []
    for f in sorted(glob.glob(str(SPIKE042_RUNS / "*" / "*_image.json"))):
        base = Path(f).name
        key = f"{base[:5]}:{int(base[7:10])}"
        if key not in truth:
            continue
        mv = model_values(f)
        if mv is None:
            continue
        for v in mv[0] | mv[1]:
            sup = v in truth[key]
            conf = v in ocr[key]
            cm[
                f"{'supported' if sup else 'unsupported'}|{'ocr_confirms' if conf else 'ocr_misses'}"
            ] += 1
            if not sup or not conf:
                rows.append((v, key, Path(f).parent.name, sup, conf))
    print("model values (unique per run file) vs native truth x OCR:", dict(cm))
    for r in rows[:60]:
        print("  ", r)
    out = (
        Path(__file__).resolve().parents[2]
        / ".local"
        / "ocr"
        / f"agree_native_{engine}_{variant}_{dpi}.json"
    )
    out.write_text(json.dumps({"cm": cm, "rows": rows}))


if __name__ == "__main__":
    main()

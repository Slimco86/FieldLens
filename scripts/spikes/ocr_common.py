"""Shared helpers for the TASK-030 phase A OCR evaluation (experiment, not product code).

Offline only. Rendering uses pypdfium2 (spike-only dependency, not in pyproject). All outputs go
to the gitignored ``.local/ocr`` scratch directory. Source documents are read-only.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pypdfium2 as pdfium  # type: ignore[import-not-found,unused-ignore]
from PIL import Image  # type: ignore[import-not-found,unused-ignore]
from spike042_common import ROOT, doc_path  # noqa: F401

SCRATCH = Path(__file__).resolve().parents[2] / ".local" / "ocr"
SPIKE042_RUNS = Path(
    "/home/slimco/code/FieldLens-worktrees/task-042-completion-spike/.local/spike042/runs"
)

# Evaluation pages: reference pages (agent-read) plus three pages without equipment.
REFERENCE_PAGES: list[tuple[str, int]] = [
    ("PV-17", 4),
    ("PV-17", 29),
    ("PV-17", 30),
    ("PV-17", 35),
    ("PV-17", 36),
    ("PV-21", 48),
    ("PV-21", 49),
    ("PV-12", 164),
]
CONTROL_PAGES: list[tuple[str, int]] = [("PV-21", 13), ("PV-21", 50), ("PV-17", 48)]
ALL_PAGES = REFERENCE_PAGES + CONTROL_PAGES


def render(pv: str, page: int, dpi: int) -> Image.Image:
    """Render a 1-based page at dpi (pdfium applies the page rotation flag)."""
    out = SCRATCH / "img" / f"{pv}_p{page:03d}_{dpi}.png"
    if out.exists():
        return Image.open(out).convert("RGB")
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(doc_path(pv)))
    try:
        img: Image.Image = pdf[page - 1].render(scale=dpi / 72).to_pil().convert("RGB")
    finally:
        pdf.close()
    img.save(out)
    return img


# ---- token normalization -------------------------------------------------------------------

_FRAC = r"\d+\s?-\s?\d+/\d+|\d+/\d+"
_NUM = r"\d+(?:[.,]\d+)?"
NUM_RE = re.compile(rf"(?<![\w.])(?:{_FRAC}|{_NUM})(?![\w]*\d)")


def canon_num(raw: str) -> str | None:
    """Canonical string for a numeric token: decimals compared by value, fractions by text."""
    s = raw.strip().replace(" ", "")
    if "/" in s:
        return s
    s = s.replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return format(d.normalize(), "f")


def numbers_in(text: str) -> list[str]:
    """Canonical numeric tokens found in text (depths, sizes, fractions, weights)."""
    out: list[str] = []
    for m in re.finditer(
        r"(?<![\d.,/])(?:\d+\s?-\s?\d+/\d+|\d+/\d+|\d+(?:[.,]\d+)?)(?![\d/]|[.,]\d)", text
    ):
        c = canon_num(m.group(0))
        if c is not None:
            out.append(c)
    return out


def num_class(c: str) -> str:
    if "/" in c:
        return "fraction"
    if "." in c:
        return "decimal"
    return "int>=3" if len(c) >= 3 else "int<3"


def words_in(text: str) -> list[str]:
    return [w.lower() for w in re.findall(r"[A-Za-z][A-Za-z0-9\-]*", text)]


def edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# ---- reference -----------------------------------------------------------------------------


def reference_tokens(key: str) -> dict[str, Any]:
    """Reference numbers and words for a page, from the agent-read spike gold (not human verified)."""
    from spike042_gold import GOLD

    if key not in GOLD:  # control page: no reference items
        return {"numbers": {}, "words": [], "kind": "control"}
    g = GOLD[key]
    nums: dict[str, dict[str, Any]] = {}
    words: set[str] = set()
    for item in g["items"]:
        vals = list(item["keys"]) + [
            v for k, v in item["attrs"].items() if k in ("depth", "od", "id")
        ]
        for v in vals:
            ns = numbers_in(v)
            for n in ns:
                nums.setdefault(n, {"unsure": bool(item["unsure"])})
            if not ns:
                words.update(w for w in words_in(v) if len(w) >= 3)
    for p in g["perforations"]:
        for v in (p["top"], p["bottom"]):
            for n in numbers_in(v):
                nums.setdefault(n, {"unsure": False})
    # A key that is only the integer part of a longer reference number (key "2615" for depth
    # "2615.4") is a labelling artifact of the gold, not a separately printed token: drop it.
    nums = {n: v for n, v in nums.items() if not any(m.startswith(n + ".") for m in nums)}
    return {"numbers": nums, "words": sorted(words), "kind": g["kind"]}

"""Render pages to gitignored PNG scratch with pypdfium2 (spike-only dependency)."""

from __future__ import annotations

import sys
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-not-found,unused-ignore]
from PIL import Image  # type: ignore[import-not-found,unused-ignore]
from spike042_common import SCRATCH, doc_path


def render_page(pv: str, page: int, long_side: int, out: Path | None = None) -> Path:
    """1-based page; long side in pixels (aspect preserved, rotation applied by pdfium)."""
    out = out or SCRATCH / "img" / f"{pv}_p{page:03d}_{long_side}.png"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf = pdfium.PdfDocument(str(doc_path(pv)))
    try:
        pg = pdf[page - 1]
        w, h = pg.get_size()
        scale = long_side / max(w, h)
        img = pg.render(scale=scale).to_pil().convert("RGB")
        img.save(out, optimize=True)
    finally:
        pdf.close()
    return out


def contact_sheet(pv: str, pages: list[int], cell: int, cols: int, out: Path) -> None:
    pdf = pdfium.PdfDocument(str(doc_path(pv)))
    try:
        tiles = []
        for p in pages:
            pg = pdf[p - 1]
            w, h = pg.get_size()
            im = pg.render(scale=cell / max(w, h)).to_pil().convert("RGB")
            tiles.append((p, im))
    finally:
        pdf.close()
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * (cell * 3 // 4 + 4)), "white")
    from PIL import ImageDraw

    d = ImageDraw.Draw(sheet)
    for i, (p, im) in enumerate(tiles):
        x, y = (i % cols) * cell, (i // cols) * (cell * 3 // 4 + 4)
        sheet.paste(im, (x, y))
        d.text((x + 3, y + 3), str(p), fill="red")
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


if __name__ == "__main__":
    if sys.argv[1] == "sheet":
        pv, a, b, cell, cols = sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), 420, 4
        contact_sheet(
            pv, list(range(a, b + 1)), cell, cols, SCRATCH / "sheets" / f"{pv}_{a}-{b}.png"
        )
    else:
        print(render_page(sys.argv[1], int(sys.argv[2]), int(sys.argv[3])))

"""Synthetic PDFs for the candidate tests (no real documents): text-layer pages, rotated text
and image-only (scan-like) pages. Hand-written PDF 1.4, deterministic bytes."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont


@dataclass
class PdfPage:
    lines: list[str] | None = None  # text-layer lines (None: no text)
    scan_lines: list[str] | None = None  # drawn into a raster image (no text layer)
    scan_angle_cw: int = 0  # rotate the raster clockwise inside the page
    content_angle: int = 0  # counter-clockwise rotation of the text block
    page_rotate: int = 0  # /Rotate


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def scan_image(lines: list[str], angle_cw: int = 0) -> bytes:
    image = Image.new("L", (700, 900), 255)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    y = 40
    for line in lines * 3:
        draw.text((40, y), line, fill=0, font=font)
        y += 36
    if angle_cw:
        image = image.rotate(-angle_cw, expand=True, fillcolor=255)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=90)
    return out.getvalue()


def make_pdf(pages: list[PdfPage]) -> bytes:
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")
    pages_obj = add(b"")
    font = add(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    kids: list[int] = []
    for page in pages:
        resources = f"/Font<</F1 {font} 0 R>>"
        ops: list[str] = []
        media = (612, 792)
        if page.lines:
            a = math.radians(page.content_angle)
            c, s = math.cos(a), math.sin(a)
            ops += ["BT", "/F1 14 Tf", f"{c:.4f} {s:.4f} {-s:.4f} {c:.4f} 300 400 Tm"]
            for line in page.lines:
                ops.append(f"({_escape(line)}) Tj 0 -20 Td")
            ops.append("ET")
        if page.scan_lines:
            jpeg = scan_image(page.scan_lines, page.scan_angle_cw)
            with Image.open(io.BytesIO(jpeg)) as probe:
                w, h = probe.size
            img = add(
                f"<</Type/XObject/Subtype/Image/Width {w}/Height {h}/ColorSpace/DeviceGray"
                f"/BitsPerComponent 8/Filter/DCTDecode/Length {len(jpeg)}>>\nstream\n".encode()
                + jpeg
                + b"\nendstream"
            )
            resources += f"/XObject<</Im1 {img} 0 R>>"
            media = (w * 612 // 700 if w else 612, h * 612 // 700)
            ops += ["q", f"{media[0]} 0 0 {media[1]} 0 0 cm", "/Im1 Do", "Q"]
        stream = "\n".join(ops).encode()
        content = add(b"<</Length %d>>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append(
            add(
                f"<</Type/Page/Parent {pages_obj} 0 R/MediaBox[0 0 {media[0]} {media[1]}]"
                f"/Rotate {page.page_rotate}/Contents {content} 0 R/Resources<<{resources}>>>>".encode()
            )
        )
    objects[catalog - 1] = f"<</Type/Catalog/Pages {pages_obj} 0 R>>".encode()
    kid_refs = " ".join(f"{k} 0 R" for k in kids)
    objects[pages_obj - 1] = f"<</Type/Pages/Kids[{kid_refs}]/Count {len(kids)}>>".encode()
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects):
        offsets.append(out.tell())
        out.write(f"{i + 1} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer<</Size {len(objects) + 1}/Root {catalog} 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()


EQUIPMENT_LINES = [
    "Completion string 7 in monobore",
    "Production packer 3064.39 m MD Baker",
    "Tubing hanger Vetco 6-3/8 in XMT",
    "Liner hanger 3095 m MD gas lift mandrel",
]

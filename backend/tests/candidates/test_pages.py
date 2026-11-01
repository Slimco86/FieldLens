"""AX-12: page image tool rendering, cache, orientation (synthetic PDFs, offline)."""

from __future__ import annotations

import asyncio
import hashlib
import io
import threading
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from fieldlens.candidates import pages as pg
from fieldlens.evidence.storage import BlobStore, blob_key
from tests.candidates.pdfs import EQUIPMENT_LINES, PdfPage, make_pdf


def _store(tmp_path: Path, data: bytes) -> tuple[pg.PageRenderer, str, str]:
    store = BlobStore(tmp_path)
    sha = hashlib.sha256(data).hexdigest()
    key = blob_key(uuid4(), sha)
    target = store.path_for(key)
    target.parent.mkdir(parents=True)
    target.write_bytes(data)
    return pg.PageRenderer(store), sha, key


def test_page_image_tool(tmp_path: Path) -> None:
    data = make_pdf([PdfPage(lines=EQUIPMENT_LINES), PdfPage(lines=["second"])])
    r, sha, key = _store(tmp_path, data)
    out = r.render(sha, key, 1)
    assert out.page == 1 and out.page_count == 2 and not out.cache_hit
    assert max(out.width, out.height) == 1600  # default long side
    with Image.open(io.BytesIO(out.data)) as img:
        assert img.mode == "RGB" and img.size == (out.width, out.height)
    assert str(tmp_path) not in repr(out.meta())  # never a filesystem path
    # hard cap, configurable
    assert max(r.render(sha, key, 1, long_side=9999).width, 0) <= 2400
    big = r.render(sha, key, 1, long_side=9999)
    assert max(big.width, big.height) == 2400
    small = r.render(sha, key, 1, long_side=800)
    assert max(small.width, small.height) == 800
    # bounds: 1-based
    for bad in (0, 3, -1):
        with pytest.raises(pg.PageError) as exc:
            r.render(sha, key, bad)
        assert exc.value.code == "page_out_of_range"
    with pytest.raises(pg.PageError):
        r.render(sha, key, 1, rotation=45)


def test_page_image_cache(tmp_path: Path) -> None:
    data = make_pdf([PdfPage(lines=EQUIPMENT_LINES)])
    r, sha, key = _store(tmp_path, data)
    first = r.render(sha, key, 1)
    again = r.render(sha, key, 1)
    assert not first.cache_hit and again.cache_hit and again.render_ms == 0.0
    assert r.renders == 1 and again.data == first.data
    r.render(sha, key, 1, long_side=900)  # different scale: new render
    r.render(sha, key, 1, rotation=90)  # different rotation: new render
    assert r.renders == 3
    assert r.render(sha, key, 1, rotation=90).cache_hit


@pytest.mark.parametrize("content_angle", [0, 90, 180, 270])
@pytest.mark.parametrize("page_rotate", [0, 90])
def test_page_orientation(tmp_path: Path, content_angle: int, page_rotate: int) -> None:
    """Text-layer pages: the rendered image is corrected to upright, whatever the source."""
    data = make_pdf(
        [PdfPage(lines=EQUIPMENT_LINES, content_angle=content_angle, page_rotate=page_rotate)]
    )
    r, sha, key = _store(tmp_path, data)
    out = r.render(sha, key, 1)
    assert out.orientation == "text_layer"
    # the corrected image has horizontal text: ascender skew is positive upright
    with Image.open(io.BytesIO(out.data)) as img:
        assert pg.image_orientation(img)[0] == 0


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_page_orientation_image_only(tmp_path: Path, angle: int) -> None:
    """Scan-like pages (no text layer): the bounded ink-profile check uprights the image."""
    data = make_pdf([PdfPage(scan_lines=EQUIPMENT_LINES, scan_angle_cw=angle)])
    r, sha, key = _store(tmp_path, data)
    assert not r.page_text(key, 1).has_text_layer
    out = r.render(sha, key, 1)
    assert out.orientation == "image_profile" and out.rotation_applied == (-angle) % 360
    with Image.open(io.BytesIO(out.data)) as img:
        assert pg.image_orientation(img)[0] == 0
    # an explicit rotation flag wins over the check
    flagged = r.render(sha, key, 1, rotation=0)
    assert flagged.orientation == "flag" and flagged.rotation_applied == 0


def test_page_text_layer_detection(tmp_path: Path) -> None:
    data = make_pdf([PdfPage(lines=EQUIPMENT_LINES), PdfPage(scan_lines=["x y z"])])
    r, _, key = _store(tmp_path, data)
    one, two = r.page_text(key, 1), r.page_text(key, 2)
    assert one.has_text_layer and "Production packer 3064.39 m MD" in one.text
    assert not two.has_text_layer


def test_render_runs_off_the_event_loop(tmp_path: Path) -> None:
    data = make_pdf([PdfPage(lines=EQUIPMENT_LINES)])
    r, sha, key = _store(tmp_path, data)
    seen: list[int] = []
    original = r.render

    def spy(*a: object, **k: object) -> pg.RenderedPage:
        seen.append(threading.get_ident())
        return original(*a, **k)  # type: ignore[arg-type]

    r.render = spy  # type: ignore[method-assign]

    async def go() -> int:
        loop_thread = threading.get_ident()
        await asyncio.gather(*(r.render_async(sha, key, 1, long_side=800 + i) for i in range(4)))
        return loop_thread

    loop_thread = asyncio.run(go())
    assert seen and loop_thread not in seen


def test_non_pdf_refused(tmp_path: Path) -> None:
    r, sha, key = _store(tmp_path, b"plain text, not a pdf\n")
    with pytest.raises(pg.PageError) as exc:
        r.render(sha, key, 1)
    assert exc.value.code == "not_a_pdf"

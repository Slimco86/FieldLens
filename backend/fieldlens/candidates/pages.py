"""Page images and page text from stored PDFs (AX-12), read-only and bounded.

pdfium is not thread-safe, so every document open/render/text call runs under one process lock;
the semaphore bounds how many callers wait inside the renderer and ``render_async`` moves the
work off the event loop. Images are cached by (blob sha256, page, long side, rotation); results
carry the locator metadata, never a filesystem path. Orientation: an explicit rotation flag wins;
otherwise the text layer's character angles decide, and for image-only pages a bounded
deterministic ink-profile check on a small thumbnail (ascender/descender skew over the four
rotations) decides, reporting ``uncertain`` rather than guessing when the evidence is weak."""

from __future__ import annotations

import asyncio
import hashlib
import io
import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c
from PIL import Image

from fieldlens.evidence.storage import BlobStore

HARD_CAP_LONG_SIDE = 2400
DEFAULT_LONG_SIDE = 1600
MIN_LONG_SIDE = 200
MAX_PAGES = 5000
MAX_TEXT_CHARS = 20000
MAX_SAMPLED_CHARS = 500
THUMB_SIDE = 600
INK_THRESHOLD = 140
MIN_SKEW = 0.08
MIN_MARGIN = 0.08
TEXT_LAYER_MIN_CHARS = 20
JPEG_QUALITY = 85

_PDFIUM_LOCK = threading.RLock()
Orientation = Literal["flag", "text_layer", "image_profile", "uncertain", "none"]


class PageError(Exception):
    """A page request that cannot be served (message is safe to show to a model)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class RenderedPage:
    data: bytes
    media_type: Literal["image/jpeg"]
    width: int
    height: int
    page: int
    page_count: int
    long_side: int
    rotation_applied: int
    orientation: Orientation
    cache_hit: bool
    render_ms: float
    image_sha256: str

    def meta(self) -> dict[str, object]:
        """Model/log-safe description. No bytes, no path."""
        return {
            "page": self.page,
            "page_count": self.page_count,
            "width": self.width,
            "height": self.height,
            "rotation_applied": self.rotation_applied,
            "orientation": self.orientation,
            "cache_hit": self.cache_hit,
            "image_sha256": self.image_sha256,
        }


@dataclass(frozen=True)
class PageText:
    text: str
    page: int
    page_count: int
    has_text_layer: bool
    truncated: bool


def clamp_long_side(value: int | None) -> int:
    if value is None:
        return DEFAULT_LONG_SIDE
    return max(MIN_LONG_SIDE, min(int(value), HARD_CAP_LONG_SIDE))


def _skew(ink: np.ndarray) -> float:
    """Mean centroid offset of text bands: positive when ascenders sit above the baseline."""
    rows = ink.sum(axis=1)
    peak = float(rows.max()) if rows.size else 0.0
    if peak <= 0:
        return 0.0
    on = rows > 0.25 * peak
    n = len(rows)
    total, count, i = 0.0, 0, 0
    while i < n:
        if not on[i]:
            i += 1
            continue
        j = i
        while j < n and on[j]:
            j += 1
        a, b = max(0, i - 6), min(n, j + 6)
        band = rows[a:b]
        weight = float(band.sum())
        if weight > 0:
            centroid = float((band * np.arange(a, b)).sum() / weight)
            total += centroid - (a + b - 1) / 2
            count += 1
        i = j
    return total / count if count else 0.0


def image_orientation(img: Image.Image) -> tuple[int, Orientation]:
    """Clockwise rotation (0/90/180/270) that makes text upright, from the ink profile."""
    scale = THUMB_SIDE / max(img.size)
    small = img.convert("L").resize(
        (max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.BILINEAR
    )
    ink = (np.asarray(small) < INK_THRESHOLD).astype(np.float32)
    scores: dict[int, float] = {}
    for rotation in (0, 90, 180, 270):
        k = (-rotation // 90) % 4  # np.rot90 turns counter-clockwise
        scores[rotation] = _skew(np.rot90(ink, k))
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top < MIN_SKEW or top - second < MIN_MARGIN:
        return 0, "uncertain"
    return best, "image_profile"


def _text_layer_rotation(page: pdfium.PdfPage) -> int | None:
    """Clockwise rotation that makes the dominant text direction upright (None: no layer)."""
    textpage = page.get_textpage()
    try:
        count = textpage.count_chars()
        if count < TEXT_LAYER_MIN_CHARS:
            return None
        step = max(1, count // MAX_SAMPLED_CHARS)
        votes: dict[int, int] = {}
        for index in range(0, count, step):
            if not textpage.get_text_range(index, 1).strip():
                continue
            angle = pdfium_c.FPDFText_GetCharAngle(textpage, index)
            if angle < 0 or not math.isfinite(angle):
                continue
            quadrant = int(round(math.degrees(angle) / 90.0)) % 4
            votes[quadrant * 90] = votes.get(quadrant * 90, 0) + 1
        if not votes:
            return None
        char_angle = max(votes.items(), key=lambda kv: kv[1])[0]
        # pdfium reports the angle in page space, counter to the visual sense, and excludes /Rotate
        return int((-char_angle - page.get_rotation()) % 360)
    finally:
        textpage.close()


class PageRenderer:
    def __init__(
        self,
        store: BlobStore,
        *,
        long_side: int = DEFAULT_LONG_SIDE,
        cache_bytes: int = 64 * 1024 * 1024,
        concurrency: int = 2,
    ) -> None:
        self._store = store
        self.long_side = clamp_long_side(long_side)
        self._cache: OrderedDict[tuple[str, int, int, int | None], RenderedPage] = OrderedDict()
        self._cache_bytes = cache_bytes
        self._cached_total = 0
        self._cache_lock = threading.Lock()
        self._gate = threading.BoundedSemaphore(max(1, concurrency))
        self._async_gate: asyncio.Semaphore | None = None
        self._concurrency = max(1, concurrency)
        self.renders = 0  # actual pdfium renders (cache misses), for tests and measurements

    # -- helpers ----------------------------------------------------------------------------
    def _path(self, storage_key: str) -> Path:
        try:
            return self._store.path_for(storage_key)
        except ValueError as exc:
            raise PageError("document_unavailable", "document content is unavailable") from exc

    @staticmethod
    def _open(path: Path) -> pdfium.PdfDocument:
        try:
            return pdfium.PdfDocument(str(path))
        except (pdfium.PdfiumError, OSError) as exc:
            raise PageError("not_a_pdf", "document is not a readable PDF") from exc

    @staticmethod
    def _check_page(page: int, count: int) -> None:
        if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= count:
            raise PageError("page_out_of_range", f"page must be between 1 and {count}")

    def page_count(self, storage_key: str) -> int:
        with self._gate, _PDFIUM_LOCK:
            doc = self._open(self._path(storage_key))
            try:
                return len(doc)
            finally:
                doc.close()

    # -- text -------------------------------------------------------------------------------
    def page_text(self, storage_key: str, page: int) -> PageText:
        with self._gate, _PDFIUM_LOCK:
            doc = self._open(self._path(storage_key))
            try:
                count = len(doc)
                self._check_page(page, count)
                textpage = doc[page - 1].get_textpage()
                try:
                    raw = textpage.get_text_range()
                finally:
                    textpage.close()
            finally:
                doc.close()
        text = raw.replace("\r\n", "\n").replace("\r", "\n")
        layer = len("".join(text.split())) >= TEXT_LAYER_MIN_CHARS
        return PageText(text[:MAX_TEXT_CHARS], page, count, layer, len(text) > MAX_TEXT_CHARS)

    def all_page_texts(self, storage_key: str, *, max_pages: int = MAX_PAGES) -> list[str]:
        """Text of every page (for triage); one open, one lock hold per call."""
        with self._gate, _PDFIUM_LOCK:
            doc = self._open(self._path(storage_key))
            try:
                out: list[str] = []
                for index in range(min(len(doc), max_pages)):
                    textpage = doc[index].get_textpage()
                    try:
                        out.append(textpage.get_text_range())
                    finally:
                        textpage.close()
                return out
            finally:
                doc.close()

    # -- images -----------------------------------------------------------------------------
    def render(
        self,
        sha256: str,
        storage_key: str,
        page: int,
        *,
        long_side: int | None = None,
        rotation: int | None = None,
    ) -> RenderedPage:
        """Upright JPEG of one page. ``rotation`` (0/90/180/270 clockwise) is an explicit flag;
        None runs the bounded orientation check."""
        if rotation is not None and rotation not in (0, 90, 180, 270):
            raise PageError("bad_rotation", "rotation must be 0, 90, 180 or 270")
        side = clamp_long_side(long_side if long_side is not None else self.long_side)
        key = (sha256, page, side, rotation)
        with self._cache_lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return RenderedPage(**{**hit.__dict__, "cache_hit": True, "render_ms": 0.0})
        started = time.perf_counter()
        with self._gate, _PDFIUM_LOCK:
            doc = self._open(self._path(storage_key))
            try:
                count = len(doc)
                self._check_page(page, count)
                pdf_page = doc[page - 1]
                width, height = pdf_page.get_size()
                if width <= 0 or height <= 0:
                    raise PageError("page_unreadable", "page has no drawable area")
                if rotation is not None:
                    applied, how = rotation, "flag"
                else:
                    layer = _text_layer_rotation(pdf_page)
                    applied, how = (layer, "text_layer") if layer is not None else (0, "none")
                scale = side / max(width, height)
                image = pdf_page.render(scale=scale).to_pil().convert("RGB")
            finally:
                doc.close()
        if rotation is None and how == "none":
            applied, how = image_orientation(image)
        if applied:
            image = image.rotate(-applied, expand=True, fillcolor=(255, 255, 255))
        if max(image.size) > HARD_CAP_LONG_SIDE:
            raise PageError("image_too_large", "rendered image exceeds the size cap")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=JPEG_QUALITY)
        data = buffer.getvalue()
        result = RenderedPage(
            data=data,
            media_type="image/jpeg",
            width=image.width,
            height=image.height,
            page=page,
            page_count=count,
            long_side=side,
            rotation_applied=applied,
            orientation=how,  # type: ignore[arg-type]
            cache_hit=False,
            render_ms=(time.perf_counter() - started) * 1000,
            image_sha256=hashlib.sha256(data).hexdigest(),
        )
        self.renders += 1
        self._remember(key, result)
        return result

    def _remember(self, key: tuple[str, int, int, int | None], value: RenderedPage) -> None:
        with self._cache_lock:
            if key in self._cache:
                return
            self._cache[key] = value
            self._cached_total += len(value.data)
            while self._cached_total > self._cache_bytes and len(self._cache) > 1:
                _, dropped = self._cache.popitem(last=False)
                self._cached_total -= len(dropped.data)

    async def render_async(
        self,
        sha256: str,
        storage_key: str,
        page: int,
        *,
        long_side: int | None = None,
        rotation: int | None = None,
    ) -> RenderedPage:
        """Event-loop entry point: pdfium work runs in a worker thread, concurrency bounded."""
        if self._async_gate is None:
            self._async_gate = asyncio.Semaphore(self._concurrency)
        async with self._async_gate:
            return await asyncio.to_thread(
                self.render, sha256, storage_key, page, long_side=long_side, rotation=rotation
            )

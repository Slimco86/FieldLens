"""MI-6 live smoke helpers: opt-in gate, synthetic PNG, raw-capture client. No network on import."""

from __future__ import annotations

import struct
import zlib
from collections.abc import Mapping
from typing import Any

OPT_IN_VAR = "FIELDLENS_LIVE_META"
# The default-test conftest blanks MODEL_API_KEY; it stashes the real value here, but only when
# the explicit opt-in variable is set in the same process.
STASHED_KEY: dict[str, str] = {}
GUARD_UNDO: list[tuple[object, str, object]] = []


def live_opt_in_problem(env: Mapping[str, str], key: str | None) -> str | None:
    """Why the live smoke must refuse to run, or None when it is explicitly authorized."""
    if env.get(OPT_IN_VAR) != "1":
        return f"live Meta smoke needs the explicit opt-in {OPT_IN_VAR}=1 (and -m live_meta)"
    if not (key or "").strip():
        return "live Meta smoke needs MODEL_API_KEY in the real environment"
    return None


_FONT = {
    "0": "111101101101111",
    "1": "010110010010111",
    "2": "111001111100111",
    "3": "111001111001111",
    "4": "101101111001001",
    "5": "111100111001111",
    "6": "111100111101111",
    "7": "111001001001001",
    "8": "111101111101111",
    "9": "111101111001111",
}


def digits_png(digits: str, scale: int) -> bytes:
    """Grayscale PNG (stdlib only): black 3x5 block digits on white, ``scale`` px per cell."""
    cells_w, cells_h = len(digits) * 4 + 1, 7
    width, height = cells_w * scale, cells_h * scale
    grid = [[255] * cells_w for _ in range(cells_h)]
    for index, ch in enumerate(digits):
        for i, bit in enumerate(_FONT[ch]):
            if bit == "1":
                grid[1 + i // 3][1 + index * 4 + i % 3] = 0
    rows = bytearray()
    for cy in range(cells_h):
        line = bytes(v for v in grid[cy] for _ in range(scale))
        rows += (b"\x00" + line) * scale

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


class _Responses:
    def __init__(self, inner: Any, sink: list[dict[str, Any]]) -> None:
        self._inner, self._sink = inner, sink

    def create(self, **kwargs: Any) -> Any:
        response = self._inner.create(**kwargs)
        raw = response.model_dump(mode="json")
        # Structure only: top-level keys, usage and statuses. Content text is not kept here.
        self._sink.append(
            {
                "keys": sorted(raw),
                "model": raw.get("model"),
                "status": raw.get("status"),
                "usage": raw.get("usage"),
                "output_types": [i.get("type") for i in raw.get("output", [])],
                "reasoning": raw.get("reasoning"),
                "service_tier": raw.get("service_tier"),
                "include_requested": kwargs.get("include"),
            }
        )
        return response


class CapturingClient:
    """Wraps the SDK client so raw usage/structure is recorded; nothing else changes."""

    def __init__(self, inner: Any) -> None:
        self.captures: list[dict[str, Any]] = []
        self.responses = _Responses(inner.responses, self.captures)
        self.max_retries = inner.max_retries

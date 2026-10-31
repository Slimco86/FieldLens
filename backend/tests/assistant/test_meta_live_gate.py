"""Offline proof that the live smoke refuses to run without an explicit opt-in (MI-6 gate)."""

from __future__ import annotations

import struct
import zlib

from tests.live_meta_support import OPT_IN_VAR, digits_png, live_opt_in_problem


def test_live_smoke_refuses_without_explicit_opt_in() -> None:
    assert live_opt_in_problem({}, "k") is not None
    assert live_opt_in_problem({OPT_IN_VAR: "true"}, "k") is not None
    assert live_opt_in_problem({OPT_IN_VAR: "0"}, "k") is not None


def test_live_smoke_refuses_without_a_key_even_when_opted_in() -> None:
    assert live_opt_in_problem({OPT_IN_VAR: "1"}, None) is not None
    assert live_opt_in_problem({OPT_IN_VAR: "1"}, "  ") is not None
    assert live_opt_in_problem({OPT_IN_VAR: "1"}, "k") is None


def test_live_marker_is_excluded_from_default_runs(pytestconfig) -> None:  # type: ignore[no-untyped-def]
    assert "not live_meta" in pytestconfig.getoption("markexpr")


def test_synthetic_digit_png_is_valid_and_sized() -> None:
    raw = digits_png("7305", 8)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (17 * 8, 7 * 8)
    idat_at = raw.index(b"IDAT")
    length = struct.unpack(">I", raw[idat_at - 4 : idat_at])[0]
    pixels = zlib.decompress(raw[idat_at + 4 : idat_at + 4 + length])
    assert len(pixels) == height * (width + 1)
    assert 0 in pixels and 255 in pixels

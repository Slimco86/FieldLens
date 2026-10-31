"""Compact little-endian array encoding for stored series (float64 values, int32 positions)."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

F8 = np.dtype("<f8")
I4 = np.dtype("<i4")


def encode_f8(values: NDArray[np.float64]) -> bytes:
    return np.ascontiguousarray(values, dtype=F8).tobytes()


def encode_i4(values: NDArray[np.int32]) -> bytes:
    return np.ascontiguousarray(values, dtype=I4).tobytes()


def decode_f8(data: bytes | memoryview) -> NDArray[np.float64]:
    return np.frombuffer(data, dtype=F8)


def decode_i4(data: bytes | memoryview) -> NDArray[np.int32]:
    return np.frombuffer(data, dtype=I4)

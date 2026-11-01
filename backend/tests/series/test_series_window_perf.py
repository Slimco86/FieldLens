"""DC-8: a 10,000-sample window answers in under 300 ms (p95) on this host. The measured
numbers are printed (``-s``) and recorded in the handoff; synthetic invented data."""

from __future__ import annotations

import statistics
import time
from pathlib import Path
from uuid import UUID

import numpy as np
import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from fieldlens.contracts.series import WindowResolution
from fieldlens.series.service import SeriesService
from tests.series.support import NULL, Lane, las_text

BUDGET_S = 0.300


def _p95(samples: list[float]) -> float:
    return statistics.quantiles(samples, n=100)[94]


def _rows(n: int) -> list[list[float]]:
    rng = np.random.default_rng(5)
    gr = np.cumsum(rng.normal(size=n))
    rows = [[1000.0 + i * 0.1, round(float(gr[i]), 4), 2.0] for i in range(n)]
    for i in range(n // 3, n // 3 + 50):
        rows[i][1] = NULL
    return rows


@pytest.mark.parametrize("n", [10_000, 100_000])
def test_window_latency_p95(migrated_url: URL, tmp_path: Path, engine: Engine, n: int) -> None:
    lane = Lane(migrated_url, tmp_path, engine)
    (doc,) = lane.upload([("big.las", las_text(_rows(n)).encode())])
    lane.drain()
    sid = next(i["series_id"] for i in lane.series(mnemonic="GR", document_id=doc))
    service = SeriesService(lane.api.client.app.state.session_factory)
    pid = UUID(lane.pid)
    cases = {
        "service 10k-sample window, downsampled to 5000": dict(max_points=5000),
        "service 10k-sample window, full resolution": dict(
            resolution=WindowResolution.FULL, start="1000", end=str(1000.0 + 0.1 * 9_999)
        ),
    }
    if n > 10_000:
        cases["service 100k-sample series, max_points=10000"] = dict(max_points=10_000)
    report: list[str] = []
    for label, kwargs in cases.items():
        service.get_window(pid, UUID(sid), **kwargs)  # type: ignore[arg-type]  # warm-up
        times = []
        for _ in range(60):
            t = time.perf_counter()
            win = service.get_window(pid, UUID(sid), **kwargs)  # type: ignore[arg-type]
            times.append(time.perf_counter() - t)
        p95 = _p95(times)
        report.append(
            f"n={n} {label}: p50={statistics.median(times) * 1000:.1f} ms "
            f"p95={p95 * 1000:.1f} ms returned={win.returned_points}"
        )
        assert p95 < BUDGET_S, report[-1]
        assert win.returned_points <= (10_000 if "full" in label else kwargs["max_points"])  # type: ignore[operator]
    http = []
    path = f"/api/v1/projects/{lane.pid}/series/{sid}/window"
    for _ in range(40):
        t = time.perf_counter()
        r = lane.api.client.get(path, params={"max_points": 5000})
        http.append(time.perf_counter() - t)
        assert r.status_code == 200
    report.append(f"n={n} HTTP window max_points=5000: p95={_p95(http) * 1000:.1f} ms")
    assert _p95(http) < BUDGET_S
    print("\n".join(report))

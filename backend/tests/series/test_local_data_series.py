"""Opt-in real-data fidelity, timing and storage checks for stored series (DC-7, DC-9, DC-11).

Skipped unless ``FIELDLENS_LOCAL_DATA_ROOT`` points at the read-only data root (for example
``/mnt/c/Users/<user>/Downloads/Hackathon_Data``). Files are read in place, never copied.
Run:  FIELDLENS_LOCAL_DATA_ROOT=... uv run pytest backend/tests/series -m local_data -s
Gaps are reported, never filled: files the upload inspector refuses, files whose index tokens are
not plain numbers (time-formatted TIME columns) and skipped data lines are counted, not hidden."""

from __future__ import annotations

import os
import re
import resource
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from fieldlens.contracts.errors import ContractError
from fieldlens.extraction import runner as runner_module
from fieldlens.ingestion.inspect import inspect_file
from fieldlens.profiles import registry
from fieldlens.profiles.las import LasProfile
from fieldlens.profiles.production import ProductionWorkbookProfile
from fieldlens.profiles.types import AxisOut, ProfileError, ProfileOutput
from fieldlens.series.builder import summarize
from tests.profile_support import CTX
from tests.series.support import Lane

pytestmark = pytest.mark.local_data

_ROOT_ENV = os.environ.get("FIELDLENS_LOCAL_DATA_ROOT")
if not _ROOT_ENV or not Path(_ROOT_ENV).is_dir():
    pytest.skip("FIELDLENS_LOCAL_DATA_ROOT is not set to a directory", allow_module_level=True)
ROOT = Path(_ROOT_ENV)
LOGS = ROOT / "Well_logs_pr_WELL"
PRODUCTION = ROOT / "Production_data" / "Volve production data.xlsx"
APPROVED = {
    w: LOGS / f"15_9-{w}" / "02.LWD_EWL" / "WL_RAW_BHPR-GR-MECH_MWD_1.LAS"
    for w in ("F-12", "F-14", "F-5")
}
MAX_EXTRA_SECONDS = 60.0
_NULL_LINE = re.compile(
    r"^\s*NULL\s*\.[^\s:]*\s+([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)", re.IGNORECASE | re.MULTILINE
)


def _las_files() -> list[Path]:
    return sorted(p for p in LOGS.rglob("*") if p.suffix.lower() == ".las")


def _parse_las(path: Path) -> ProfileOutput | str:
    """The LAS profile output, or a short reason the file never reaches it."""
    try:
        family = inspect_file(
            path, path.name, max_file_bytes=2 * 1024**3, remaining_batch_bytes=2 * 1024**3
        ).format_family
    except ContractError:
        return "refused_by_upload_inspector"
    if "las_2_0" not in [p.name for p in registry.detect(path, family, path.name)]:
        return "not_a_las_profile_match"
    try:
        return LasProfile().parse(path, CTX)
    except ProfileError as exc:
        return f"profile_error:{exc.code}"


def _independent_samples(path: Path, ncols: int) -> tuple[np.ndarray, float | None]:
    """Re-read the data section with a deliberately separate, minimal reader (plain float())."""
    raw = path.read_bytes().decode("latin-1")
    null_match = _NULL_LINE.search(raw)
    null = float(null_match.group(1)) if null_match else None
    parts = re.split(r"(?im)^[ \t]*~A[^\n]*\n", raw, maxsplit=1)
    assert len(parts) == 2, "no ~A section"
    rows = []
    for line in parts[1].splitlines():
        toks = line.split()
        if len(toks) != ncols:
            continue
        try:
            vals = [float(t) for t in toks]
        except ValueError:
            continue
        if all(np.isfinite(vals)):
            rows.append(vals)
    return np.array(rows, dtype=np.float64).reshape(-1, ncols), null


def _check_axis_against_records(out: ProfileOutput, axis: AxisOut) -> int:
    header = out.records[0]
    data_rows = header.attr("las_header.data_rows")
    assert data_rows is not None and data_rows.number is not None
    assert axis.index.size == int(data_rows.number), "stored sample count == data_rows"
    assert axis.positions.size == axis.index.size
    for curve in axis.curves:
        rec = out.records[curve.record_ordinal or 0]
        assert rec.kind == "las_curve" and rec.locator["las_mnemonic"] == curve.measure
        got = summarize(axis.index, curve.values)
        a = {k: rec.attr(f"las_curve.{k}") for k in ("valid_count", "null_count", "min", "max")}
        assert got["valid_count"] == int(a["valid_count"].number)  # type: ignore[union-attr]
        assert got["null_count"] == int(a["null_count"].number)  # type: ignore[union-attr]
        assert got["valid_count"] + got["null_count"] == axis.index.size
        for k, key in (("min", "min_value"), ("max", "max_value")):
            attr = a[k]
            assert attr is not None
            assert (attr.number is None) == (got[key] is None)
            if attr.number is not None:
                assert attr.number == got[key]
        if got["valid_count"]:
            valid = np.flatnonzero(~np.isnan(curve.values))
            loc = a["valid_count"].locator  # type: ignore[union-attr]
            assert loc["line_start"] == int(axis.positions[valid[0]])
            assert loc["line_end"] == int(axis.positions[valid[-1]])
    return int(data_rows.number)


def test_series_fidelity_every_real_las() -> None:
    files = _las_files()
    assert len(files) >= 200, "the approved data root has 300+ LAS files"
    reasons: Counter[str] = Counter()
    stored = zero_sample = partial = independent = 0
    samples = cells = skipped_lines = 0
    mismatched_lines: list[str] = []
    for path in files:
        out = _parse_las(path)
        if isinstance(out, str):
            reasons[out] += 1
            continue
        header = out.records[0]
        data_rows = header.attr("las_header.data_rows")
        assert data_rows is not None and data_rows.number is not None
        total_lines = int(data_rows.original_text or 0)
        if total_lines != int(data_rows.number):
            skipped_lines += total_lines - int(data_rows.number)
            mismatched_lines.append(f"{path.name}: {int(data_rows.number)}/{total_lines}")
        partial += out.status == "partial"
        if int(data_rows.number) == 0:
            assert out.series == [], "no sample, no series"
            zero_sample += 1
            continue
        assert len(out.series) == 1
        axis = out.series[0]
        samples += _check_axis_against_records(out, axis)
        cells += axis.index.size * (len(axis.curves) + 1)
        stored += 1
        if path.stat().st_size <= 6 * 1024 * 1024:
            ncols = len(axis.curves) + 1
            ref, null = _independent_samples(path, ncols)
            assert ref.shape[0] == axis.index.size, path
            assert np.array_equal(ref[:, 0], axis.index), path
            for i, curve in enumerate(axis.curves, start=1):
                col = ref[:, i].copy()
                if null is not None:
                    col[col == null] = np.nan
                assert np.array_equal(col, curve.values, equal_nan=True), (path, curve.measure)
            independent += 1
    print(
        f"\nLAS files found={len(files)} series stored for={stored} (samples={samples}, "
        f"cells={cells}) zero-sample files={zero_sample} partial={partial} "
        f"independent re-read compared={independent} skipped data lines={skipped_lines} "
        f"not parsed={dict(reasons)}"
    )
    if mismatched_lines:
        print("data_rows != data lines (rows skipped by the profile): " + "; ".join(mismatched_lines[:25]))
    assert stored > 100


def test_production_series_counts_values_and_units_equal_the_records() -> None:
    out = ProductionWorkbookProfile().parse(PRODUCTION, CTX)
    days = [r for r in out.records if r.kind == "production_day"]
    by_row = {int(r.locator["cell_range"].split(":")[0][1:]): r for r in days}
    per_wellbore = Counter(r.subject["wellbore_label"] for r in days)
    assert {a.subject["wellbore_label"] for a in out.series} == set(per_wellbore)
    total = checked = 0
    for axis in out.series:
        label = axis.subject["wellbore_label"]
        assert axis.index.size == per_wellbore[label], "one sample per production_day record"
        assert np.all(np.diff(axis.index) >= 0), "day index non-decreasing"
        total += axis.index.size
        for curve in axis.curves:
            assert curve.values.size == axis.index.size
            key = f"production_day.{curve.measure}"
            for k, row in enumerate(axis.positions):
                attr = by_row[int(row)].attr(key)
                expect = np.nan if attr is None or attr.number is None else attr.number
                got = curve.values[k]
                assert (np.isnan(expect) and np.isnan(got)) or expect == got
                checked += 1
            if curve.measure != "avg_choke_size_p":
                assert curve.unit is None and curve.unit_status == "missing"
    assert total == len(days) - out.detail["counts"]["daily_rows_without_date"]
    print(
        f"\nproduction: wellbores={len(out.series)} day records={len(days)} "
        f"samples per measure total={total} values compared={checked}"
    )


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def test_real_extraction_time_storage_and_database_roundtrip(
    migrated_url: URL, tmp_path: Path, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    files = [
        (f"{w}_{p.name}", p.read_bytes()) for w, p in APPROVED.items()
    ] + [(PRODUCTION.name, PRODUCTION.read_bytes())]

    def extract(with_series: bool, root: Path) -> tuple[float, Lane]:
        lane = Lane(migrated_url, root, engine)
        lane.upload(files)
        if not with_series:
            monkeypatch.setattr(runner_module, "store_series", lambda *a, **k: 0)
        t = time.perf_counter()
        n = lane.drain()
        elapsed = time.perf_counter() - t
        monkeypatch.undo()
        assert n == len(files)
        return elapsed, lane

    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    without, lane_without = extract(False, tmp_path / "a")
    assert lane_without.series() == []
    with_s, lane = extract(True, tmp_path / "b")
    extra = with_s - without
    sizes = lane.sql(
        "select pg_total_relation_size('series_axis') a, pg_total_relation_size('series_curve') c, "
        "(select count(*) from series_curve) n, (select sum(sample_count) from series_curve) s"
    )[0]
    rec_size = lane.sql(
        "select sum(pg_column_size(attributes)) from extracted_record where project_id = :p",
        p=lane.pid,
    )[0][0]
    print(
        f"\nextraction wall: without series={without:.2f}s with series={with_s:.2f}s "
        f"extra={extra:.2f}s (budget {MAX_EXTRA_SECONDS:.0f}s); peak RSS of this process "
        f"{_rss_mb():.0f} MB; series storage axis={sizes.a / 1e6:.2f} MB curve={sizes.c / 1e6:.2f} MB "
        f"curves={sizes.n} samples={sizes.s}; extracted_record attributes={rec_size / 1e6:.2f} MB"
    )
    assert extra <= MAX_EXTRA_SECONDS
    # database round trip: what the API returns equals what the profile produced
    items = lane.series()
    assert items and all(i["sample_count"] > 0 for i in items)
    out = LasProfile().parse(APPROVED["F-12"], CTX)
    axis = out.series[0]
    f12 = [i for i in items if i["kind"] == "log" and i["well_name"] == axis.subject["well_name"]]
    assert len(f12) == len(axis.curves)
    for curve in axis.curves:
        entry = next(i for i in f12 if i["measure"] == curve.measure and i["sample_count"] == axis.index.size)
        win = lane.get(f"/{entry['series_id']}/window", resolution="full").json()
        assert win["index"] == axis.index.tolist()
        assert win["values"] == [None if np.isnan(v) else v for v in curve.values.tolist()]
        assert entry["valid_count"] + entry["null_count"] == entry["sample_count"]

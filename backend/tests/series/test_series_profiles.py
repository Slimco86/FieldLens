"""DC-7/DC-9 at profile level (no database): samples beside the records, NULLs as real nulls,
counts equal to the per-curve summary records. Synthetic invented values only."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from fieldlens.profiles import las as las_module
from fieldlens.profiles.las import LasProfile, classify_index
from fieldlens.profiles.production import ProductionWorkbookProfile
from tests.profile_support import CTX, write
from tests.series.support import DAILY_HEAD, NULL, day_row, las_text, workbook_bytes


def _rec_curve(out, name):  # type: ignore[no-untyped-def]
    return next(
        r for r in out.records if r.locator.get("las_mnemonic") == name and r.kind == "las_curve"
    )


def test_las_series_matches_the_per_curve_summary_records(tmp_path: Path) -> None:
    rows = [[100.0, 50.0, 2.4], [101.0, NULL, 2.41], [102.0, 55.5, NULL], [103.0, NULL, NULL]]
    out = LasProfile().parse(write(tmp_path, "a.las", las_text(rows)), CTX)
    assert len(out.series) == 1
    axis = out.series[0]
    assert axis.kind == "log" and axis.index_type == "depth" and axis.index_unit == "M"
    assert axis.index.tolist() == [100.0, 101.0, 102.0, 103.0]
    first = next(
        i for i, ln in enumerate(las_text(rows).splitlines(), 1) if ln.startswith(" 100.0")
    )
    assert axis.positions.tolist() == [first, first + 1, first + 2, first + 3]
    data_rows = out.records[0].attr("las_header.data_rows")
    assert data_rows is not None and data_rows.number == len(axis.index)
    for curve in axis.curves:
        rec = _rec_curve(out, curve.measure)
        v = curve.values
        valid = ~np.isnan(v)
        assert rec.attr("las_curve.valid_count").number == valid.sum()  # type: ignore[union-attr]
        assert rec.attr("las_curve.null_count").number == (~valid).sum()  # type: ignore[union-attr]
        assert float(rec.attr("las_curve.min").number) == v[valid].min()  # type: ignore[union-attr,arg-type]
        assert float(rec.attr("las_curve.max").number) == v[valid].max()  # type: ignore[union-attr,arg-type]
        assert curve.record_ordinal == rec.ordinal
    gr = next(c for c in axis.curves if c.measure == "GR")
    assert np.isnan(gr.values).tolist() == [False, True, False, True]
    assert gr.values[2] == 55.5 and gr.null_sentinel == NULL
    assert (gr.unit, gr.unit_status) == ("GAPI", "stated")
    rhob = next(c for c in axis.curves if c.measure == "RHOB")
    assert (rhob.unit, rhob.unit_status) == (None, "missing"), "no unit is assumed"
    assert out.detail["series_samples"] == 4


def test_las_nulls_never_become_zero_and_real_zeros_survive(tmp_path: Path) -> None:
    rows = [[1.0, 0.0, NULL], [2.0, NULL, 0.0]]
    axis = LasProfile().parse(write(tmp_path, "z.las", las_text(rows)), CTX).series[0]
    gr = next(c for c in axis.curves if c.measure == "GR")
    assert gr.values[0] == 0.0 and np.isnan(gr.values[1])


def test_las_skipped_lines_are_not_stored_and_run_is_partial(tmp_path: Path) -> None:
    text_ = las_text([[1.0, 2.0, 3.0], [2.0, 5.0, 6.0]]).replace(" 2.0 5.0 6.0", " 2.0 5.0")
    out = LasProfile().parse(write(tmp_path, "p.las", text_), CTX)
    assert out.status == "partial"
    assert out.series[0].index.tolist() == [1.0]
    attr = out.records[0].attr("las_header.data_rows")
    assert attr is not None and attr.number == 1.0 and attr.original_text == "2"


def test_las_without_samples_stores_no_series(tmp_path: Path) -> None:
    out = LasProfile().parse(write(tmp_path, "e.las", las_text([])), CTX)
    assert out.series == []


def test_las_series_limit_is_explicit_partial_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(las_module, "MAX_SERIES_CELLS", 5)
    out = LasProfile().parse(write(tmp_path, "l.las", las_text([[1.0, 2.0, 3.0]] * 3)), CTX)
    assert out.series == [] and out.status == "partial"
    assert any(f.key == "las_series_too_large" for f in out.findings)
    assert any("not stored" in r for r in out.coverage.reasons)


def test_las_unordered_index_keeps_source_order(tmp_path: Path) -> None:
    axis = (
        LasProfile()
        .parse(
            write(tmp_path, "u.las", las_text([[3.0, 1.0, 1.0], [1.0, 2.0, 2.0], [2.0, 3.0, 3.0]])),
            CTX,
        )
        .series[0]
    )
    assert axis.index.tolist() == [3.0, 1.0, 2.0]


@pytest.mark.parametrize(
    ("name", "unit", "kind"),
    [
        ("DEPT", "M", "depth"),
        ("MD", "", "depth"),
        ("X", "ft", "depth"),
        ("TIME", "s", "time"),
        ("T", "HHMMSS", "time"),
        ("FOO", "bar", "unknown"),
    ],
)
def test_index_classification(name: str, unit: str, kind: str) -> None:
    assert classify_index(name, unit) == kind


def test_production_series_per_wellbore_keep_days_nulls_and_units(tmp_path: Path) -> None:
    daily = [
        day_row(40001, "15/9-F-A", 1, 20.0),
        day_row(40000, "15/9-F-A", 1, "NULL"),  # out of date order in the sheet
        day_row(40003, "15/9-F-A", 1, 0),  # a real zero; 40002 is simply absent
        day_row(40000, "15/9-F-B", 2, 7.5),
    ]
    out = ProductionWorkbookProfile().parse(write(tmp_path, "p.xlsx", workbook_bytes(daily)), CTX)
    assert [a.subject["wellbore_label"] for a in out.series] == ["NO 15/9-F-A", "NO 15/9-F-B"]
    a, b = out.series
    assert a.index_type == "time" and a.index_encoding == "epoch_days" and a.position_kind == "row"
    assert a.index.tolist() == [14431.0, 14432.0, 14434.0]  # 1900-serial 40000 = 2009-07-06
    assert a.positions.tolist() == [3, 2, 4]
    oil = next(c for c in a.curves if c.measure == "bore_oil_vol")
    assert np.isnan(oil.values[0]) and oil.values[1] == 20.0 and oil.values[2] == 0.0
    assert (oil.unit, oil.unit_status) == (None, "missing"), "daily sheet states no unit"
    gas = next(c for c in a.curves if c.measure == "bore_gas_vol")
    assert np.isnan(gas.values).all(), "NULL cells stay missing, not zero"
    assert next(c for c in b.curves if c.measure == "bore_oil_vol").values.tolist() == [7.5]
    records = [r for r in out.records if r.kind == "production_day"]
    assert sum(len(x.index) for x in out.series) == len(records)
    assert oil.evidence["first_row"] == 2 and oil.evidence["column"] == "F"
    assert out.detail["counts"]["daily_rows_without_date"] == 0


def test_production_duplicate_days_are_kept_in_source_order(tmp_path: Path) -> None:
    daily = [day_row(40000, "15/9-F-A", 1, 1.0), day_row(40000, "15/9-F-A", 1, 2.0)]
    out = ProductionWorkbookProfile().parse(write(tmp_path, "d.xlsx", workbook_bytes(daily)), CTX)
    oil = next(c for c in out.series[0].curves if c.measure == "bore_oil_vol")
    assert oil.values.tolist() == [1.0, 2.0] and out.series[0].index.tolist() == [14431.0] * 2


def test_production_header_columns_define_the_measures(tmp_path: Path) -> None:
    out = ProductionWorkbookProfile().parse(
        write(tmp_path, "m.xlsx", workbook_bytes([day_row(40000, "15/9-F-A", 1, 1.0)])), CTX
    )
    measures = {c.measure for c in out.series[0].curves}
    assert measures == {
        "on_stream_hrs",
        "bore_oil_vol",
        "bore_gas_vol",
        "bore_wat_vol",
        "bore_wi_vol",
    }
    assert set(DAILY_HEAD) >= {"DATEPRD"}

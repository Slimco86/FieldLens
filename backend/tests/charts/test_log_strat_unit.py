"""Pure-unit tests (no database): log tracks (XC-1) and stratigraphic correlation (XC-3).

The formation layer set is built by the real pure core (``build_layer_set``) from synthetic picks
and trajectories, so the datum/blocked rules under test are the formation read model's own."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import numpy as np

from fieldlens.charts.log_strat import (
    LogCurve,
    build_log_tracks,
    build_stratigraphic_correlation,
    unavailable_correlation,
)
from fieldlens.context.formations import Bore, build_layer_set
from fieldlens.contracts.charts import (
    AxisKind,
    ChartEmptyReason,
    ChartKey,
    ChartScope,
    ChartSeriesScope,
    ChartSpec,
    FieldChartSet,
    SeriesUnitStatus,
    WellboreChartSet,
)
from tests.context.test_formations import PROJECT, deviated, pick, vertical

WB = uuid4()
BORE_SCOPE = ChartSeriesScope(
    scope=ChartScope.WELLBORE,
    scope_label="wellbore-level",
    wellbore_id=WB,
    wellbore_label="F-1",
    well_name="F",
)
FIELD_SCOPE = ChartSeriesScope(scope=ChartScope.FIELD, scope_label="field (all wellbores)")


def _curve(
    measure: str,
    unit: str | None,
    y: list[float],
    *,
    index_name: str = "DEPT",
    index_unit: str | None = "M",
    index_type: str = "depth",
    x0: float = 1000.0,
) -> LogCurve:
    return LogCurve(
        series_id=uuid4(),
        document_id=uuid4(),
        measure=measure,
        description=f"{measure} curve",
        unit=unit,
        status=SeriesUnitStatus.STATED if unit else SeriesUnitStatus.MISSING,
        sha=f"sha-{measure}",
        evidence=[],
        x=x0 + np.arange(len(y), dtype=np.float64) * 0.5,
        y=np.array(y, dtype=np.float64),
        index_name=index_name,
        index_unit=index_unit,
        index_type=index_type,
    )


def _tops(*names_md: tuple[str, float], unit: str = "m"):  # type: ignore[no-untyped-def]
    bore = Bore(WB, vertical().trajectory, "RKB")
    rows = [pick(WB, n, md, tvd=md, unit=unit) for n, md in names_md]
    layers = build_layer_set(PROJECT, WB, rows, [bore])
    return [p for s in layers.surfaces for p in s.picks]


def _wellbore_set(chart: ChartSpec) -> WellboreChartSet:
    return WellboreChartSet(
        project_id=PROJECT,
        wellbore_id=WB,
        charts=[chart],
        generated_from_revision="r",
        cache_key="c",
    )


# --- D1: log tracks -------------------------------------------------------------------------------


def test_no_log_records_says_so_never_zero() -> None:
    chart = build_log_tracks([], _tops(("Top A", 1100.0)), scope=BORE_SCOPE, seed="s")
    assert chart.key is ChartKey.LOG_TRACKS
    assert chart.series == [] and chart.reference_lines == []
    assert chart.empty is not None and chart.empty.reason is ChartEmptyReason.NO_RECORDS
    assert "another wellbore" in chart.empty.message
    _wellbore_set(chart)  # validates


def test_log_axes_units_gaps_and_md_x_axis() -> None:
    gr = _curve("GR", "GAPI", [50.0, float("nan"), 70.0, 80.0])
    res = _curve("RES", "OHMM", [1.0, 2.0, 3.0, 4.0])
    gr2 = _curve("GR2", "GAPI", [51.0, 52.0, 53.0, 54.0])
    chart = build_log_tracks([gr, res, gr2], [], scope=BORE_SCOPE, seed="s")
    x_axis = next(a for a in chart.axes if a.axis_id == "x")
    assert x_axis.kind is AxisKind.VALUE and x_axis.unit == "M"
    assert "MD" in x_axis.name
    y_axes = [a for a in chart.axes if a.axis_id != "x"]
    assert {a.unit for a in y_axes} == {"GAPI", "OHMM"} and len(y_axes) == 2
    by_name = {s.series_key.split(":")[1]: s for s in chart.series}
    assert [p.x for p in by_name["GR"].points] == [1000.0, 1000.5, 1001.0, 1001.5]
    assert [p.y for p in by_name["GR"].points] == [50.0, None, 70.0, 80.0]  # gap kept, not zero
    assert by_name["GR"].gap_count == 1
    assert by_name["GR"].aggregates.null_count == 1 and by_name["GR"].aggregates.minimum == 50.0
    assert by_name["GR"].aggregates.first_valid_x == 1000.0
    assert chart.scope.wellbore_id == WB
    assert chart.as_of is None and chart.window is None
    assert any("not time based" in n for n in chart.notes)
    _wellbore_set(chart)


def test_unstated_curve_units_never_share_an_axis() -> None:
    chart = build_log_tracks(
        [_curve("A", None, [1.0, 2.0]), _curve("B", None, [3.0, 4.0])],
        [],
        scope=BORE_SCOPE,
        seed="s",
    )
    assert len([a for a in chart.axes if a.axis_id != "x"]) == 2
    assert all(s.unit is None and s.unit_status is SeriesUnitStatus.MISSING for s in chart.series)


def test_formation_tops_are_md_reference_lines_with_source() -> None:
    chart = build_log_tracks(
        [_curve("GR", "GAPI", [1.0, 2.0, 3.0])],
        _tops(("Top A", 1100.0), ("Top B", 1200.0)),
        scope=BORE_SCOPE,
        seed="s",
    )
    assert [
        (r.label.split(" top")[0], r.value, r.unit, r.axis_id) for r in chart.reference_lines
    ] == [
        ("Top A", 1100.0, "M", "x"),
        ("Top B", 1200.0, "M", "x"),
    ]
    for line in chart.reference_lines:
        assert line.pick_id is not None and line.surface_key
        assert line.evidence and line.evidence[0].record_id == line.pick_id
        assert "formation pick" in line.label and "MD" in line.label
    _wellbore_set(chart)


def test_top_in_other_unit_is_not_converted_or_drawn() -> None:
    chart = build_log_tracks(
        [_curve("GR", "GAPI", [1.0, 2.0])],
        _tops(("Top A", 3000.0), unit="ft"),
        scope=BORE_SCOPE,
        seed="s",
    )
    assert chart.reference_lines == []
    assert chart.series  # the curve itself is still drawn
    assert any("not converted" in n for n in chart.notes)


def test_tops_are_not_drawn_on_an_empty_chart() -> None:
    chart = build_log_tracks([], _tops(("Top A", 1100.0)), scope=BORE_SCOPE, seed="s")
    assert chart.reference_lines == [] and chart.axes == []


def test_non_md_or_unitless_or_other_unit_index_is_excluded_not_mixed() -> None:
    good = _curve("GR", "GAPI", [1.0, 2.0])
    good2 = _curve("RES", "OHMM", [1.0, 2.0])
    tvd = _curve("GR_TVD", "GAPI", [1.0, 2.0], index_name="TVDSS")
    nounit = _curve("NU", "GAPI", [1.0, 2.0], index_unit=None)
    feet = _curve("FT", "GAPI", [1.0, 2.0], index_unit="FT")
    time = _curve("T", "GAPI", [1.0, 2.0], index_name="TIME", index_type="time")
    chart = build_log_tracks([good, good2, tvd, nounit, feet, time], [], scope=BORE_SCOPE, seed="s")
    assert [s.name.split(" ")[0] for s in chart.series] == ["GR", "RES"]
    reasons = {e.name: e.reason for e in chart.excluded_series}
    assert set(reasons) == {"GR_TVD", "NU", "FT", "T"}
    assert "not equated" in reasons["GR_TVD"]
    assert "not stated" in reasons["NU"]
    assert "not converted" in reasons["FT"]
    assert "not a depth" in reasons["T"]


def test_all_curves_excluded_is_an_explicit_empty_state() -> None:
    chart = build_log_tracks(
        [_curve("X", "GAPI", [1.0], index_name="TVD")], [], scope=BORE_SCOPE, seed="s"
    )
    assert chart.series == [] and chart.empty is not None
    assert chart.empty.reason is ChartEmptyReason.SOURCE_UNAVAILABLE
    assert [e.name for e in chart.excluded_series] == ["X"]


def test_all_null_curve_is_excluded_not_drawn() -> None:
    chart = build_log_tracks(
        [_curve("GR", "GAPI", [1.0, 2.0]), _curve("DEAD", "GAPI", [float("nan")] * 3)],
        [],
        scope=BORE_SCOPE,
        seed="s",
    )
    assert [e.name.split(" ")[0] for e in chart.excluded_series] == ["DEAD"]


def test_log_display_is_bounded_but_aggregates_are_exact() -> None:
    n = 20000
    y = np.sin(np.arange(n) / 50.0) * 100.0
    y[7000:7100] = np.nan
    curve = _curve("GR", "GAPI", list(y))
    chart = build_log_tracks([curve], [], scope=BORE_SCOPE, seed="s")
    s = chart.series[0]
    assert len(s.points) <= 5000 and s.downsample.applied and s.downsample.source_points == n
    agg = s.aggregates
    assert agg.count == n and agg.null_count == 100
    assert agg.minimum == float(np.nanmin(y)) and agg.maximum == float(np.nanmax(y))
    assert any(p.y is None for p in s.points)  # the gap survives decimation
    _wellbore_set(chart)


def test_log_cache_key_is_deterministic_and_revision_sensitive() -> None:
    a = build_log_tracks([_curve("GR", "GAPI", [1.0])], [], scope=BORE_SCOPE, seed="s")
    b = build_log_tracks([_curve("GR", "GAPI", [1.0])], [], scope=BORE_SCOPE, seed="s")
    assert a.cache_key == b.cache_key  # same sha -> same key
    changed = _curve("GR", "GAPI", [1.0])
    changed.sha = "other"
    assert build_log_tracks([changed], [], scope=BORE_SCOPE, seed="s").cache_key != a.cache_key


# --- D2: stratigraphic correlation ----------------------------------------------------------------


def _two_bores(ref_a: str | None = "RKB", ref_b: str | None = "RKB") -> tuple[Bore, Bore]:
    a, b = vertical(), vertical()
    return replace(a, vertical_reference=ref_a), replace(b, vertical_reference=ref_b)


def _field(bores: list[Bore], rows):  # type: ignore[no-untyped-def]
    layers = build_layer_set(PROJECT, None, rows, bores)
    names = {b.wellbore_id: (f"F-{i + 1}", "F") for i, b in enumerate(bores)}
    chart = build_stratigraphic_correlation(layers, names, scope=FIELD_SCOPE, seed="s")
    FieldChartSet(
        project_id=PROJECT,
        charts=[chart],
        generated_from_revision="r",
        cache_key="c",
    )  # validates through the contract
    return chart, layers


def _y_axes(chart: ChartSpec) -> dict[str, tuple[AxisKind, str | None, str | None]]:
    return {a.axis_id: (a.kind, a.unit, a.datum) for a in chart.axes if a.axis_id != "x"}


def test_strat_states_md_and_tvd_explicitly_with_stated_reference() -> None:
    a, b = _two_bores()
    chart, _ = _field(
        [a, b],
        [
            pick(a.wellbore_id, "Top Hugin", 1500.0, tvd=1500.0),
            pick(b.wellbore_id, "Top Hugin", 1520.0, tvd=1520.0),
            pick(a.wellbore_id, "Top Skagerrak", 1800.0, tvd=1800.0),
        ],
    )
    assert chart.key is ChartKey.STRATIGRAPHIC_CORRELATION and chart.empty is None
    axes = _y_axes(chart)
    assert set(axes.values()) == {
        (AxisKind.DEPTH_MD, "m", None),
        (AxisKind.DEPTH_TVD, "m", "RKB"),
    }
    assert all(a.inverted for a in chart.axes if a.axis_id != "x")
    md_axis = next(i for i, v in axes.items() if v[0] is AxisKind.DEPTH_MD)
    tvd_axis = next(i for i, v in axes.items() if v[0] is AxisKind.DEPTH_TVD)
    names = {s.name: s for s in chart.series}
    assert set(names) == {
        "Top Hugin top — MD",
        "Top Hugin top — TVD",
        "Top Skagerrak top — MD",
        "Top Skagerrak top — TVD",
    }
    hugin_md = names["Top Hugin top — MD"]
    assert hugin_md.axis_id == md_axis and names["Top Hugin top — TVD"].axis_id == tvd_axis
    assert [(p.x, p.y) for p in hugin_md.points] == [(1.0, 1500.0), (2.0, 1520.0)]
    assert hugin_md.aggregates.minimum == 1500.0 and hugin_md.aggregates.maximum == 1520.0
    assert any("1 = F-1; 2 = F-2" in n for n in chart.notes)
    assert all(s.evidence for s in chart.series)  # pick-backed provenance
    assert chart.excluded_series == []


def test_strat_tvdss_withheld_without_stated_datum() -> None:
    a, b = _two_bores()
    chart, _ = _field(
        [a, b],
        [
            pick(a.wellbore_id, "Top A", 1500.0, tvd=1500.0, tvdss=1475.0),
            pick(b.wellbore_id, "Top A", 1500.0, tvd=1500.0, tvdss=1475.0),
        ],
    )
    assert AxisKind.DEPTH_TVDSS not in {v[0] for v in _y_axes(chart).values()}
    assert any("TVDSS" in n and "no datum" in n for n in chart.notes)
    assert any(s.name.endswith("TVD") for s in chart.series)


def test_strat_differing_references_never_mixed() -> None:
    a, b = _two_bores("RKB", "MSL")
    chart, layers = _field(
        [a, b],
        [
            pick(a.wellbore_id, "Top Shared", 1500.0, tvd=1500.0),
            pick(b.wellbore_id, "Top Shared", 1500.0, tvd=1500.0),
            pick(a.wellbore_id, "Top Only A", 1600.0, tvd=1600.0),
        ],
    )
    assert layers.blocked  # the read model itself blocks the cross-bore surface
    tvd_names = {s.name for s in chart.series if s.name.endswith("TVD")}
    assert "Top Shared top — TVD" not in tvd_names  # blocked pair is not plotted together
    assert {e.name for e in chart.excluded_series} == {
        "Top Shared — F-1 (TVD)",
        "Top Shared — F-2 (TVD)",
    }
    assert all("vertical reference" in e.reason for e in chart.excluded_series)
    # MD stays: it is bore-local and its axis says so
    assert "Top Shared top — MD" in {s.name for s in chart.series}
    md_axis = next(a for a in chart.axes if a.kind is AxisKind.DEPTH_MD)
    assert "not comparable between wellbores" in md_axis.name


def test_strat_unknown_reference_blocks_cross_bore_tvd_and_says_unstated() -> None:
    a, b = _two_bores("RKB", None)
    chart, _ = _field(
        [a, b],
        [
            pick(a.wellbore_id, "Top Shared", 1500.0, tvd=1500.0),
            pick(b.wellbore_id, "Top Shared", 1500.0, tvd=1500.0),
            pick(b.wellbore_id, "Top Only B", 1600.0, tvd=1600.0),
        ],
    )
    assert len(chart.excluded_series) == 2
    assert [s.name for s in chart.series if s.name.endswith("TVD")] == ["Top Only B top — TVD"]
    tvd_axis = next(a for a in chart.axes if a.kind is AxisKind.DEPTH_TVD)
    assert tvd_axis.datum is None and "reference not stated" in tvd_axis.name
    assert any("not stated" in n for n in chart.notes)


def test_strat_units_get_separate_axes() -> None:
    a, b = _two_bores()
    chart, _ = _field(
        [a, b],
        [
            pick(a.wellbore_id, "Top A", 1500.0, tvd=1500.0, unit="m"),
            pick(b.wellbore_id, "Top A", 5000.0, tvd=5000.0, unit="ft"),
        ],
    )
    units = sorted(v[1] for v in _y_axes(chart).values() if v[0] is AxisKind.DEPTH_MD)
    assert units == ["ft", "m"]
    for s in chart.series:
        assert next(ax for ax in chart.axes if ax.axis_id == s.axis_id).unit == s.unit


def test_strat_tvd_conflicting_with_trajectory_is_excluded() -> None:
    a, _ = _two_bores()
    chart, layers = _field(
        [a],
        [
            pick(a.wellbore_id, "Top A", 1500.0, tvd=1200.0),
            pick(a.wellbore_id, "Top B", 1600.0, tvd=1600.0),
        ],
    )
    assert layers.conflicts
    assert [e.name for e in chart.excluded_series] == ["Top A — F-1 (TVD)"]
    assert "Top A top — MD" in {s.name for s in chart.series}  # the MD pick is still shown
    assert "Top A top — TVD" not in {s.name for s in chart.series}


def test_strat_unplaced_picks_are_counted_not_drawn() -> None:
    a, _ = _two_bores()
    chart, layers = _field(
        [a],
        [
            pick(a.wellbore_id, "Top A", 1500.0, tvd=1500.0),
            pick(a.wellbore_id, "Top Q", 100.0, qlf="FO"),
        ],
    )
    assert len(layers.unsupported) == 1
    assert {s.name for s in chart.series} == {"Top A top — MD", "Top A top — TVD"}
    assert any("1 formation pick(s) not drawn" in n for n in chart.notes)


def test_strat_no_picks_is_explicit_empty_state() -> None:
    a, _ = _two_bores()
    chart, _ = _field([a], [])
    assert chart.series == [] and chart.empty is not None
    assert chart.empty.reason is ChartEmptyReason.NO_RECORDS
    only_unplaced = _field([], [pick(uuid4(), "Top A", 1500.0)])[0]
    assert only_unplaced.empty is not None
    assert only_unplaced.empty.reason is ChartEmptyReason.SOURCE_UNAVAILABLE


def test_strat_cache_key_follows_formation_revision() -> None:
    a, b = _two_bores()
    rows = [pick(a.wellbore_id, "Top A", 1500.0, tvd=1500.0)]
    first, _ = _field([a, b], rows)
    again, _ = _field([a, b], rows)
    other, _ = _field([a, b], [*rows, pick(b.wellbore_id, "Top A", 1500.0, tvd=1500.0)])
    assert first.cache_key == again.cache_key != other.cache_key


def test_unavailable_correlation_is_an_empty_state_with_reason() -> None:
    chart = unavailable_correlation(FIELD_SCOPE, "s", "boom")
    assert chart.empty is not None and "boom" in chart.empty.message
    assert chart.empty.reason is ChartEmptyReason.SOURCE_UNAVAILABLE


def test_deviated_bore_keeps_md_and_tvd_distinct() -> None:
    a = deviated("RKB")
    layers = build_layer_set(PROJECT, None, [pick(a.wellbore_id, "Top A", 1000.0)], [a])
    chart = build_stratigraphic_correlation(
        layers, {a.wellbore_id: ("F-1", "F")}, scope=FIELD_SCOPE, seed="s"
    )
    assert [s.name for s in chart.series] == ["Top A top — MD"]  # no TVD stated: none invented
    assert isinstance(a.wellbore_id, UUID)

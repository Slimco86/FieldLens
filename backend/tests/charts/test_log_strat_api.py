"""XC-1/XC-3 through the API on PostgreSQL (synthetic LAS uploads only).

Needs the test database (see ``tests/conftest.py``); not runnable without it."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import URL

from fieldlens.contracts.charts import (
    ChartEmptyReason,
    ChartKey,
    FieldChartSet,
    WellboreChartSet,
)
from fieldlens.identity.resolver import resolve_project
from fieldlens.persistence.session import session_scope
from tests.series.support import Lane, las_text


@pytest.fixture
def lane(migrated_url: URL, tmp_path: Path, engine: Engine) -> Lane:
    return Lane(migrated_url, tmp_path, engine)


def _rows(n: int) -> list[list[float]]:
    return [[100.0 + i * 0.5, 40.0 + i, 2.0 + i / 100] for i in range(n)]


def _bores(lane: Lane) -> dict[str, str]:
    r = lane.api.client.get(f"/api/v1/projects/{lane.pid}/identity")
    assert r.status_code == 200, r.text
    return {b["name"]: b["wellbore_id"] for w in r.json()["wells"] for b in w["wellbores"]}


def _chart_set(lane: Lane, wellbore_id: str) -> WellboreChartSet:
    r = lane.api.client.get(f"/api/v1/projects/{lane.pid}/wellbores/{wellbore_id}/charts")
    assert r.status_code == 200, r.text
    return WellboreChartSet.model_validate(r.json())


def _chart(charts: WellboreChartSet, key: ChartKey) -> Any:
    (found,) = [c for c in charts.charts if c.key is key]
    return found


def test_log_tracks_use_only_this_wellbores_curves(lane: Lane) -> None:
    lane.upload([("a.las", las_text(_rows(40), well="15/9-F-99").encode())])
    lane.upload([("b.las", las_text(_rows(10), well="15/9-F-98").encode())])
    lane.drain()
    with session_scope(lane.api.client.app.state.session_factory) as session:
        resolve_project(session, UUID(lane.pid))
    bores = _bores(lane)
    assert len(bores) == 2
    sets = {name: _chart_set(lane, wid) for name, wid in bores.items()}
    for name, charts in sets.items():
        chart = _chart(charts, ChartKey.LOG_TRACKS)
        assert chart.empty is None, name
        assert {s.name.split(" ")[0] for s in chart.series} == {"GR", "RHOB"}
        assert all(s.scope.wellbore_id == UUID(bores[name]) for s in chart.series)
        x_axis = next(a for a in chart.axes if a.axis_id == "x")
        assert x_axis.unit == "M" and "MD" in x_axis.name
        assert chart.window is None and chart.as_of is None
    longest = max(
        len(s.points) for c in sets.values() for s in _chart(c, ChartKey.LOG_TRACKS).series
    )
    assert longest == 40  # the 10-row log of the other bore is never merged in
    # units preserved; the unit-less RHOB curve never shares GR's axis
    chart = _chart(next(iter(sets.values())), ChartKey.LOG_TRACKS)
    by_unit = {s.name.split(" ")[0]: s.unit for s in chart.series}
    assert by_unit == {"GR": "GAPI", "RHOB": None}
    assert len({s.axis_id for s in chart.series}) == 2


def test_wellbore_without_logs_says_so(lane: Lane) -> None:
    lane.upload([("a.las", las_text(_rows(5), well="15/9-F-99").encode())])
    lane.drain()
    with session_scope(lane.api.client.app.state.session_factory) as session:
        resolve_project(session, UUID(lane.pid))
    lane.sql("DELETE FROM series_axis")  # the wellbore stays but the project has no log series
    (wid,) = _bores(lane).values()
    chart = _chart(_chart_set(lane, wid), ChartKey.LOG_TRACKS)
    assert chart.series == [] and chart.empty is not None
    assert chart.empty.reason is ChartEmptyReason.NO_RECORDS


def test_field_set_has_explicit_stratigraphic_correlation_state(lane: Lane) -> None:
    lane.upload([("a.las", las_text(_rows(5), well="15/9-F-99").encode())])
    lane.drain()
    r = lane.api.client.get(f"/api/v1/projects/{lane.pid}/charts/field")
    assert r.status_code == 200, r.text
    charts = FieldChartSet.model_validate(r.json())
    (strat,) = [c for c in charts.charts if c.key is ChartKey.STRATIGRAPHIC_CORRELATION]
    assert strat.series == [] and strat.empty is not None
    assert strat.empty.reason is ChartEmptyReason.NO_RECORDS

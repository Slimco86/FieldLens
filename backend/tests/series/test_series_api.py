"""DC-8/DC-9 through the API on PostgreSQL: listing, windows, bounds, nulls, hostile params,
project scoping. Synthetic uploads only."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import URL

import fieldlens.series.service as service_module
from tests.series.support import NULL, Lane, day_row, las_text, workbook_bytes


def _rows(n: int) -> list[list[float]]:
    rng = np.random.default_rng(3)
    gr = np.cumsum(rng.normal(size=n)) + 50
    out = [[100.0 + i * 0.5, float(gr[i]), 2.0 + (i % 7) / 100] for i in range(n)]
    if n > 700:
        for i in range(300, 340):
            out[i][1] = NULL
        out[700][1] = float(gr.max() + 500)  # spike
    return out


@pytest.fixture
def lane(migrated_url: URL, tmp_path: Path, engine: Engine) -> Lane:
    return Lane(migrated_url, tmp_path, engine)


def _gr(lane: Lane, doc: str | None = None) -> dict[str, Any]:
    items = lane.series(mnemonic="gr", **({"document_id": doc} if doc else {}))
    assert len(items) == 1
    return items[0]


def test_list_filters_ranges_units_and_evidence(lane: Lane) -> None:
    rows = _rows(1000)
    (doc,) = lane.upload([("a.las", las_text(rows).encode())])
    lane.drain()
    other = lane.upload([("b.las", las_text(rows[:50], well="15/9-F-98").encode())])[0]
    lane.drain()
    items = lane.series()
    assert [i["measure"] for i in items].count("GR") == 2
    gr = _gr(lane, doc)
    assert gr["kind"] == "log" and gr["unit"] == "GAPI" and gr["unit_status"] == "stated"
    assert gr["sample_count"] == 1000 and gr["null_count"] == 40 and gr["valid_count"] == 960
    assert gr["null_sentinel"] == NULL
    assert gr["index"]["type"] == "depth" and gr["index"]["unit"] == "M"
    assert gr["index"]["first"] == 100.0 and gr["index"]["last"] == 599.5
    assert gr["index"]["order"] == "increasing"
    assert gr["well_name"] == "15/9-F-99" and gr["wellbore_label"] is None
    ev = gr["evidence"]
    assert ev["position_kind"] == "line" and ev["record_ordinal"] is not None
    assert ev["profile_name"] == "las_2_0" and ev["profile_version"] == "2"
    assert ev["locator"]["curve_locator"]["las_section"] == "curve"
    assert ev["first_source_position"] < ev["last_source_position"]
    rhob = lane.series(mnemonic="RHOB", document_id=doc)[0]
    assert rhob["unit"] is None and rhob["unit_status"] == "missing"
    assert {i["document_id"] for i in lane.series(document_id=other)} == {other}
    assert lane.series(kind="production") == []
    assert lane.series(kind="log", mnemonic="nope") == []
    page = lane.get("", limit=2, offset=1).json()
    assert len(page["items"]) == 2 and page["total"] == len(items) and page["next_offset"] == 3
    assert lane.get(f"/{gr['series_id']}").json()["series_id"] == gr["series_id"]


def test_window_bounds_nulls_downsampling_and_determinism(lane: Lane) -> None:
    rows = _rows(1000)
    (doc,) = lane.upload([("a.las", las_text(rows).encode())])
    lane.drain()
    sid = _gr(lane, doc)["series_id"]
    full = lane.get(f"/{sid}/window", resolution="full").json()
    assert full["returned_points"] == 1000 and full["downsampled"] is False
    assert full["algorithm"] is None and full["dates"] is None
    assert full["values"][300] is None and full["values"][339] is None, "NULL -> real null"
    assert full["values"][340] is not None
    assert full["index"][0] == 100.0 and full["index"][-1] == 599.5
    # inclusive bounds on a contiguous slice
    w = lane.get(f"/{sid}/window", **{"from": "110", "to": "112", "resolution": "full"}).json()
    assert w["index"] == [110.0, 110.5, 111.0, 111.5, 112.0]
    assert w["values"] == full["values"][20:25]
    assert w["requested_from"] == "110" and w["source_samples_in_window"] == 5
    # out-of-range windows are empty, not an error and not a fabricated sample
    empty = lane.get(f"/{sid}/window", **{"from": "9000", "to": "9100"}).json()
    assert empty["returned_points"] == 0 and empty["index"] == [] and empty["values"] == []
    # downsampled: bounded, deterministic, spike and gap survive, same cache key
    d1 = lane.get(f"/{sid}/window", max_points=50).json()
    d2 = lane.get(f"/{sid}/window", max_points=50).json()
    assert d1 == d2 and d1["cache_key"] == d2["cache_key"]
    assert d1["downsampled"] is True and d1["returned_points"] <= 50
    assert d1["algorithm"] == "minmax-gap-v1" and d1["source_samples_in_window"] == 1000
    assert max(v for v in d1["values"] if v is not None) == max(
        v for v in full["values"] if v is not None
    )
    assert None in d1["values"], "the null gap stays visible"
    assert d1["index"] == sorted(d1["index"])
    assert d1["null_samples_in_window"] == 40
    other = lane.get(f"/{sid}/window", max_points=51).json()
    assert other["cache_key"] != d1["cache_key"]
    assert (
        lane.get(f"/{sid}/window", max_points=50, **{"from": "100"}).json()["cache_key"]
        != d1["cache_key"]
    )
    # window units and evidence ride along
    assert d1["series"]["unit"] == "GAPI" and d1["series"]["evidence"]["record_ordinal"] is not None


def test_full_resolution_is_capped(lane: Lane, monkeypatch: pytest.MonkeyPatch) -> None:
    (doc,) = lane.upload([("a.las", las_text(_rows(120)).encode())])
    lane.drain()
    sid = _gr(lane, doc)["series_id"]
    monkeypatch.setattr(service_module, "FULL_RESOLUTION_LIMIT", 100)
    r = lane.get(f"/{sid}/window", resolution="full")
    assert r.status_code == 422 and "limited to 100" in r.json()["error"]["message"]
    assert (
        lane.get(f"/{sid}/window", resolution="downsampled", max_points=10_000).status_code == 200
    )


def test_unordered_index_windows_keep_source_order(lane: Lane) -> None:
    rows = [[3.0, 30.0, 1.0], [1.0, 10.0, 1.0], [2.0, 20.0, 1.0], [5.0, 50.0, 1.0]]
    (doc,) = lane.upload([("u.las", las_text(rows).encode())])
    lane.drain()
    gr = _gr(lane, doc)
    assert gr["index"]["order"] == "unordered"
    w = lane.get(f"/{gr['series_id']}/window", **{"from": "2", "to": "3"}).json()
    assert w["index"] == [3.0, 2.0] and w["values"] == [30.0, 20.0]


def test_production_series_dates_nulls_units_and_zero_fill(lane: Lane) -> None:
    daily = [
        day_row(40000, "15/9-F-A", 1, 10.0),
        day_row(40001, "15/9-F-A", 1, "NULL"),
        day_row(40003, "15/9-F-A", 1, 0),
        day_row(40000, "15/9-F-B", 2, 5.0),
    ]
    (doc,) = lane.upload([("prod.xlsx", workbook_bytes(daily))])
    lane.drain()
    a = lane.series(wellbore_label="NO 15/9-F-A", mnemonic="bore_oil_vol")
    assert len(a) == 1 and lane.series(wellbore_label="NO 15/9-F-B", mnemonic="bore_oil_vol")
    s = a[0]
    assert s["kind"] == "production" and s["unit"] is None and s["unit_status"] == "missing"
    assert s["index"]["encoding"] == "epoch_days" and s["index"]["first_date"] == "2009-07-06"
    assert s["index"]["last_date"] == "2009-07-09" and s["index"]["type"] == "time"
    assert s["sample_count"] == 3 and s["null_count"] == 1 and s["wellbore_label"] == "NO 15/9-F-A"
    assert s["evidence"]["position_kind"] == "row" and s["evidence"]["first_source_position"] == 2
    assert s["evidence"]["locator"]["cell_range"].startswith("F")
    w = lane.get(f"/{s['series_id']}/window", **{"from": "2009-07-07", "to": "2009-07-09"}).json()
    assert w["dates"] == ["2009-07-07", "2009-07-09"], "absent 2009-07-08 stays absent"
    assert w["values"] == [None, 0.0], "missing is null, a real zero stays zero"
    for bad in ("5", "2009-13-40", "2009-7-1", "x"):
        assert lane.get(f"/{s['series_id']}/window", **{"from": bad}).status_code == 422
    # wellbores are never pooled
    assert {i["wellbore_label"] for i in lane.series(kind="production")} == {
        "NO 15/9-F-A",
        "NO 15/9-F-B",
    }


def test_hostile_and_malformed_parameters(lane: Lane) -> None:
    (doc,) = lane.upload([("a.las", las_text(_rows(30)).encode())])
    lane.drain()
    sid = _gr(lane, doc)["series_id"]
    win = f"/{sid}/window"
    bad: list[dict[str, Any]] = [
        {"from": "nan"},
        {"from": "inf"},
        {"from": "1_0"},
        {"from": "1e999"},
        {"from": "10", "to": "9"},
        {"from": "a\x00b"},
        {"to": "\x00"},
        {"max_points": 9},
        {"max_points": 10_001},
        {"max_points": "x"},
        {"resolution": "everything"},
        {"unexpected": "1"},
        {"from": ""},
        {"from": "9" * 65},
    ]
    for params in bad:
        r = lane.get(win, **params)
        assert r.status_code == 422, (params, r.status_code, r.text[:200])
        assert r.json()["error"]["code"] == "VALIDATION_ERROR"
    for params in (
        {"mnemonic": "a\x00"},
        {"wellbore_label": "\x00"},
        {"kind": "other"},
        {"limit": 0},
        {"limit": 501},
        {"offset": -1},
        {"document_id": "nope"},
        {"junk": 1},
    ):
        assert lane.get("", **params).status_code == 422, params
    assert lane.get("/not-a-uuid").status_code == 422
    assert lane.get(f"/{uuid4()}").status_code == 404
    assert lane.get(f"/{uuid4()}/window").status_code == 404
    # SQL-shaped and traversal-shaped text is only ever data
    assert lane.series(mnemonic="gr'; drop table series_curve; --") == []
    assert lane.series(wellbore_label="../../etc/passwd") == []
    assert lane.get(win, **{"from": "10; select 1"}).status_code == 422
    r = lane.get(win)
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert lane.get("").headers["cache-control"] == "no-store"


def test_series_are_project_scoped(lane: Lane) -> None:
    (doc,) = lane.upload([("a.las", las_text(_rows(30)).encode())])
    lane.drain()
    sid = _gr(lane, doc)["series_id"]
    other = lane.api.project("Other")
    base = f"/api/v1/projects/{other}/series"
    assert lane.api.client.get(base).json()["items"] == []
    assert lane.api.client.get(f"{base}/{sid}").status_code == 404
    assert lane.api.client.get(f"{base}/{sid}/window").status_code == 404
    assert lane.api.client.get(f"{base}?document_id={doc}").json()["total"] == 0
    assert lane.api.client.get(f"/api/v1/projects/{uuid4()}/series").status_code == 404
    assert lane.api.client.get(f"/api/v1/projects/{uuid4()}/series/{sid}").status_code == 404

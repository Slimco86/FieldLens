"""DTO registry, OpenAPI surface and the checked-in generated TypeScript for the series API."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from fieldlens.app import create_app
from fieldlens.contracts.registry import public_models
from fieldlens.contracts.series import (
    FULL_RESOLUTION_LIMIT,
    MAX_SERIES_WINDOW_POINTS,
    SeriesWindowQuery,
)
from tests.conftest import settings_for

GENERATED = Path(__file__).resolve().parents[3] / "frontend" / "src" / "api" / "generated.ts"
DTOS = {
    "SeriesInfo",
    "SeriesList",
    "SeriesListQuery",
    "SeriesWindow",
    "SeriesWindowQuery",
    "SeriesIndex",
    "SeriesEvidence",
}


def test_series_dtos_are_registered_in_openapi_and_generated_types() -> None:
    assert DTOS <= {m.__name__ for m in public_models()}
    spec = create_app(settings_for(database_url=None)).openapi()
    assert DTOS <= set(spec["components"]["schemas"])
    paths = spec["paths"]
    for suffix in ("/series", "/series/{series_id}", "/series/{series_id}/window"):
        entry = paths[f"/api/v1/projects/{{project_id}}{suffix}"]
        assert set(entry) == {"get"}, "read-only"
    params = {
        p["name"]
        for p in paths["/api/v1/projects/{project_id}/series/{series_id}/window"]["get"][
            "parameters"
        ]
    }
    assert {"from", "to", "max_points", "resolution"} <= params
    ts = GENERATED.read_text()
    for name in DTOS - {"SeriesListQuery", "SeriesWindowQuery"}:
        assert f"{name}: {{" in ts, name
    assert "/api/v1/projects/{project_id}/series/{series_id}/window" in ts


def test_window_schema_is_bounded() -> None:
    schema = create_app(settings_for(database_url=None)).openapi()["components"]["schemas"]
    window = schema["SeriesWindow"]["properties"]
    for field in ("index", "values"):
        assert window[field]["maxItems"] == FULL_RESOLUTION_LIMIT
    assert schema["SeriesWindowQuery"]["properties"]["max_points"]["maximum"] == (
        MAX_SERIES_WINDOW_POINTS
    )


@pytest.mark.parametrize(
    "bad", [{"max_points": 9}, {"max_points": 10_001}, {"to": "a\x00"}, {"x": 1}]
)
def test_window_query_rejects_out_of_range_and_unknown(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SeriesWindowQuery(**bad)  # type: ignore[arg-type]


def test_window_query_accepts_the_from_alias() -> None:
    assert SeriesWindowQuery.model_validate({"from": "1", "to": "2"}).from_ == "1"

"""Explore enrichment contracts (TASK-094): AppLink validation, enums, registry coverage."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from fieldlens.contracts import (
    charts,
    chat,
    context_layers,
    export_component_schemas,
    public_models,
)
from fieldlens.contracts.charts import (
    ChartAxis,
    ChartKey,
    ChartKind,
    ChartPoint,
    ChartScope,
    ChartSeries,
    ChartSeriesScope,
    ChartSpec,
    DownsampleInfo,
    SeriesAggregates,
)
from fieldlens.contracts.chat import (
    AnswerBlock,
    AppLink,
    ChatMessage,
    ChatRole,
    ChatRunState,
    ChatTurn,
    ChatUsage,
)
from fieldlens.contracts.context_layers import (
    DatumStatus,
    DepthReference,
    DepthValue,
    FormationSurface,
    FormationTier,
    InterpretationStatus,
)

DOC = uuid.uuid4()
REV = uuid.uuid4()
NOW = datetime(2026, 11, 3, tzinfo=UTC)


def _link(target: dict[str, object]) -> AppLink:
    return AppLink.model_validate({"label": "open", "target": target})


def test_run_states_cover_spec() -> None:
    assert {s.value for s in ChatRunState} == {
        "queued",
        "running",
        "completed",
        "failed",
        "cancelled",
        "refused",
        "truncated",
    }


def test_tier_and_status_enums() -> None:
    assert {t.value for t in FormationTier} == {"T1", "T2", "T3", "T4"}
    assert {s.value for s in InterpretationStatus} >= {"observed", "illustrative", "interpolated"}


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "source", "document_id": str(DOC), "page": 3},
        {"kind": "element", "element_id": str(uuid.uuid4())},
        {"kind": "wellbore", "wellbore_id": str(uuid.uuid4())},
        {"kind": "formation", "surface_key": "hugin"},
        {
            "kind": "chart",
            "chart_key": "production_rates",
            "window": {"from": "2020-01-01", "to": "2020-06-01"},
        },
    ],
)
def test_app_link_accepts_typed_targets(target: dict[str, object]) -> None:
    link = _link(target)
    assert link.target.root.kind == target["kind"]


@pytest.mark.parametrize(
    "target",
    [
        {"kind": "url", "href": "https://example.com"},
        {"kind": "source", "document_id": str(DOC)},
        {"kind": "source", "document_id": str(DOC), "page": 0},
        {"kind": "wellbore", "wellbore_id": "not-a-uuid"},
        {"kind": "chart", "chart_key": "nope"},
        {"kind": "chart", "chart_key": "production_rates", "window": {"from": "yesterday"}},
        {
            "kind": "chart",
            "chart_key": "production_rates",
            "window": {"from": "2021-01-01", "to": "2020-01-01"},
        },
        {"kind": "formation", "surface_key": "x", "script": "alert(1)"},
        {
            "kind": "source",
            "document_id": str(DOC),
            "page": 2,
            "locator": {
                "kind": "pdf",
                "document_id": str(DOC),
                "source_revision_id": str(REV),
                "page": 5,
            },
        },
    ],
)
def test_app_link_rejects_invalid_targets(target: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        _link(target)


def test_answer_block_is_closed_and_discriminated() -> None:
    adapter = TypeAdapter(AnswerBlock)
    assert adapter.validate_python({"kind": "gap", "reason": "no_data", "text": "none"})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "value", "label": "x", "tool_call_id": str(uuid.uuid4()), "result_path": "a"}
        )
    with pytest.raises(ValidationError):
        adapter.validate_python({"kind": "code", "text": "rm -rf"})
    with pytest.raises(ValidationError):
        adapter.validate_python(
            {"kind": "chart", "request": {"chart_key": "custom", "points": [1]}}
        )


def test_chat_usage_has_no_spend_ceiling_fields() -> None:
    fields = set(ChatUsage.model_fields)
    assert not {f for f in fields if "budget" in f or "ceiling" in f or "cap" in f}


def test_turn_state_invariants() -> None:
    user = ChatMessage(
        message_id=uuid.uuid4(),
        conversation_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        role=ChatRole.USER,
        text="hi",
        created_at=NOW,
    )
    base = {
        "turn_id": user.turn_id,
        "conversation_id": user.conversation_id,
        "project_id": uuid.uuid4(),
        "user_message": user,
        "created_at": NOW,
    }
    assert ChatTurn(state=ChatRunState.QUEUED, **base)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ChatTurn(state=ChatRunState.FAILED, completed_at=NOW, **base)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ChatTurn(state=ChatRunState.REFUSED, **base)  # type: ignore[arg-type]


def test_depth_value_never_assumes_datum_or_unit() -> None:
    with pytest.raises(ValidationError):
        DepthValue(reference=DepthReference.TVD, value=1.0, datum_status=DatumStatus.UNKNOWN)
    with pytest.raises(ValidationError):
        DepthValue(reference=DepthReference.TVDSS, value=None, datum_status=DatumStatus.UNKNOWN)
    with pytest.raises(ValidationError):
        DepthValue(
            reference=DepthReference.TVD,
            value=1.0,
            unit="m",
            datum="KB",
            datum_status=DatumStatus.UNKNOWN,
        )
    ok = DepthValue(
        reference=DepthReference.TVD, value=1.0, unit="m", datum_status=DatumStatus.UNKNOWN
    )
    assert ok.datum is None


def test_surface_tier_requires_matching_geometry_and_status() -> None:
    with pytest.raises(ValidationError):
        FormationSurface(
            surface_key="a",
            name="A",
            tier=FormationTier.T2,
            tier_label="T2",
            status=InterpretationStatus.ILLUSTRATIVE,
            scope=context_layers.FormationScope.WELLBORE,
            wellbore_ids=[uuid.uuid4()],
        )
    with pytest.raises(ValidationError):
        FormationSurface(
            surface_key="a",
            name="A",
            tier=FormationTier.T1,
            tier_label="T1",
            status=InterpretationStatus.ILLUSTRATIVE,
            scope=context_layers.FormationScope.WELLBORE,
            wellbore_ids=[uuid.uuid4()],
        )


def _series(points: list[ChartPoint], *, source: int | None = None) -> ChartSeries:
    return ChartSeries(
        series_key="oil",
        name="Oil",
        axis_id="y1",
        unit="Sm3/d",
        scope=ChartSeriesScope(scope=ChartScope.WELL, scope_label="well-level"),
        points=points,
        downsample=DownsampleInfo(
            applied=False,
            source_points=len(points) if source is None else source,
            returned_points=len(points),
        ),
        aggregates=SeriesAggregates(count=len(points), valid_count=1, null_count=1),
    )


def _spec(series: list[ChartSeries], empty: charts.ChartEmptyState | None = None) -> ChartSpec:
    return ChartSpec(
        chart_id="c",
        key=ChartKey.PRODUCTION_RATES,
        title="Rates",
        kind=ChartKind.LINE,
        scope=ChartSeriesScope(scope=ChartScope.WELL, scope_label="well-level"),
        axes=[
            ChartAxis(
                axis_id="y1",
                name="Rate",
                kind=charts.AxisKind.VALUE,
                position=charts.AxisPosition.Y_LEFT,
                unit="Sm3/d",
            )
        ],
        series=series,
        empty=empty,
        as_of=date(2020, 1, 1),
        cache_key="k",
    )


def test_chart_gaps_preserved_and_empty_state_exclusive() -> None:
    spec = _spec([_series([ChartPoint(x="2020-01-01", y=1.0), ChartPoint(x="2020-01-02", y=None)])])
    assert spec.series[0].points[1].y is None
    with pytest.raises(ValidationError):
        _spec([])  # neither series nor empty state
    with pytest.raises(ValidationError):
        _spec(
            [_series([ChartPoint(x=1.0, y=1.0), ChartPoint(x=2.0, y=None)])],
            charts.ChartEmptyState(reason=charts.ChartEmptyReason.NO_RECORDS, message="none"),
        )
    assert _spec(
        [], charts.ChartEmptyState(reason=charts.ChartEmptyReason.NO_RECORDS, message="none")
    )


def test_chart_scope_never_attributes_well_level_to_a_wellbore() -> None:
    with pytest.raises(ValidationError):
        ChartSeriesScope(scope=ChartScope.WELL, scope_label="well-level", wellbore_id=uuid.uuid4())
    with pytest.raises(ValidationError):
        ChartSeriesScope(scope=ChartScope.WELLBORE, scope_label="wellbore")


def test_unknown_axis_rejected() -> None:
    series = _series([ChartPoint(x=1.0, y=1.0), ChartPoint(x=2.0, y=None)])
    bad = series.model_copy(update={"axis_id": "missing"})
    with pytest.raises(ValidationError):
        _spec([bad])


def test_new_modules_registered_and_exported() -> None:
    names = {m.__name__ for m in public_models()}
    for module in (context_layers, charts, chat):
        defined = {
            n
            for n, o in vars(module).items()
            if isinstance(o, type)
            and o.__module__ == module.__name__
            and not n.startswith("_")
            and hasattr(o, "model_fields")
        }
        assert defined, module.__name__
        assert defined <= names
    schemas = export_component_schemas()
    for name in (
        "FormationLayerSet",
        "WellboreChartSet",
        "FieldChartSet",
        "AppLink",
        "AnswerBlock",
        "ChatTurn",
        "ChartSpec",
    ):
        assert name in schemas

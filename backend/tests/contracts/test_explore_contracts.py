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
        gap_count=sum(1 for p in points if p.y is None),
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


def _scene(value: float = -1000.0, **kw: object) -> DepthValue:
    return DepthValue(
        reference=DepthReference.SCENE_ELEVATION,
        value=value,
        unit="m",
        datum_status=DatumStatus.NOT_APPLICABLE,
        **kw,  # type: ignore[arg-type]
    )


def _plane(**kw: object) -> context_layers.LevelPlane:
    return context_layers.LevelPlane(
        elevation=_scene(),
        footprint=context_layers.PlaneFootprint(
            min_east=0, max_east=10, min_north=0, max_north=10, margin_m=1
        ),
        **kw,  # type: ignore[arg-type]
    )


def _pick(wellbore: uuid.UUID, **kw: object) -> context_layers.FormationPick:
    return context_layers.FormationPick(
        pick_id=uuid.uuid4(),
        wellbore_id=wellbore,
        surface_key="a",
        surface_name="A",
        name="A",
        validation_state=context_layers.ValidationState.VALID,
        **kw,  # type: ignore[arg-type]
    )


def _surface(wellbores: list[uuid.UUID], **kw: object) -> FormationSurface:
    base: dict[str, object] = {
        "surface_key": "a",
        "name": "A",
        "tier": FormationTier.T1,
        "tier_label": "T1 pick - observed",
        "status": InterpretationStatus.OBSERVED,
        "scope": context_layers.FormationScope.PROJECT,
        "wellbore_ids": wellbores,
    }
    base.update(kw)
    return FormationSurface(**base)  # type: ignore[arg-type]


def _layer_set(
    surfaces: list[FormationSurface], **frame: object
) -> context_layers.FormationLayerSet:
    return context_layers.FormationLayerSet(
        project_id=uuid.uuid4(),
        frame=context_layers.FormationFrame(**frame),  # type: ignore[arg-type]
        surfaces=surfaces,
        generated_from_revision="r",
    )


def test_d1_truthful_labels() -> None:
    assert _plane().label == context_layers.LEVEL_PLANE_LABEL
    with pytest.raises(ValidationError):
        _plane(label="Interpreted horizon")
    with pytest.raises(ValidationError):
        _plane(note="geologic horizon")
    wb = uuid.uuid4()
    with pytest.raises(ValidationError):
        _pick(wb, tier=FormationTier.T1, status=InterpretationStatus.INTERPOLATED)
    with pytest.raises(ValidationError):
        _pick(wb, label="horizon")
    assert _pick(wb).status is InterpretationStatus.OBSERVED
    t2: dict[str, object] = {
        "tier": FormationTier.T2,
        "status": InterpretationStatus.ILLUSTRATIVE,
        "scope": context_layers.FormationScope.WELLBORE,
        "plane": _plane(),
    }
    with pytest.raises(ValidationError):
        _surface([wb], tier_label="Interpreted horizon", **t2)
    assert _surface([wb], tier_label=context_layers.LEVEL_PLANE_LABEL, **t2)


def test_d2_project_scope_requires_shared_reference() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    with pytest.raises(ValidationError):
        _layer_set([_surface([a, b])])
    with pytest.raises(ValidationError):
        _layer_set(
            [_surface([a, b])],
            vertical_reference_status=DatumStatus.UNKNOWN,
        )
    with pytest.raises(ValidationError):  # stated status without a name
        context_layers.FormationFrame(vertical_reference_status=DatumStatus.STATED)
    stated = {"vertical_reference": "MSL", "vertical_reference_status": DatumStatus.STATED}
    assert _layer_set([_surface([a, b])], **stated)
    blocked = context_layers.FormationBlocked(
        reason=context_layers.FormationBlockReason.DATUM_MISMATCH, message="differ"
    )
    assert _layer_set([_surface([a, b], blocked=[blocked])])


def test_d3_chart_series_integrity() -> None:
    pts = [ChartPoint(x="2020-01-01", y=1.0), ChartPoint(x="2020-01-02", y=None)]
    good = _series(pts)
    assert _spec([good])

    def agg(**kw: object) -> SeriesAggregates:
        base: dict[str, object] = {"count": 2, "valid_count": 1, "null_count": 1}
        base.update(kw)
        return SeriesAggregates(**base)  # type: ignore[arg-type]

    assert agg(minimum=1, maximum=2)
    with pytest.raises(ValidationError):
        agg(minimum=3, maximum=2)
    with pytest.raises(ValidationError):
        agg(count=5, valid_count=1, null_count=0)
    with pytest.raises(ValidationError):
        good.model_validate({**good.model_dump(), "gap_count": 0})
    with pytest.raises(ValidationError):
        DownsampleInfo(applied=False, source_points=100, returned_points=2)
    with pytest.raises(ValidationError):
        DownsampleInfo(applied=True, source_points=2, returned_points=3)
    assert DownsampleInfo(applied=True, source_points=100, returned_points=10)
    with pytest.raises(ValidationError):
        _spec([good.model_copy(update={"unit": "bbl/d"})])
    wb = uuid.uuid4()
    wb_scope = ChartSeriesScope(scope=ChartScope.WELLBORE, scope_label="wb", wellbore_id=wb)
    with pytest.raises(ValidationError):  # wellbore series in a well-level chart
        _spec([good.model_copy(update={"scope": wb_scope})])
    for bad_x in ("not a date", "20200101", "5", " 2020-01-01"):
        with pytest.raises(ValidationError):
            ChartPoint(x=bad_x, y=1.0)
    with pytest.raises(ValidationError):
        ChartPoint(x=1.0, y="5")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        ChartPoint(x=1.0, y=True)  # type: ignore[arg-type]
    assert ChartPoint(x="2020-01-01T00:00:00Z", y=1)
    with pytest.raises(ValidationError):
        charts.ChartWindow.model_validate({"from": "2020-02-01", "to": "2020-01-01"})
    with pytest.raises(ValidationError):
        ChartSpec.model_validate({**_spec([good]).model_dump(), "window": {"from": "9", "to": "2"}})


def test_d4_window_bounds_are_strict() -> None:
    for bound in ("1e999", " 5", "20200101", "nan", "inf", "2020-13-01"):
        with pytest.raises(ValidationError):
            _link({"kind": "chart", "chart_key": "production_rates", "window": {"from": bound}})
    with pytest.raises(ValidationError):
        _link(
            {
                "kind": "chart",
                "chart_key": "production_rates",
                "window": {"from": "2020-01-01", "to": "5"},
            }
        )
    assert _link(
        {"kind": "chart", "chart_key": "production_rates", "window": {"from": "1.5", "to": "1e3"}}
    )


def test_d5_degenerate_mesh_and_datum_rules() -> None:
    ids = [uuid.uuid4() for _ in range(3)]

    def mesh(positions: list[float], indices: list[int]) -> context_layers.SurfaceMesh:
        return context_layers.SurfaceMesh(
            positions=positions,
            indices=indices,
            method="tin",
            support_polygon=[[0, 0], [1, 0], [0, 1]],
            pick_ids=ids,
        )

    good = [0, 0, 0, 1, 0, 0, 0, 1, 0]
    assert mesh(good, [0, 1, 2])
    with pytest.raises(ValidationError):
        mesh(good, [0, 1, 1])
    with pytest.raises(ValidationError):
        mesh([0, 0, 0, 1, 1, 0, 2, 2, 0], [0, 1, 2])  # collinear
    with pytest.raises(ValidationError):
        DepthValue(
            reference=DepthReference.MD,
            value=1.0,
            unit="m",
            datum="KB",
            datum_status=DatumStatus.STATED,
        )
    with pytest.raises(ValidationError):
        _scene(datum="MSL")
    with pytest.raises(ValidationError):
        DepthValue(
            reference=DepthReference.SCENE_ELEVATION,
            value=1.0,
            unit="m",
            datum_status=DatumStatus.STATED,
        )


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

"""Formation and equipment tools plus AppLink validation (no DB: services are faked)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from fieldlens.assistant.messages import ToolCallPart
from fieldlens.chat import tools as tools_module
from fieldlens.chat.answer import AnswerValidator
from fieldlens.chat.evidence_pool import TurnEvidence
from fieldlens.chat.tools import TOOLS, ToolRunner, element_uuid
from fieldlens.contracts.asset_spec import (
    AssetComponent,
    SpecGenerator,
    SpecState,
    SpecStatus,
    VisualAssetSpec,
    VisualAssetSpecRecord,
)
from fieldlens.contracts.chat import ChatContext, DroppedBlockReason
from fieldlens.contracts.context_layers import (
    LEVEL_PLANE_LABEL,
    DatumStatus,
    DepthReference,
    DepthValue,
    FormationFrame,
    FormationLayerSet,
    FormationPick,
    FormationScope,
    FormationSurface,
    FormationTier,
    InterpretationStatus,
    LevelPlane,
    PlaneFootprint,
)
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import EvidenceLink, PdfLocator, ValidationState
from tests.chat.support import INJECTION

PID = uuid4()
WB = uuid4()
WB2 = uuid4()
OTHER_WB = uuid4()  # exists in some other project
DOC = uuid4()
REV = uuid4()
PICK = uuid4()
SPEC_ID = uuid4()


class Scope:
    def __init__(self, wellbores: set[UUID]) -> None:
        self._w = wellbores

    def document_exists(self, document_id: UUID) -> bool:
        return document_id == DOC

    def wellbore_exists(self, wellbore_id: UUID) -> bool:
        return wellbore_id in self._w


def _link(page: int = 4) -> EvidenceLink:
    return EvidenceLink(
        document_id=DOC,
        source_revision_id=REV,
        locator=PdfLocator(document_id=DOC, source_revision_id=REV, page=page),  # type: ignore[arg-type]
    )


def _depth(ref: DepthReference, value: float) -> DepthValue:
    datum = DatumStatus.NOT_APPLICABLE if ref is DepthReference.MD else DatumStatus.UNKNOWN
    return DepthValue(
        reference=ref,
        value=value,
        unit="m",
        datum_status=datum,
        unknown_reason=None,
    )


def _layer_set(wellbore_id: UUID | None) -> FormationLayerSet:
    pick = FormationPick(
        pick_id=PICK,
        wellbore_id=WB,
        surface_key="top-brent",
        surface_name="Top Brent",
        name="Top Brent",
        md=_depth(DepthReference.MD, 2310.5),
        tvd=_depth(DepthReference.TVD, 2105.25),
        validation_state=ValidationState.VALID,
        tier=FormationTier.T2,
        status=InterpretationStatus.ILLUSTRATIVE,
        label="pick - illustrative",
        evidence=[_link()],
    )
    surface = FormationSurface(
        surface_key="top-brent",
        name="Top Brent",
        tier=FormationTier.T2,
        tier_label=LEVEL_PLANE_LABEL,
        status=InterpretationStatus.ILLUSTRATIVE,
        scope=FormationScope.WELLBORE,
        wellbore_ids=[WB],
        picks=[pick],
        plane=LevelPlane(
            elevation=_depth(DepthReference.SCENE_ELEVATION, -2105.25),
            footprint=PlaneFootprint(
                min_east=-10, max_east=10, min_north=-10, max_north=10, margin_m=5
            ),
        ),
        evidence=[_link()],
    )
    return FormationLayerSet(
        project_id=PID,
        wellbore_id=wellbore_id,
        frame=FormationFrame(),
        surfaces=[surface],
        generated_from_revision="rev-1",
    )


def _spec_record(label: str = "ESP pump") -> VisualAssetSpecRecord:
    comps = [
        AssetComponent.model_validate(
            {
                "id": "esp-1",
                "kind": "pump_esp",
                "label": label,
                "placement": {"state": "located", "md_top": 1500, "md_bottom": 1530, "unit": "m"},
                "representation": "generic_illustrative",
            }
        ),
        AssetComponent.model_validate(
            {
                "id": "packer-1",
                "kind": "packer",
                "label": "Packer",
                "placement": {"state": "unlocated", "reason": "depth not stated"},
                "representation": "catalog_reference",
                "params": {"od": {"value": 5.5, "unit": "in"}},
            }
        ),
    ]
    spec = VisualAssetSpec(
        project_id=PID,
        wellbore_id=WB,
        source_revision="srcrev",
        generator=SpecGenerator(provider="stub", model="stub"),
        generated_at=datetime(2024, 1, 1, tzinfo=UTC),
        status=SpecStatus.CURRENT,
        components=comps,
    )
    return VisualAssetSpecRecord(
        spec_id=SPEC_ID,
        revision=2,
        state=SpecState.CURRENT,
        created_at=datetime(2024, 1, 1, tzinfo=UTC),
        spec=spec,
    )


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {}

    @contextmanager
    def scope(_factory: Any):  # type: ignore[no-untyped-def]
        yield None

    def layer_set(_s: Any, project_id: UUID, wellbore_id: UUID | None = None) -> FormationLayerSet:
        calls["layers"] = (project_id, wellbore_id)
        if wellbore_id is not None and wellbore_id not in {WB, WB2}:
            raise ContractError(ErrorCode.NOT_FOUND, "wellbore not found", 404)
        return _layer_set(wellbore_id)

    def current(_s: Any, project_id: UUID, wellbore_id: UUID) -> VisualAssetSpecRecord:
        calls["spec"] = (project_id, wellbore_id)
        if wellbore_id != WB:
            raise ContractError(ErrorCode.NOT_FOUND, "no asset spec for this wellbore yet", 404)
        return _spec_record(calls.get("label", "ESP pump")[:120])

    monkeypatch.setattr(tools_module, "session_scope", scope)
    monkeypatch.setattr(tools_module.formation_service, "formation_layer_set", layer_set)
    monkeypatch.setattr(tools_module.assetspec, "get_current", current)
    return calls


def _run(
    name: str, args: dict[str, Any], ev: TurnEvidence | None = None
) -> tuple[Any, TurnEvidence]:
    ev = ev or TurnEvidence()
    runner = ToolRunner(
        project_id=PID,
        factory=None,  # type: ignore[arg-type]
        retrieval=None,
        series=None,
        context=ChatContext(),
        evidence=ev,
    )
    out = json.loads(runner.execute(ToolCallPart(call_id="c", name=name, arguments=args)))
    return out, ev


def _validator(ev: TurnEvidence) -> AnswerValidator:
    return AnswerValidator(
        project_id=PID,
        evidence=ev,
        scope=Scope({WB, WB2}),
        series=None,
        context=ChatContext(),
        tool_calls_made=1,
    )


def _link_block(target: dict[str, Any]) -> dict[str, Any]:
    return {"kind": "link", "link": {"label": "open", "target": target}}


# --- allowlist ---------------------------------------------------------------------------------


def test_new_tools_are_allowlisted_closed_and_unscoped() -> None:
    for name in ("get_formation_picks", "get_formation_layers", "get_equipment_summary"):
        tool = TOOLS[name]
        assert tool.args.model_config.get("extra") == "forbid"
        assert "project_id" not in tool.args.model_fields
    assert not any("approach" in n for n in TOOLS)  # no closest-approach service is exposed


@pytest.mark.parametrize("name", ["get_formation_picks", "get_formation_layers"])
def test_formation_tools_reject_extra_arguments(name: str, fakes: dict[str, Any]) -> None:
    out, _ = _run(name, {"project_id": str(uuid4())})
    assert out["ok"] is False and "layers" not in fakes
    out, _ = _run(name, {"wellbore_id": "not-a-uuid"})
    assert out["ok"] is False


# --- formations --------------------------------------------------------------------------------


def test_formation_picks_report_depths_source_and_illustrative_tier(fakes: dict[str, Any]) -> None:
    out, ev = _run("get_formation_picks", {"wellbore_id": str(WB)})
    assert out["ok"] is True and fakes["layers"] == (PID, WB)
    pick = out["result"]["picks"][0]
    assert pick["md"]["value"] == 2310.5 and pick["tvd"]["value"] == 2105.25
    assert pick["label"] == "pick - illustrative" and pick["cite"] == "[1]"
    assert out["result"]["scope"]["dataset_revision"] == "rev-1"
    assert ev.picks[PICK] == ("top-brent", WB)
    assert ev.pages[DOC] == {4}
    assert ev.number_known("2310.5")


def test_formation_layers_state_level_planes_are_not_horizons(fakes: dict[str, Any]) -> None:
    out, ev = _run("get_formation_layers", {})
    res = out["result"]
    assert fakes["layers"] == (PID, None)
    assert res["surfaces"][0]["tier_label"] == LEVEL_PLANE_LABEL
    assert res["surfaces"][0]["illustrative"] is True
    assert "not interpreted horizons" in res["illustrative_notice"]
    assert "top-brent" in ev.surfaces and WB in ev.wellbores


def test_formation_tool_unknown_wellbore_is_an_error_not_data(fakes: dict[str, Any]) -> None:
    out, ev = _run("get_formation_picks", {"wellbore_id": str(OTHER_WB)})
    assert out["ok"] is False and "not found" in out["result"]["error"]
    assert not ev.surfaces and not ev.picks


def test_formation_results_are_bounded(
    fakes: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _layer_set(None)
    template = base.surfaces[0].picks[0]
    many = [template.model_copy(update={"pick_id": uuid4()}) for _ in range(120)]
    big = base.surfaces[0].model_copy(update={"picks": many})
    monkeypatch.setattr(
        tools_module.formation_service,
        "formation_layer_set",
        lambda *_a, **_k: base.model_copy(update={"surfaces": [big]}),
    )
    out, _ = _run("get_formation_picks", {})
    assert out["ok"] is True
    assert len(out["result"]["picks"]) == tools_module.MAX_PICKS
    assert out["result"]["truncated"] is True and out["result"]["total_picks"] == 120


# --- equipment ---------------------------------------------------------------------------------


def test_equipment_summary_labels_generic_and_catalog_and_is_not_installed(
    fakes: dict[str, Any],
) -> None:
    out, ev = _run("get_equipment_summary", {"wellbore_id": str(WB)})
    res = out["result"]
    assert fakes["spec"] == (PID, WB)
    assert res["visual_only"] is True and "does not establish" in res["caveat"]
    esp, packer = res["components"]
    assert esp["representation"] == "generic_illustrative"
    assert "generic placeholder" in esp["representation_note"] and esp["params"] is None
    assert packer["placement"]["state"] == "unlocated"
    assert "not evidence that it is installed" in packer["representation_note"]
    assert UUID(esp["element_id"]) == element_uuid(SPEC_ID, "esp-1")
    assert ev.element_wellbores[element_uuid(SPEC_ID, "esp-1")] == WB


def test_equipment_summary_missing_spec_and_extra_args(fakes: dict[str, Any]) -> None:
    out, _ = _run("get_equipment_summary", {"wellbore_id": str(WB2)})
    assert out["ok"] is False and "no equipment description" in out["result"]["error"]
    out, _ = _run("get_equipment_summary", {})
    assert out["ok"] is False


# --- AppLinks ----------------------------------------------------------------------------------


def test_formation_links_validate_against_tool_results(fakes: dict[str, Any]) -> None:
    _, ev = _run("get_formation_layers", {})
    answer = _validator(ev).validate(
        [
            _link_block({"kind": "formation", "surface_key": "top-brent"}),
            _link_block(
                {
                    "kind": "formation",
                    "surface_key": "top-brent",
                    "wellbore_id": str(WB),
                    "pick_id": str(PICK),
                }
            ),
            _link_block({"kind": "formation", "surface_key": "invented"}),
            _link_block({"kind": "formation", "surface_key": "top-brent", "pick_id": str(uuid4())}),
            _link_block({"kind": "formation", "surface_key": "top-brent", "wellbore_id": str(WB2)}),
            _link_block(
                {"kind": "formation", "surface_key": "top-brent", "wellbore_id": str(OTHER_WB)}
            ),
        ]
    )
    assert len(answer.blocks) == 2
    reasons = [d.reason for d in answer.dropped_blocks]
    assert reasons == [
        DroppedBlockReason.UNKNOWN_TARGET,
        DroppedBlockReason.UNKNOWN_TARGET,
        DroppedBlockReason.UNKNOWN_TARGET,
        DroppedBlockReason.OUT_OF_PROJECT,
    ]


def test_element_links_validate_and_reject_stale_or_cross_project(fakes: dict[str, Any]) -> None:
    _, ev = _run("get_equipment_summary", {"wellbore_id": str(WB)})
    good = str(element_uuid(SPEC_ID, "esp-1"))
    answer = _validator(ev).validate(
        [
            _link_block({"kind": "element", "element_id": good, "wellbore_id": str(WB)}),
            _link_block({"kind": "element", "element_id": good}),
            _link_block({"kind": "element", "element_id": str(uuid4())}),  # unknown/stale
            _link_block({"kind": "element", "element_id": good, "wellbore_id": str(WB2)}),
        ]
    )
    assert len(answer.blocks) == 2
    assert [d.reason for d in answer.dropped_blocks] == [DroppedBlockReason.UNKNOWN_TARGET] * 2


def test_links_fail_when_the_owning_wellbore_is_outside_the_project(fakes: dict[str, Any]) -> None:
    _, ev = _run("get_equipment_summary", {"wellbore_id": str(WB)})
    validator = AnswerValidator(
        project_id=PID,
        evidence=ev,
        scope=Scope(set()),  # the wellbore is not in this project
        series=None,
        context=ChatContext(),
        tool_calls_made=1,
    )
    answer = validator.validate(
        [
            _link_block({"kind": "element", "element_id": str(element_uuid(SPEC_ID, "esp-1"))}),
            {"kind": "text", "text": "ok"},
        ]
    )
    assert answer.dropped_blocks[0].reason is DroppedBlockReason.OUT_OF_PROJECT


# --- injection controls (AV-8) -----------------------------------------------------------------


def test_injection_in_equipment_text_cannot_add_tools_scope_or_links(fakes: dict[str, Any]) -> None:
    fakes["label"] = INJECTION
    out, ev = _run("get_equipment_summary", {"wellbore_id": str(WB)})
    assert out["context_class"] == "published" and out["ok"] is True
    assert set(TOOLS) >= {"get_equipment_summary"} and "delete_project" not in TOOLS
    injected_doc = "00000000-0000-4000-8000-0000000000d2"
    answer = _validator(ev).validate(
        [
            _link_block({"kind": "source", "document_id": injected_doc, "page": 1}),
            _link_block(
                {"kind": "wellbore", "wellbore_id": "00000000-0000-4000-8000-0000000000ff"}
            ),
            _link_block(
                {
                    "kind": "element",
                    "element_id": "00000000-0000-4000-8000-0000000000ff",
                    "wellbore_id": str(WB),
                }
            ),
            _link_block({"kind": "formation", "surface_key": "from-injected-text"}),
            {"kind": "text", "text": "ok"},
        ]
    )
    assert len(answer.blocks) == 1 and len(answer.dropped_blocks) == 4


def test_unknown_injected_tool_name_does_not_run(fakes: dict[str, Any]) -> None:
    out, _ = _run("get_formation_picks_sql", {"query": "drop table pick"})
    assert out["ok"] is False

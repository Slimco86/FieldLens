"""VisualAssetSpec contract + validator (TASK-077, AG-4/AG-5/AG-6): pure, no database."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from fieldlens.assetspec.validator import validate_spec
from fieldlens.contracts.asset_spec import FindingCode, Located, Unlocated

FIXTURES = Path(__file__).parent / "fixtures"
FRONTEND_COPY = Path(__file__).parents[3] / "frontend" / "tests" / "fixtures" / "asset-specs"
MANIFEST = json.loads((FIXTURES / "manifest.json").read_text())


def _load(name: str) -> dict[str, Any]:
    out: dict[str, Any] = json.loads((FIXTURES / name).read_text())
    return out


def _rich() -> dict[str, Any]:
    return _load("f14-dimensioned.json")


def _codes(raw: dict[str, Any], **kw: Any) -> list[FindingCode]:
    return [f.code for f in validate_spec(raw, **kw).findings]


@pytest.mark.parametrize("entry", MANIFEST["specs"], ids=lambda e: e["case"])
def test_fixtures_validate_cleanly(entry: dict[str, Any]) -> None:
    raw = _load(entry["file"])
    out = validate_spec(raw, md_range_m=tuple(entry["md_range_m"]))
    assert out.findings == []
    assert out.spec is not None
    assert len(out.spec.components) == len(raw["components"])
    assert out.spec.visual_only is True


def test_frontend_fixture_copies_are_identical() -> None:
    names = ["manifest.json", *(e["file"] for e in MANIFEST["specs"])]
    for name in names:
        assert (FRONTEND_COPY / name).read_text() == (FIXTURES / name).read_text(), name


def test_unlocated_stays_unlocated() -> None:
    out = validate_spec(_load("f12-unlocated.json"), md_range_m=(0, 3000))
    assert out.spec is not None
    kinds = [type(c.placement) for c in out.spec.components]
    assert kinds.count(Unlocated) == 4 and kinds.count(Located) == 1


def test_unknown_kind_is_dropped_not_guessed() -> None:
    raw = _rich()
    raw["components"][2]["kind"] = "rocket"
    out = validate_spec(raw, md_range_m=(0, 3400))
    assert [f.code for f in out.findings] == [FindingCode.UNKNOWN_KIND]
    assert out.spec is not None
    assert "csg-30" not in {c.id for c in out.spec.components}
    assert len(out.spec.components) == len(raw["components"]) - 1


def test_source_dimensioned_requires_evidence() -> None:
    raw = _rich()
    raw["components"][2]["evidence"] = []
    assert _codes(raw) == [FindingCode.MISSING_EVIDENCE]


def test_generic_is_never_dimensioned() -> None:
    raw = _load("f5-generic.json")
    raw["components"][0]["params"] = {"od": {"value": 5, "unit": "in"}}
    assert _codes(raw) == [FindingCode.GENERIC_DIMENSIONED]
    raw = _load("f5-generic.json")
    raw["components"][2]["representation"] = "source_dimensioned"
    assert _codes(raw) == [FindingCode.GENERIC_DIMENSIONED]


def test_md_range_is_enforced_only_when_given() -> None:
    raw = _rich()
    assert _codes(raw) == []
    out = _codes(raw, md_range_m=(0, 3000))
    assert out == [FindingCode.OUT_OF_MD_RANGE] * 2  # the 7 in liner and the perforations


def test_md_range_in_feet_is_converted() -> None:
    raw = _load("f5-generic.json")
    raw["components"][2]["placement"].update(md_top=3000, md_bottom=3100, unit="ft")
    assert _codes(raw, md_range_m=(0, 1000)) == []  # 3100 ft = 944.9 m
    assert _codes(raw, md_range_m=(0, 900)) == [FindingCode.OUT_OF_MD_RANGE]


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"od": {"value": 5, "unit": "in"}, "id": {"value": 6, "unit": "in"}}, "out_of_bounds"),
        ({"od": {"value": 500, "unit": "in"}}, "out_of_bounds"),
        ({"od": {"value": 0, "unit": "in"}}, "schema_invalid"),
        ({"od": {"value": 5, "unit": "cubits"}}, "schema_invalid"),
        ({"length": {"value": 99999, "unit": "m"}}, "out_of_bounds"),
        ({"weight": 3}, "schema_invalid"),
    ],
)
def test_param_bounds(params: dict[str, Any], code: str) -> None:
    raw = _rich()
    raw["components"][2]["params"] = params
    expected = {
        "out_of_bounds": FindingCode.PARAM_OUT_OF_BOUNDS,
        "schema_invalid": FindingCode.SCHEMA_INVALID,
    }[code]
    assert _codes(raw) == [expected]


def test_param_not_allowed_for_kind() -> None:
    raw = _rich()
    raw["components"][7]["params"]["id"] = {"value": 2, "unit": "in"}  # esp takes od/length only
    assert _codes(raw) == [FindingCode.PARAM_NOT_ALLOWED]


def test_duplicate_ids_and_non_finite_numbers() -> None:
    raw = _rich()
    dup = copy.deepcopy(raw["components"][2])
    raw["components"].append(dup)
    assert _codes(raw) == [FindingCode.DUPLICATE_ID]
    raw = _rich()
    raw["components"][2]["placement"]["md_bottom"] = float("nan")
    assert _codes(raw) == [FindingCode.SCHEMA_INVALID]


def test_urls_are_strings_with_http_scheme_only() -> None:
    raw = _rich()
    raw["components"][1]["visual_reference"]["url"] = "file:///etc/passwd"
    assert _codes(raw) == [FindingCode.SCHEMA_INVALID]
    raw = _rich()
    raw["components"][1]["visual_reference"] = {
        "image": {
            "storage_key": "k",
            "content_type": "image/svg+xml",
            "size_bytes": 10,
            "sha256": "a" * 64,
        }
    }
    assert _codes(raw) == [FindingCode.SCHEMA_INVALID]
    raw["components"][1]["visual_reference"]["image"].update(
        content_type="image/png", size_bytes=3 * 1024 * 1024
    )
    assert _codes(raw) == [FindingCode.SCHEMA_INVALID]
    raw["components"][1]["visual_reference"]["image"]["size_bytes"] = 1024
    assert _codes(raw) == []


def test_header_problems_make_the_document_unusable() -> None:
    raw = _rich()
    raw["visual_only"] = False
    out = validate_spec(raw)
    assert out.spec is None and out.findings[0].code == FindingCode.HEADER_INVALID
    assert validate_spec("not json").spec is None
    assert validate_spec("[]").spec is None
    big = validate_spec(json.dumps(_rich()), max_bytes=100)
    assert big.spec is None and big.findings[0].code == FindingCode.SPEC_TOO_LARGE


def test_too_many_components_are_capped_and_reported() -> None:
    raw = _load("f5-generic.json")
    raw["components"] = [
        {
            "id": f"b{i}",
            "kind": "generic_block",
            "label": "x",
            "placement": {"state": "unlocated"},
            "representation": "generic_illustrative",
        }
        for i in range(201)
    ]
    out = validate_spec(raw)
    assert out.spec is not None and len(out.spec.components) == 200
    assert out.findings[0].code == FindingCode.TOO_MANY_COMPONENTS


def test_incoming_findings_are_ignored() -> None:
    raw = _rich()
    raw["findings"] = [{"code": "unknown_kind", "message": "forged"}]
    out = validate_spec(raw)
    assert out.spec is not None and out.spec.findings == []


def test_surface_facilities_never_get_an_md() -> None:
    raw = _rich()
    sep = next(c for c in raw["components"] if c["id"] == "sep-1")
    sep["placement"] = {"state": "located", "md_top": 0, "md_bottom": 5, "unit": "m"}
    assert _codes(raw) == [FindingCode.PLACEMENT_NOT_ALLOWED]


def test_downhole_kind_cannot_sit_at_surface() -> None:
    raw = _rich()
    raw["components"][2]["placement"] = {"state": "surface"}  # casing
    assert _codes(raw) == [FindingCode.PLACEMENT_NOT_ALLOWED]
    raw = _rich()
    raw["components"][0]["placement"] = {"state": "surface"}  # wellhead may
    assert _codes(raw) == []


def test_surface_offset_is_bounded() -> None:
    raw = _rich()
    next(c for c in raw["components"] if c["id"] == "sep-1")["placement"]["offset_east_m"] = 5000
    assert _codes(raw) == [FindingCode.SCHEMA_INVALID]


@pytest.mark.parametrize("label", ["", "   ", "x" * 121])
def test_every_component_needs_a_visible_label(label: str) -> None:
    raw = _rich()
    raw["components"][2]["label"] = label
    out = _codes(raw)
    assert len(out) == 1 and out[0] in (FindingCode.LABEL_EMPTY, FindingCode.SCHEMA_INVALID)
    del raw["components"][3]["label"]
    assert FindingCode.SCHEMA_INVALID in _codes(raw)


def test_no_draft_or_accepted_status() -> None:
    raw = _rich()
    raw["status"] = "accepted"
    assert validate_spec(raw).spec is None


@pytest.mark.parametrize("label", ["\u200b\u200b", "\u200b \u00a0\u2028", "\ufeff", "\u202e"])
def test_invisible_only_label_is_rejected(label: str) -> None:
    raw = _rich()
    raw["components"][2]["label"] = label
    assert _codes(raw) == [FindingCode.LABEL_EMPTY]
    raw["components"][2]["label"] = "\u200bCasing"  # a visible character is enough
    assert _codes(raw) == []


@pytest.mark.parametrize(
    "path",
    ["label", "confidence_note", "evidence.quote", "visual_reference.url", "visual_reference.note"],
)
def test_control_characters_are_rejected_in_every_string(path: str) -> None:
    for bad in ("a\x00b", "a\x07b", "a\x1fb"):
        raw = _rich()
        comp = raw["components"][1]  # christmas tree: has evidence + visual_reference + note
        target: Any = comp
        *parents, leaf = path.split(".")
        for p in parents:
            target = target[p][0] if isinstance(target[p], list) else target[p]
        target[leaf] = bad if leaf != "url" else "https://example.org/" + bad
        out = validate_spec(raw)
        assert [f.code for f in out.findings] == [FindingCode.CONTROL_CHARACTER], (path, bad)
        assert out.spec is not None and len(out.spec.components) == len(raw["components"]) - 1


def test_control_character_in_header_or_newline_in_quote() -> None:
    raw = _rich()
    raw["generator"]["model"] = "m\x00"
    out = validate_spec(raw)
    assert out.spec is None and out.findings[0].code == FindingCode.HEADER_INVALID
    raw = _rich()
    raw["components"][0]["evidence"][0]["quote"] = "line one\nline two\ttab"
    assert _codes(raw) == []  # ordinary whitespace controls are fine


def test_deeply_nested_json_is_a_finding_not_a_crash() -> None:
    deep = "[" * 100_000 + "]" * 100_000
    out = validate_spec(deep)
    assert out.spec is None and out.findings[0].code == FindingCode.HEADER_INVALID
    obj = '{"components": ' + deep + "}"
    assert validate_spec(obj).spec is None
    nested: Any = {}
    cur = nested
    for _ in range(5000):
        cur["a"] = {}
        cur = cur["a"]
    assert validate_spec({**_rich(), "extra": nested}).spec is None
    assert validate_spec(b"\xff\xfe").spec is None

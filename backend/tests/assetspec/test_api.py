"""Asset spec persistence, stub designer and routes on real PostgreSQL (AG-4/AG-5/AG-6)."""

from __future__ import annotations

import copy
import json
from typing import Any
from uuid import UUID, uuid4

import pytest

from fieldlens.assetspec import service
from fieldlens.contracts.errors import ContractError
from fieldlens.persistence.session import session_scope
from tests.candidates.conftest import World
from tests.candidates.eq_helpers import equip, run_equip

F99 = "15/9-F-99"


def _seed(world: World) -> tuple[str, str]:
    doc = world.pdf_doc
    items = [
        equip(
            doc,
            1,
            category="casing",
            label_text="9-5/8 in casing",
            od={"value_text": "9.625", "unit": "in"},
            id={"value_text": "8.681", "unit": "in"},
            top_depth={"value_text": "0", "unit": "m", "reference_text": "MD"},
            bottom_depth={"value_text": "2800", "unit": "m", "reference_text": "MD"},
        ),
        equip(doc, 1, category="completion_accessory", label_text="Test separator"),
        equip(doc, 1, category="packer", label_text="Production packer"),  # top only, no OD
        equip(doc, 1, category="other", label_text="Mystery item"),
    ]
    out, _ = run_equip(world, items, doc=doc, subject=F99)
    assert out.state == "succeeded"
    wb = world.scalar(
        "select wellbore_id from extraction_candidate where attributes->>'kind'='equipment' limit 1"
    )
    return str(world.project_id), str(wb)


def _url(pid: str, wb: str, tail: str = "") -> str:
    return f"/api/v1/projects/{pid}/wellbores/{wb}/asset-spec{tail}"


def test_stub_designer_builds_a_labelled_visual_only_spec(world: World) -> None:
    pid, wb = _seed(world)
    api = world.api
    assert api.client.get(_url(pid, wb)).status_code == 404  # nothing generated yet
    r = api.client.post(_url(pid, wb, "/generate"), json={}, headers=api.headers)
    assert r.status_code == 201, r.text
    rec = r.json()
    assert rec["revision"] == 1 and rec["state"] == "current"
    spec = rec["spec"]
    assert spec["visual_only"] is True and spec["status"] == "current"
    assert spec["generator"]["provider"] == "stub"
    comps = {c["label"]: c for c in spec["components"]}
    assert all(c["label"].strip() for c in spec["components"])  # every element is labelled
    csg = comps["9-5/8 in casing"]
    assert csg["kind"] == "casing" and csg["representation"] == "source_dimensioned"
    assert csg["placement"]["state"] == "located" and csg["placement"]["md_bottom"] == 2800
    assert csg["params"]["od"]["unit"] == "m" and csg["evidence"][0]["candidate_id"]
    sep = comps["Test separator"]
    assert sep["kind"] == "separator" and sep["placement"] == {
        "state": "surface",
        "offset_east_m": None,
        "offset_north_m": None,
    }
    # nothing invented: no OD -> generic without numbers; unknown depth -> unlocated
    pkr = comps["Production packer"]
    assert pkr["representation"] == "generic_illustrative" and pkr.get("params") is None
    assert pkr["placement"]["state"] == "unlocated"
    assert comps["Mystery item"]["kind"] == "generic_block"
    got = api.client.get(_url(pid, wb))
    assert got.status_code == 200 and got.json()["spec_id"] == rec["spec_id"]
    assert got.headers["cache-control"] == "no-store"


def test_regeneration_keeps_history_with_one_current(world: World) -> None:
    pid, wb = _seed(world)
    api = world.api
    first = api.client.post(_url(pid, wb, "/generate"), json={}, headers=api.headers).json()
    second = api.client.post(_url(pid, wb, "/generate"), json={}, headers=api.headers).json()
    assert second["revision"] == 2 and second["spec_id"] != first["spec_id"]
    hist = api.client.get(_url(pid, wb, "/history")).json()["items"]
    assert [(h["revision"], h["state"]) for h in hist] == [(2, "current"), (1, "superseded")]
    assert api.client.get(_url(pid, wb)).json()["revision"] == 2
    assert world.scalar("select count(*) from wellbore_asset_spec where state='current'") == 1


def test_invalid_generation_leaves_the_current_spec_untouched(world: World) -> None:
    pid, wb = _seed(world)
    api = world.api
    first = api.client.post(_url(pid, wb, "/generate"), json={}, headers=api.headers).json()
    good: dict[str, Any] = first["spec"]
    bad_header = {**copy.deepcopy(good), "visual_only": False}
    empty = {**copy.deepcopy(good), "components": []}
    wrong_wb = {**copy.deepcopy(good), "wellbore_id": str(uuid4())}
    unknown_only = {**copy.deepcopy(good), "components": [{"id": "x", "kind": "rocket"}]}
    for raw in (bad_header, empty, wrong_wb, unknown_only):
        with pytest.raises(ContractError) as err:
            with session_scope(world.factory) as s:
                service.store_validated(s, UUID(pid), UUID(wb), raw, md_range_m=None)
        assert err.value.status_code == 422
    cur = api.client.get(_url(pid, wb)).json()
    assert cur["spec_id"] == first["spec_id"] and cur["state"] == "current"
    assert len(api.client.get(_url(pid, wb, "/history")).json()["items"]) == 1


def test_out_of_range_md_components_are_dropped_with_findings(world: World) -> None:
    pid, wb = _seed(world)
    api = world.api
    r = api.client.post(
        _url(pid, wb, "/generate"), json={"md_min": 0, "md_max": 1000}, headers=api.headers
    )
    assert r.status_code == 201
    spec = r.json()["spec"]
    assert "9-5/8 in casing" not in {c["label"] for c in spec["components"]}
    assert [f["code"] for f in spec["findings"]] == ["out_of_md_range"]


def test_scoping_and_guards(world: World) -> None:
    pid, wb = _seed(world)
    api = world.api
    assert api.client.get(_url(str(uuid4()), wb)).status_code == 404
    assert api.client.get(_url(pid, str(uuid4()))).status_code == 404
    assert (
        api.client.post(
            _url(pid, str(uuid4()), "/generate"), json={}, headers=api.headers
        ).status_code
        == 404
    )
    # the mutation guard applies (no session token header)
    assert api.client.post(_url(pid, wb, "/generate"), json={}).status_code == 403
    # no accept endpoint exists
    assert api.client.post(_url(pid, wb, "/accept"), headers=api.headers).status_code in (404, 405)


def test_invalidate_hook_keeps_history(world: World) -> None:
    pid, wb = _seed(world)
    api = world.api
    api.client.post(_url(pid, wb, "/generate"), json={}, headers=api.headers)
    with session_scope(world.factory) as s:
        assert service.invalidate_current(s, UUID(pid), UUID(wb)) is True
    assert api.client.get(_url(pid, wb)).status_code == 404
    hist = api.client.get(_url(pid, wb, "/history")).json()["items"]
    assert [h["state"] for h in hist] == ["invalidated"]
    # a new generation after the invalidation becomes revision 2 and current
    r = api.client.post(_url(pid, wb, "/generate"), json={}, headers=api.headers)
    assert r.json()["revision"] == 2


def test_database_refuses_non_visual_or_second_current(world: World) -> None:
    pid, wb = _seed(world)
    api = world.api
    api.client.post(_url(pid, wb, "/generate"), json={}, headers=api.headers)
    from sqlalchemy.exc import IntegrityError

    base = (
        "insert into wellbore_asset_spec (project_id, wellbore_id, revision, state, "
        "source_revision, generator_provider, generator_model, spec) "
        "values (:p, :w, :r, 'current', 's', 'x', 'y', cast(:spec as jsonb))"
    )
    from sqlalchemy import text

    for rev, spec in ((9, {"visual_only": True}), (10, {"visual_only": False})):
        with pytest.raises(IntegrityError):
            with session_scope(world.factory) as s:
                s.execute(text(base), {"p": pid, "w": wb, "r": rev, "spec": json.dumps(spec)})

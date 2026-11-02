"""Opt-in real-record check of the TASK-056 start gate over the Statoil survey exports.

    FIELDLENS_LOCAL_DATA_ROOT=... uv run pytest backend/tests/identity/test_local_data_exposure.py -m local_data -s

Read-only and in place: the files are read into memory and uploaded to the isolated test database
through the real upload, extraction and identity path; nothing is copied or transmitted."""

from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

import pytest

from fieldlens.identity.resolver import resolve_project
from fieldlens.merge_proposals.blocking import build_dataset
from fieldlens.persistence.session import session_scope
from tests.retrieval.support import World

pytestmark = pytest.mark.local_data

_ROOT_ENV = os.environ.get("FIELDLENS_LOCAL_DATA_ROOT")
if not _ROOT_ENV or not Path(_ROOT_ENV).is_dir():
    pytest.skip("FIELDLENS_LOCAL_DATA_ROOT is not set to a directory", allow_module_level=True)
ROOT = Path(_ROOT_ENV)

SURVEY = "Well_technical_data/WellWellbore/15_9-{w}/15_9-{w}/Volve F_{w}_{w}_{w}_ACTUAL"

QUALIFYING = "Geophysical_Interpretations/Wells/Well_perforations_Volve.dat"


def _settle(world: World, pid: str) -> None:
    while world.api.worker.run_once():
        pass
    while world.api.worker.extraction.run_once():
        pass
    with session_scope(world.factory) as session:
        resolve_project(session, UUID(pid))


def test_real_statoil_actual_exports_gate(world: World) -> None:
    pid = world.project()
    files = []
    for w in ("F-12", "F-5"):
        path = ROOT / SURVEY.format(w=w)
        if not path.is_file():
            pytest.skip(f"{path.name} is not in the local data subset")
        files.append((path.name, path.read_bytes()))
    r = world.api.upload(pid, files, parent=world.api.latest(pid))
    assert r.status_code in (200, 201, 202), r.text
    _settle(world, pid)
    # D9 (TASK-061): the exports name the well only as "F-12"/"F-5" (no block). Each is a
    # block-less wellbore named as written; the gate opens with warnings, nothing invented.
    alone = world.api.client.get(f"/api/v1/projects/{pid}/identity/start-gate").json()
    assert alone["can_start"] is True and alone["unmet"] == []
    per = {w["wellbore_name"]: w for w in alone["wellbores"]}
    assert sorted(per) == ["F-12", "F-5"]
    for w in per.values():
        codes = {x["code"] for x in w["warnings"]}
        assert w["trajectory_validated"] is True, w["unmet"]
        assert {"BLOCK_NOT_STATED", "SURVEY_STATUS_UNSTATED"} <= codes
        if w["location_state"] == "located":
            assert "SURFACE_LOCATION_MISSING" not in codes
        else:
            assert w["unlocated"] is True and codes & {
                "SURFACE_LOCATION_MISSING",
                "SURFACE_LOCATION_INCOMPLETE",
            }
    print({n: (w["trajectory_validated"], w["location_state"]) for n, w in per.items()})
    qualified = ROOT / QUALIFYING
    if not qualified.is_file():
        pytest.skip("the perforation table is not in the local data subset")
    r = world.api.upload(
        pid, [(qualified.name, qualified.read_bytes())], parent=world.api.latest(pid)
    )
    assert r.status_code in (200, 201, 202), r.text
    _settle(world, pid)
    g = world.api.client.get(f"/api/v1/projects/{pid}/identity/start-gate").json()
    names = {w["wellbore_name"]: w for w in g["wellbores"]}
    assert g["can_start"] is True and g["unmet"] == []
    # separate wellbores: the block-less ones keep their trajectories, nothing merged silently
    assert {"F-12", "F-5", "15/9-F-12", "15/9-F-5"} <= set(names)
    for name in ("F-12", "F-5"):
        assert names[name]["trajectory_validated"] is True
    with session_scope(world.factory) as session:
        ds = build_dataset(session, UUID(pid))
    pairs = {(b.target.key, c.party.key) for b in ds.blocks for c in b.members}
    assert ("15/9-F-12", "F-12") in pairs and ("15/9-F-5", "F-5") in pairs
    assert ("15/9-F-12", "F-5") not in pairs and ("15/9-F-5", "F-12") not in pairs
    assert world.sql("SELECT count(*) FROM identity_merge")[0][0] == 0

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
    # The exports name the well only as "F-12"/"F-5" (no block): identity needs a block-qualified
    # source in the project (resolver rule), so alone they stay unresolved and the gate says so.
    alone = world.api.client.get(f"/api/v1/projects/{pid}/identity/start-gate").json()
    assert alone["can_start"] is False
    assert [u["code"] for u in alone["unmet"]] == ["NO_WELLBORE_IDENTIFIED"]
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
    print({n: (w["trajectory_validated"], w["location_state"]) for n, w in names.items()})
    print([x["code"] for x in g["warnings"]])
    assert g["can_start"] is True and g["unmet"] == []
    for name in ("15/9-F-12", "15/9-F-5"):
        w = names[name]
        assert w["trajectory_validated"] is True, w["unmet"]
        assert w["trajectory_sets"][0]["survey_status"] == "unstated"
        codes = {x["code"] for x in w["warnings"]}
        assert "SURVEY_STATUS_UNSTATED" in codes
        assert w["unlocated"] is False and w["location_state"] == "located", w["warnings"]
        assert "SURFACE_LOCATION_MISSING" not in codes

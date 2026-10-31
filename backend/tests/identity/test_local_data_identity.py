"""Opt-in: identity resolution and depth defaults over the approved local Volve subset.

    FIELDLENS_LOCAL_DATA_ROOT=... uv run pytest backend/tests/identity/test_local_data_identity.py -m local_data -s

Read-only, in place, nothing transmitted. Reports resolved wells/wellbores, depth-default counts,
warnings and unresolved/ambiguous labels; says nothing about engineering correctness."""

from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

from fieldlens.extraction.runner import _time
from fieldlens.identity.resolver import resolve_project
from fieldlens.ingestion.inspect import inspect_file
from fieldlens.persistence.session import session_scope
from fieldlens.profiles import registry
from fieldlens.profiles.types import ParseContext, ProfileOutput
from tests.retrieval.support import World

pytestmark = pytest.mark.local_data

_ROOT_ENV = os.environ.get("FIELDLENS_LOCAL_DATA_ROOT")
if not _ROOT_ENV or not Path(_ROOT_ENV).is_dir():
    pytest.skip("FIELDLENS_LOCAL_DATA_ROOT is not set to a directory", allow_module_level=True)
ROOT = Path(_ROOT_ENV)

WITSML = "WITSML Realtime drilling data/Norway-Statoil-NO 15_$47$_9-{w}/1/{obj}/1.xml"
SURVEY = "Well_technical_data/WellWellbore/15_9-{w}/15_9-{w}/Standard Survey Report_Volve F_{w}_{w}_{w}_ACTUAL.pdf"
LAS = "Well_logs_pr_WELL/15_9-{w}/02.LWD_EWL/WL_RAW_BHPR-GR-MECH_MWD_1.LAS"
WELLS = ("F-12", "F-14", "F-5")
SHARED = [
    "Geophysical_Interpretations/Wells/Well_perforations_Volve.dat",
    "Geophysical_Interpretations/Wells/Well_picks_Volve_v1.dat",
    "Production_data/Volve production data.xlsx",
]


def _paths() -> list[str]:
    out = list(SHARED)
    for w in WELLS:
        out += [WITSML.format(w=w, obj=o) for o in ("tubular", "bhaRun", "wbGeometry")]
        out += [SURVEY.format(w=w), LAS.format(w=w)]
    return out


def _parse(rel: str) -> tuple[ProfileOutput, str]:
    path = ROOT / rel
    family = inspect_file(
        path, path.name, max_file_bytes=2 * 1024**3, remaining_batch_bytes=2 * 1024**3
    ).format_family
    profile = registry.detect(path, family, path.name)[0]
    return profile.parse(path, ParseContext(uuid4(), uuid4(), "0" * 64, path.name)), profile.name


def test_real_subset_identity_and_depth_defaults(world: World) -> None:
    pid = world.project()
    defaulted = Counter[str]()
    warnings: dict[str, int] = {}
    for rel in _paths():
        out, profile_name = _parse(rel)
        n_default = sum(
            1
            for r in out.records
            for a in r.attrs
            if a.unit is None
            and a.normalized_unit == "m"
            and a.reference
            and "(default)" in a.reference
        )
        if n_default:
            defaulted[Path(rel).name] = n_default
        warnings[Path(rel).name] = sum(1 for f in out.findings if f.code == "MISSING_UNIT")
        records = [
            {
                "kind": r.kind,
                "subject": r.subject,
                "locator": r.locator,
                "effective_time": _time(r.effective_time),
                "validation_state": r.validation_state,
                "attributes": [a.to_json() for a in r.attrs],
            }
            for r in out.records
        ]
        doc = world.add_doc(pid, Path(rel).name, records)
        world.sql(
            "UPDATE extraction_run SET profile_name = :p WHERE run_id = :r",
            p=profile_name,
            r=doc.run_id,
        )
    with session_scope(world.factory) as session:
        outcome = resolve_project(session, UUID(pid))
    listing = world.api.client.get(f"/api/v1/projects/{pid}/identity").json()
    print(f"outcome: {outcome}")
    print(f"depth-default attributes by file: {dict(defaulted)}")
    print(f"MISSING_UNIT findings per file: { {k: v for k, v in warnings.items() if v} }")
    for well in listing["wells"]:
        print(f"WELL {well['name']}: {well['record_count']} records, {well['document_count']} docs")
        for b in well["wellbores"]:
            kinds = ", ".join(f"{c['kind']}={c['records']}" for c in b["record_counts"])
            print(
                f"    {b['name']:20} parent={'yes' if b['parent_wellbore_id'] else '-':3} {kinds}"
            )
    print(f"unresolved: {listing['unresolved_record_count']} {listing['unresolved']}")
    for row in world.sql(
        "SELECT code, severity, message FROM extraction_issue "
        "WHERE producer_key LIKE 'identity_resolution:%' ORDER BY code, message"
    ):
        print(f"{row.code} {row.severity}: {row.message[:300]}")
    names = {w["name"] for w in listing["wells"]}
    assert {"15/9-F-12", "15/9-F-14", "15/9-F-5"} <= names
    bores: dict[str, Any] = {b["name"]: b for w in listing["wells"] for b in w["wellbores"]}
    assert "15/9-F-12" in bores and "15/9-F-12 PILOT" in bores
    # production H/AH bores are aliased to the observed base wellbore (owner rule)
    assert "15/9-F-12 H" not in bores and "15/9-F-5 AH" not in bores
    assert any(k["kind"] == "production_day" for k in bores["15/9-F-12"]["record_counts"])
    assert not any("volve" in n.lower() for n in names | set(bores))
    assert listing["resolved_current"] is True

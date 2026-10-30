"""Opt-in local-data run of every profile against the approved Volve subset.

Skipped unless ``FIELDLENS_LOCAL_DATA_ROOT`` points at the read-only data root (for example
``/mnt/c/Users/<user>/Downloads/Hackathon_Data``). Nothing is copied; files are read in place.
Run:  FIELDLENS_LOCAL_DATA_ROOT=... uv run pytest backend/tests -m local_data -s
The per-wellbore coverage matrix is printed; gaps are reported, never filled."""

from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

import pytest

from fieldlens.ingestion.inspect import inspect_file
from fieldlens.profiles import registry
from tests.profile_support import CTX

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
    "Production_data/Volve production data.xlsx",
    "Geophysical_Interpretations/Wells/Well_perforations_Volve.dat",
    "Geophysical_Interpretations/Wells/Well_picks_Volve_v1.dat",
]
CATEGORY = {
    "trajectory_station": "trajectory",
    "production_day": "production",
    "perforation_interval": "completion",
    "tubular_component": "equipment",
    "casing_point": "equipment",
}


def _files() -> list[tuple[str | None, str]]:
    out: list[tuple[str | None, str]] = [(None, p) for p in SHARED]
    for w in WELLS:
        out += [(w, WITSML.format(w=w, obj=o)) for o in ("tubular", "bhaRun", "wbGeometry")]
        out += [(w, SURVEY.format(w=w)), (w, LAS.format(w=w))]
    return out


def _wellbore_of(text: str) -> str | None:
    m = re.search(r"F-(12|14|5)\b", text)
    return f"F-{m.group(1)}" if m else None


def test_profiles_cover_at_least_two_wellbores_and_report_gaps() -> None:
    matrix: dict[str, dict[str, int]] = {w: defaultdict(int) for w in WELLS}
    results: list[str] = []
    for well, rel in _files():
        path = ROOT / rel
        assert path.is_file(), f"approved-subset file missing: {rel}"
        family = inspect_file(
            path, path.name, max_file_bytes=2 * 1024**3, remaining_batch_bytes=2 * 1024**3
        ).format_family
        profiles = registry.detect(path, family, path.name)
        assert len(profiles) == 1, f"{rel}: profiles {[p.name for p in profiles]}"
        out = profiles[0].parse(path, CTX)
        results.append(f"{out.status:9} {profiles[0].name:28} {len(out.records):6} {rel}")
        assert out.status in ("succeeded", "partial")
        for rec in out.records:
            cat = CATEGORY.get(rec.kind)
            if cat is None:
                continue
            owner = well or _wellbore_of(" ".join(str(v) for v in rec.subject.values()))
            if owner in matrix:
                matrix[owner][cat] += 1
    print("\n".join(results))
    print("wellbore  trajectory production completion equipment")
    for w in WELLS:
        row = matrix[w]
        print(
            f"{w:8} {row['trajectory']:10} {row['production']:10} "
            f"{row['completion']:10} {row['equipment']:9}"
        )
    complete = [w for w in WELLS if all(matrix[w][c] > 0 for c in set(CATEGORY.values()))]
    assert len(complete) >= 2, f"fewer than two wellbores covered: {dict(matrix)}"

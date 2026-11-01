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
from sqlalchemy.engine import URL

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
    print(
        "columns: trajectory stations | production days | perforation intervals "
        "(depths default to m, warned) | drilling-assembly/casing-point records"
    )
    print("wellbore  trajectory production completion equipment")
    for w in WELLS:
        row = matrix[w]
        print(
            f"{w:8} {row['trajectory']:10} {row['production']:10} "
            f"{row['completion']:10} {row['equipment']:9}"
        )
    for w in WELLS:
        print(
            f"{w}: completion string/packers/tubing not extracted (deferred completion PDFs); "
            "equipment = drilling-assembly/casing-point records only"
        )
    complete = [w for w in WELLS if all(matrix[w][c] > 0 for c in set(CATEGORY.values()))]
    assert len(complete) >= 2, f"fewer than two wellbores covered: {dict(matrix)}"


def test_report_builder_answers_200_for_every_real_file(migrated_url: URL, tmp_path: Path) -> None:
    """Catches report-construction bugs (e.g. duplicate blocked operations) on real data."""
    from tests.jobs.test_extraction_flow import _drain, _ingest, _report
    from tests.upload_support import make_api

    api = make_api(migrated_url, tmp_path)
    files = [(Path(rel).name, (ROOT / rel).read_bytes()) for _, rel in _files()]
    names: dict[str, int] = {}
    pid, docs = _ingest(api, [(f"{i}_{n}", b) for i, (n, b) in enumerate(files)])
    assert len(docs) == len(files)
    _drain(api)
    for doc in docs:
        rep = _report(api, pid, str(doc["document_id"]))
        assert rep["status"] in ("succeeded", "partial"), (doc["original_filename"], rep["status"])
        assert rep["coverage_notes"] is not None
        names[doc["original_filename"]] = len(rep["issues"])
    print(f"report builder OK for {len(names)} real files; findings per file: {names}")


STATOIL = "Well_technical_data/WellWellbore/15_9-{w}/15_9-{w}/Volve F_{w}_{w}_{name}"
STATOIL_FILES = (
    ("F-12", "F-12_ACTUAL", 211, 3520.0, 3108.36),
    ("F-12", "F12 Rev011 CC 240707_PLAN", 119, 3441.29, 3073.84),
    ("F-5", "F-5_ACTUAL", 97, 3792.0, 3246.43),
    ("F-5", "F5 Rev 143 131207_PLAN", 137, 3868.3, 3293.29),
)


@pytest.mark.parametrize(("well", "name", "count", "last_md", "last_tvd"), STATOIL_FILES)
def test_statoil_survey_export_text_files_parse_with_surface_location(
    well: str, name: str, count: int, last_md: float, last_tvd: float
) -> None:
    """The extensionless Statoil-default survey exports (IN-11): stations + surface location."""
    path = ROOT / STATOIL.format(w=well, name=name)
    assert path.is_file(), f"approved-subset file missing: {path}"
    det = inspect_file(path, path.name, max_file_bytes=2**30, remaining_batch_bytes=2**30)
    assert (det.format_family, det.extraction_state, det.encoding) == (
        "text",
        "pending_extraction",
        "cp1252",
    )
    profiles = registry.detect(path, det.format_family, path.name)
    assert [p.name for p in profiles] == ["text_statoil_survey_export"]
    out = profiles[0].parse(path, CTX)
    stations = [r for r in out.records if r.kind == "trajectory_station"]
    assert out.status == "succeeded" and len(stations) == count
    assert not [f for f in out.findings if f.severity == "error"]
    mdn, tvdn = (stations[-1].attr(f"trajectory_station.{k}") for k in ("md", "tvd"))
    assert mdn and tvdn and (mdn.number, tvdn.number) == (last_md, last_tvd)
    loc = next(r for r in out.records if r.kind == "well_surface_location")
    e, n = (loc.attr(f"well_surface_location.{k}") for k in ("easting", "northing"))
    assert e and n and e.number is not None and n.number is not None and e.unit == n.unit == "m"
    lat = loc.attr("well_surface_location.latitude")
    assert lat and "°" in (lat.original_text or "") and lat.normalized_number is not None
    if well == "F-12":
        md0 = stations[0].attr("trajectory_station.md")
        assert md0 and md0.number == 145.9
        assert (e.number, n.number) == (435050.21, 6478566.22)
    print(f"{well} {name}: {count} stations; findings:")
    for f in out.findings:
        print(f"  {f.severity:7} {f.code} {f.key}: {f.message[:100]}")


def test_statoil_survey_export_real_upload_reaches_the_profile(
    migrated_url: URL, tmp_path: Path
) -> None:
    """Real F-12 ACTUAL through the real upload/inspect/extract path (test database only)."""
    from tests.jobs.test_extraction_flow import _drain, _ingest, _report
    from tests.upload_support import make_api

    path = ROOT / STATOIL.format(w="F-12", name="F-12_ACTUAL")
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [(path.name, path.read_bytes())])
    doc = docs[0]
    assert doc["format_family"] == "text" and doc["origin_metadata"]["text_encoding"] == "cp1252"
    assert doc["extraction_state"] == "pending_extraction"
    did = str(doc["document_id"])
    _drain(api)
    rep = _report(api, pid, did)
    assert rep["profile_name"] == "text_statoil_survey_export" and rep["status"] == "succeeded"
    base = f"/api/v1/projects/{pid}/documents/{did}/extraction/records"
    counts = {
        kind: api.client.get(f"{base}?kind={kind}").json()["total"]
        for kind in (
            "survey_report_header",
            "well_surface_location",
            "survey_program_entry",
            "trajectory_station",
        )
    }
    print(f"real upload record counts: {counts}; issues: {len(rep['issues'])}")
    assert counts == {
        "survey_report_header": 1,
        "well_surface_location": 1,
        "survey_program_entry": 4,
        "trajectory_station": 211,
    }

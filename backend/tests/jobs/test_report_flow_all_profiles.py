"""Regression for the QA D1/D2/D5 defects: upload -> extract -> GET report for every profile
through the real API must answer 200 with findings listed (small synthetic real-shaped fixtures),
wellbore identity must stay distinct, and requeue must be idempotent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

from tests.jobs.test_extraction_flow import _drain, _ingest, _report
from tests.profile_support import station, text_pdf, witsml, xlsx_bytes
from tests.test_profiles_sources import (
    DAILY_HEAD,
    LAS,
    MONTHLY_HEAD,
    MONTHLY_UNITS,
    PERF_HEAD,
    PICKS,
    SURVEY_PAGE,
    _day,
    _perf_row,
)
from tests.upload_support import Api, make_api


def _files() -> list[tuple[str, bytes]]:
    perf = (
        PERF_HEAD
        + _perf_row(1, 1, "4160.00", "4165.00", "2772.90", "2776.64", "2010-05-03")
        + _perf_row(2, 2, "4157.00", "4159.00", "2770.66", "2772.15", "")
    )
    book = xlsx_bytes(
        {
            "Daily Production Data": [DAILY_HEAD, _day(40000, "15/9-F-99", 1, 10.5)],
            "Monthly Production Data": [MONTHLY_HEAD, MONTHLY_UNITS],
        }
    )
    traj = witsml(
        "trajectorys",
        "trajectory",
        station("S-0", "0", "0", "0", "0") + station("S-1", "100", "99.9", "5", "120"),
    )
    tub = witsml(
        "tubulars",
        "tubular",
        "<typeTubularAssy>drilling</typeTubularAssy>"
        '<tubularComponent uid="C1"><typeTubularComp>tubing</typeTubularComp>'
        '<id uom="m">0.1</id><od uom="m">0.17</od><len uom="m">2054</len>'
        '<tensYield uom="Pa">0</tensYield></tubularComponent>',
    )
    return [
        ("perf.dat", perf.encode()),
        ("prod.xlsx", book),
        ("picks.dat", PICKS.encode()),
        ("log.las", LAS.encode()),
        ("traj.xml", traj.encode()),
        ("tub.xml", tub.encode()),
        ("survey.pdf", text_pdf([SURVEY_PAGE])),
    ]


def test_every_profile_report_is_http_200_with_findings(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, _files())
    assert len(docs) == 7
    _drain(api)
    seen: dict[str, int] = {}
    for doc in docs:
        rep = _report(api, pid, str(doc["document_id"]))
        assert rep["status"] in ("succeeded", "partial"), (doc["original_filename"], rep["status"])
        assert rep["issues"], f"{doc['original_filename']} should list findings"
        for issue in rep["issues"]:
            ops = issue["blocked_operations"]
            assert len(ops) == len(set(ops))
        seen[rep["profile_name"]] = len(rep["issues"])
    assert len(seen) == 7, seen


def test_malformed_stored_issue_never_500s_the_report(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("log.las", LAS.encode())])
    did = str(docs[0]["document_id"])
    _drain(api)
    with engine.begin() as conn:
        conn.execute(
            text(
                "update extraction_issue set blocked_operations = "
                "array['placement','placement','bogus']"
            )
        )
    rep = _report(api, pid, did)
    assert rep["issues"]
    for issue in rep["issues"]:
        assert issue["blocked_operations"] in ([], ["placement"])


def test_report_labels_equipment_and_completion_gaps_and_keeps_identity(
    migrated_url: URL, tmp_path: Path
) -> None:
    api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, _files())
    _drain(api)
    by_name = {d["original_filename"]: str(d["document_id"]) for d in docs}
    rep = _report(api, pid, by_name["perf.dat"])
    notes = " ".join(rep["coverage_notes"])
    assert "completion string" in notes and "deferred" in notes
    assert "perforation" in notes
    rep = _report(api, pid, by_name["tub.xml"])
    assert "drilling-assembly" in " ".join(rep["coverage_notes"])
    ids = rep["wellbore_identities"]
    assert ids and all(i["wellbore_label"] and "well_key" in i for i in ids)


def test_identity_mismatch_finding_across_sources(migrated_url: URL, tmp_path: Path) -> None:
    api = make_api(migrated_url, tmp_path)
    a = witsml("trajectorys", "trajectory", station("S-0", "0", "0", "0", "0"))
    b = a.replace("<nameWellbore>15/9-F-99</nameWellbore>", "<nameWellbore>F-99 A</nameWellbore>")
    assert a != b
    pid, docs = _ingest(api, [("a.xml", a.encode()), ("b.xml", b.encode())])
    _drain(api)
    _drain(api)
    all_codes: set[str] = set()
    labels: set[str] = set()
    for doc in docs:
        rep = _report(api, pid, str(doc["document_id"]))
        all_codes |= {i["code"] for i in rep["issues"]}
        labels |= {i["wellbore_label"] for i in rep["wellbore_identities"]}
    assert labels >= {"15/9-F-99", "F-99 A"}
    assert "IDENTITY_MISMATCH" in all_codes


def _runs(engine: Engine) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text("select count(*) from extraction_run")).scalar_one())


def test_requeue_of_unsupported_run_is_idempotent_until_explicit_retry(
    migrated_url: URL, tmp_path: Path, engine: Engine
) -> None:
    api: Api = make_api(migrated_url, tmp_path)
    pid, docs = _ingest(api, [("notes.csv", b"a,b\n1,2\n")])
    did = str(docs[0]["document_id"])
    _drain(api)
    assert _report(api, pid, did)["status"] == "unsupported"
    before = _runs(engine)
    url = f"/api/v1/projects/{pid}/documents/{did}/extraction"
    for _ in range(3):
        r = api.client.post(url, headers=api.headers)
        assert r.status_code in (200, 202), r.text
    assert _runs(engine) == before
    r: Any = api.client.post(url + "?retry=true", headers=api.headers)
    assert r.status_code in (200, 202), r.text
    assert _runs(engine) == before + 1

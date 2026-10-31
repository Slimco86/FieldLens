"""TASK-046 DC-3..DC-6 against PostgreSQL: deterministic identity rows, links, findings, API.
Records are inserted directly (synthetic, invented values) with the real subject shapes."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fieldlens.identity.resolver import resolve_project
from fieldlens.persistence.session import session_scope
from tests.retrieval.support import World, attr, rec


def _subj(
    well: str | None,
    label: str | None,
    key: str | None,
    suffix: str | None = None,
    bore: str | None = None,
) -> dict[str, Any]:
    return {
        "well_name": well,
        "wellbore_name": bore,
        "wellbore_label": label,
        "well_key": key,
        "wellbore_suffix": suffix,
    }


def _perf(
    label: str, key: str | None, suffix: str | None, top: float, base: float
) -> dict[str, Any]:
    def depth(k: str, v: float) -> dict[str, Any]:
        a = attr(f"perforation.{k}", f"{v:.2f}", number=v)
        a["normalized_number"], a["normalized_unit"] = v, "m"
        a["reference"] = "assumed MD (default)"
        return a

    return rec(
        "perforation_interval",
        _subj(label, label, key, suffix),
        [depth("top_md", top), depth("base_md", base)],
    )


def _station(label: str, key: str, md: float) -> dict[str, Any]:
    a = attr("trajectory_station.md", str(md), "m", number=md)
    a["normalized_number"], a["normalized_unit"] = md, "m"
    return rec("trajectory_station", _subj("Volve F", label, key), [a])


def _resolve(world: World, pid: str) -> Any:
    with session_scope(world.factory) as session:
        return resolve_project(session, UUID(pid))


def _listing(world: World, pid: str) -> dict[str, Any]:
    r = world.api.client.get(f"/api/v1/projects/{pid}/identity")
    assert r.status_code == 200, r.text
    return dict(r.json())


def _bores(listing: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {b["name"]: b for w in listing["wells"] for b in w["wellbores"]}


def _volve_docs(world: World, pid: str) -> None:
    world.add_doc(
        pid,
        "perf.dat",
        [
            _perf("NO 15/9-F-12", "15/9-F-12", None, 4160, 4165),
            _perf("NO 15/9-F-11 B", "15/9-F-11", "B", 3000, 3010),
            _perf("NO 15/9-F-1 B", "15/9-F-1", "B", 2000, 2010),
        ],
    )
    picks = [
        rec("formation_pick", _subj(n, n, k, s), [attr("pick.surface_name", "Hugin Fm. Top")])
        for n, k, s in (
            ("NO 15/9-F-11", "15/9-F-11", None),
            ("NO 15/9-F-11 A", "15/9-F-11", "A"),
            ("NO 15/9-F-11 T2", "15/9-F-11", "T2"),
            ("NO 15/9-F-1", "15/9-F-1", None),
            ("NO 15/9-F-12 pilot", "15/9-F-12", "pilot"),
            ("NO 15/9-19 SR", None, None),
            ("NO 15/9-19 BT2", None, None),
        )
    ]
    world.add_doc(pid, "picks.dat", picks)
    world.add_doc(
        pid,
        "survey.pdf",
        [_station("F-12", "15/9-F-12", 100.0), _station("F-12", "15/9-F-12", 3000.0)],
    )
    world.add_doc(
        pid,
        "log.las",
        [rec("las_header", _subj("15/9-F5", None, "15/9-F-5"), [attr("las_header.stop", "2000")])],
    )
    prod = world.add_doc(
        pid,
        "prod.xlsx",
        [
            rec(
                "production_day",
                _subj("15/9-F-12", "NO 15/9-F-12 H", "15/9-F-12", None, "NO 15/9-F-12 H"),
                [attr("production_day.bore_oil_vol", "1", number=1.0)],
            )
        ],
    )
    world.sql(
        "UPDATE extraction_run SET profile_name = 'production_workbook_volve' WHERE run_id = :r",
        r=prod.run_id,
    )
    world.add_doc(
        pid, "field.txt", [rec("note", _subj("Volve F", None, None), [attr("note.text", "x")])]
    )


def test_identity_resolution(world: World) -> None:
    pid = world.project()
    _volve_docs(world, pid)
    out = _resolve(world, pid)
    assert out.wells == 5 and out.wellbores == 11
    listing = _listing(world, pid)
    assert [w["name"] for w in listing["wells"]] == [
        "15/9-19",
        "15/9-F-1",
        "15/9-F-11",
        "15/9-F-12",
        "15/9-F-5",
    ]
    bores = _bores(listing)
    # distinct wellbores, never merged
    assert {"15/9-F-12", "15/9-F-12 PILOT", "15/9-F-11", "15/9-F-11 A"} <= set(bores)
    assert {"15/9-F-1", "15/9-F-1 B", "15/9-19 SR", "15/9-19 BT2", "15/9-F-5"} <= set(bores)
    assert not any(b == "Volve F" or b.startswith("volve") for b in bores)
    # parent links only to an OBSERVED base wellbore, by name suffix
    f11, f11b = bores["15/9-F-11"], bores["15/9-F-11 B"]
    assert (
        f11b["parent_wellbore_id"] == f11["wellbore_id"] and f11b["parent_basis"] == "name_suffix"
    )
    assert f11["parent_wellbore_id"] is None and f11["suffix"] is None
    assert bores["15/9-19 SR"]["parent_wellbore_id"] is None, "no base 15/9-19 bore was observed"
    assert "15/9-F-12 H" not in bores, "production H bore is aliased to the observed base bore"
    assert bores["15/9-F-12 PILOT"]["parent_wellbore_id"] == bores["15/9-F-12"]["wellbore_id"]
    # F-12 (survey 'F-12' + perforation + key) is one wellbore; the field-level doc is unresolved
    f12 = bores["15/9-F-12"]
    assert {c["kind"]: c["records"] for c in f12["record_counts"]} == {
        "perforation_interval": 1,
        "production_day": 1,
        "trajectory_station": 2,
    }
    assert f12["document_count"] == 3 and f12["record_count"] == 4
    assert listing["unresolved_record_count"] == 1
    (group,) = listing["unresolved"]
    assert group["reason"] == "not_a_well" and group["labels"] == ["Volve F"]
    assert listing["resolved_current"] is True
    well_f12 = next(w for w in listing["wells"] if w["name"] == "15/9-F-12")
    assert well_f12["record_count"] == 4 + 1 and well_f12["document_count"] == 4


def test_resolution_is_idempotent_with_stable_ids(world: World) -> None:
    pid = world.project()
    _volve_docs(world, pid)
    _resolve(world, pid)
    first = _listing(world, pid)
    again = _resolve(world, pid)
    second = _listing(world, pid)
    assert first == second
    assert again.wells == 5 and again.linked_records == first["linked_record_count"]
    assert world.sql("SELECT count(*) FROM well")[0][0] == 5


def test_identity_scope_never_merges_or_crosses_projects(world: World) -> None:
    a, b = world.project("A"), world.project("B")
    world.add_doc(a, "a.dat", [_perf("NO 15/9-F-12", "15/9-F-12", None, 1, 2)])
    # project B writes F-12 only unqualified: it must NOT borrow project A's block
    world.add_doc(
        b,
        "b.dat",
        [rec("note", _subj("F-12", "F-12", None), [attr("note.text", "x")])],
    )
    _resolve(world, a)
    _resolve(world, b)
    la, lb = _listing(world, a), _listing(world, b)
    assert [w["name"] for w in la["wells"]] == ["15/9-F-12"]
    assert lb["wells"] == []
    assert lb["unresolved"][0]["reason"] == "unqualified_label"
    # a wellbore id of project A is a 404 under project B
    wid = la["wells"][0]["wellbores"][0]["wellbore_id"]
    ok = world.api.client.get(f"/api/v1/projects/{a}/identity/wellbores/{wid}/evidence")
    cross = world.api.client.get(f"/api/v1/projects/{b}/identity/wellbores/{wid}/evidence")
    assert ok.status_code == 200 and cross.status_code == 404


def test_ambiguous_label_is_a_finding_and_creates_no_row(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "two_blocks.dat",
        [
            _perf("NO 15/9-F-12", "15/9-F-12", None, 1, 2),
            _perf("NO 16/1-F-12", "16/1-F-12", None, 1, 2),
            rec("note", _subj("F-12", "F-12", None), [attr("note.text", "x")]),
            # one record naming two different wells
            rec("note", _subj("NO 15/9-F-14", "NO 15/9-F-12", "15/9-F-14"), [attr("n", "x")]),
        ],
    )
    out = _resolve(world, pid)
    listing = _listing(world, pid)
    assert out.identity_findings >= 2
    assert sorted(_bores(listing)) == ["15/9-F-12", "16/1-F-12"]
    assert [w["name"] for w in listing["wells"]] == ["15/9-F-12", "16/1-F-12"]
    reasons = {g["reason"] for g in listing["unresolved"]}
    assert reasons == {"ambiguous"} and listing["unresolved_record_count"] == 2
    issues = world.sql(
        "SELECT code, severity, record_ordinals, blocked_operations FROM extraction_issue "
        "WHERE code = 'IDENTITY_MISMATCH'"
    )
    assert len(issues) == 2 and {i.severity for i in issues} == {"warning"}
    assert sorted(o for i in issues for o in i.record_ordinals) == [2, 3]
    # idempotent: findings are replaced, not duplicated
    _resolve(world, pid)
    assert (
        world.sql("SELECT count(*) FROM extraction_issue WHERE code='IDENTITY_MISMATCH'")[0][0] == 2
    )


def test_unqualified_spelling_joins_a_single_qualified_well(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "mixed.dat",
        [
            _perf("NO 15/9-F-12", "15/9-F-12", None, 1, 2),
            rec("note", _subj("F-12", "F-12 A", None), [attr("note.text", "x")]),
        ],
    )
    _resolve(world, pid)
    bores = _bores(_listing(world, pid))
    assert sorted(bores) == ["15/9-F-12", "15/9-F-12 A"], "F-12 and F-12 A stay distinct"
    assert bores["15/9-F-12 A"]["parent_wellbore_id"] == bores["15/9-F-12"]["wellbore_id"]


def test_wellbore_evidence_documents_and_locators(world: World) -> None:
    pid = world.project()
    _volve_docs(world, pid)
    _resolve(world, pid)
    bore = _bores(_listing(world, pid))["15/9-F-12"]
    r = world.api.client.get(
        f"/api/v1/projects/{pid}/identity/wellbores/{bore['wellbore_id']}/evidence"
    )
    assert r.status_code == 200
    docs = r.json()["documents"]
    assert sorted(d["filename"] for d in docs) == ["perf.dat", "prod.xlsx", "survey.pdf"]
    assert sum(d["record_count"] for d in docs) == bore["record_count"]
    assert all(d["first_record_locator"]["kind"] == "text" for d in docs)
    missing = world.api.client.get(
        f"/api/v1/projects/{pid}/identity/wellbores/{UUID(int=1)}/evidence"
    )
    assert missing.status_code == 404


def test_superseded_source_removes_unsupported_identities(world: World) -> None:
    pid = world.project()
    doc = world.add_doc(pid, "a.dat", [_perf("NO 15/9-F-12", "15/9-F-12", None, 1, 2)])
    world.add_doc(pid, "b.dat", [_perf("NO 15/9-F-14", "15/9-F-14", None, 1, 2)])
    _resolve(world, pid)
    assert len(_listing(world, pid)["wells"]) == 2
    world.sql("UPDATE extraction_run SET superseded = true WHERE run_id = :r", r=doc.run_id)
    _resolve(world, pid)
    listing = _listing(world, pid)
    assert [w["name"] for w in listing["wells"]] == ["15/9-F-14"]
    assert world.sql("SELECT count(*) FROM record_wellbore_link")[0][0] == 1


def test_depth_range_warning(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "perf.dat",
        [
            _perf("NO 15/9-F-12", "15/9-F-12", None, 3100, 3140),  # within +5% of 3000
            _perf("NO 15/9-F-12", "15/9-F-12", None, 3500, 3510),  # beyond: flagged
            _perf("NO 15/9-F-14", "15/9-F-14", None, 9000, 9010),  # no range known: no check
        ],
    )
    world.add_doc(pid, "survey.pdf", [_station("F-12", "15/9-F-12", 3000.0)])
    before = world.sql("SELECT attributes FROM extracted_record ORDER BY run_id, ordinal")
    out = _resolve(world, pid)
    assert out.range_findings == 1
    (issue,) = world.sql(
        "SELECT code, severity, message, record_ordinals, attribute_keys, blocked_operations "
        "FROM extraction_issue WHERE code='SUSPICIOUS_VALUE'"
    )
    assert issue.severity == "warning" and issue.blocked_operations == []
    assert issue.record_ordinals == [1] and "15/9-F-12" in issue.message
    assert "15/9-F-14" not in issue.message
    assert world.sql("SELECT attributes FROM extracted_record ORDER BY run_id, ordinal") == before
    _resolve(world, pid)  # idempotent
    assert (
        world.sql("SELECT count(*) FROM extraction_issue WHERE code='SUSPICIOUS_VALUE'")[0][0] == 1
    )


def test_depth_range_ignores_values_with_a_stated_unit_or_no_default(world: World) -> None:
    pid = world.project()
    stated = rec(
        "perforation_interval",
        _subj("NO 15/9-F-12", "NO 15/9-F-12", "15/9-F-12"),
        [attr("perforation.top_md", "99999", "m", number=99999.0)],
    )
    world.add_doc(pid, "perf.dat", [stated])
    world.add_doc(pid, "survey.pdf", [_station("F-12", "15/9-F-12", 3000.0)])
    assert _resolve(world, pid).range_findings == 0


def test_extraction_runner_resolves_identity_after_a_run(world: World) -> None:
    from tests.test_profiles_sources import PERF_HEAD, _perf_row

    pid = world.project()
    table = PERF_HEAD + _perf_row(1, 1, "4160.00", "4165.00", "2772.90", "2776.64", "2010-05-03")
    r = world.api.upload(pid, [("perf.dat", table.encode())])
    assert r.status_code in (200, 201, 202), r.text
    while world.api.worker.run_once():
        pass
    while world.api.worker.extraction.run_once():
        pass
    listing = _listing(world, pid)
    assert [w["name"] for w in listing["wells"]] == ["15/9-F-99"]
    assert listing["linked_record_count"] == 1 and listing["resolved_current"] is True
    explicit = world.api.client.post(
        f"/api/v1/projects/{pid}/identity/resolve", headers=world.api.headers
    )
    assert explicit.status_code == 200 and explicit.json()["linked_records"] == 1
    assert world.api.client.post(f"/api/v1/projects/{pid}/identity/resolve").status_code in (
        401,
        403,
    )


def test_identity_tables_cascade_with_record_and_wellbore(world: World) -> None:
    pid = world.project()
    doc = world.add_doc(pid, "a.dat", [_perf("NO 15/9-F-12", "15/9-F-12", None, 1, 2)])
    _resolve(world, pid)
    world.sql("DELETE FROM extraction_run WHERE run_id = :r", r=doc.run_id)
    assert world.sql("SELECT count(*) FROM record_wellbore_link")[0][0] == 0


def _prod(label: str, key: str, bore: str) -> dict[str, Any]:
    return rec(
        "production_day",
        _subj(key, bore, key, None, bore),
        [attr("production_day.bore_oil_vol", "1", number=1.0)],
    )


def _as_production(world: World, run_id: UUID) -> None:
    world.sql(
        "UPDATE extraction_run SET profile_name = 'production_workbook_volve' WHERE run_id = :r",
        r=run_id,
    )


def test_production_h_ah_alias_to_observed_base_only(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "perf.dat",
        [
            _perf("NO 15/9-F-12", "15/9-F-12", None, 1, 2),
            _perf("NO 15/9-F-5", "15/9-F-5", None, 1, 2),
            _perf("NO 15/9-F-12 T2", "15/9-F-12", "T2", 1, 2),
        ],
    )
    prod = world.add_doc(
        pid,
        "prod.xlsx",
        [
            _prod("F-12 H", "15/9-F-12", "NO 15/9-F-12 H"),
            _prod("F-12 H", "15/9-F-12", "NO 15/9-F-12 H"),
            _prod("F-5 AH", "15/9-F-5", "NO 15/9-F-5 AH"),
            _prod("F-12 T2", "15/9-F-12", "NO 15/9-F-12 T2"),  # not an alias suffix
            _prod("F-4 AH", "15/9-F-4", "NO 15/9-F-4 AH"),  # base F-4 never observed
        ],
    )
    _as_production(world, prod.run_id)
    # the same H label from a NON-production profile is not aliased
    world.add_doc(pid, "other.txt", [_prod("F-12 H", "15/9-F-12", "NO 15/9-F-12 H")])
    out = _resolve(world, pid)
    bores = _bores(_listing(world, pid))
    assert sorted(bores) == [
        "15/9-F-12",
        "15/9-F-12 H",  # only from the non-production document
        "15/9-F-12 T2",
        "15/9-F-4 AH",
        "15/9-F-5",
    ]
    counts = lambda n: {c["kind"]: c["records"] for c in bores[n]["record_counts"]}  # noqa: E731
    assert counts("15/9-F-12")["production_day"] == 2
    assert counts("15/9-F-5")["production_day"] == 1
    assert counts("15/9-F-12 T2")["production_day"] == 1
    assert counts("15/9-F-12 H") == {"production_day": 1}
    assert bores["15/9-F-4 AH"]["parent_wellbore_id"] is None
    bases = world.sql("SELECT basis, count(*) FROM record_wellbore_link GROUP BY basis ORDER BY 1")
    assert {b[0]: b[1] for b in bases} == {"alias:h_ah_production": 3, "label": 6}
    (finding,) = world.sql(
        "SELECT severity, message, blocked_operations FROM extraction_issue "
        "WHERE code='IDENTITY_MISMATCH' AND run_id = :r",
        r=prod.run_id,
    )
    assert finding.severity == "warning" and finding.blocked_operations == []
    assert "3 record(s)" in finding.message
    assert "15/9-F-12 H -> 15/9-F-12: 2" in finding.message
    assert "15/9-F-5 AH -> 15/9-F-5: 1" in finding.message
    assert out.identity_findings == 1
    # raw subject label stays in the record
    raw = world.sql(
        "SELECT count(*) FROM extracted_record WHERE subject->>'wellbore_name' = 'NO 15/9-F-12 H'"
    )
    assert raw[0][0] == 3
    _resolve(world, pid)  # idempotent
    assert (
        world.sql("SELECT count(*) FROM extraction_issue WHERE code='IDENTITY_MISMATCH'")[0][0] == 1
    )

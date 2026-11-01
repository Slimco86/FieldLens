"""TASK-056 PF-6 / PF-8 against PostgreSQL: per-wellbore exposure and the deterministic start gate.
Records are inserted directly (synthetic, invented values) with the real subject shapes."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

from fieldlens.identity.resolver import resolve_project
from fieldlens.persistence.session import session_scope
from tests.retrieval.support import Doc, World, attr, rec


def _subj(label: str, key: str, suffix: str | None = None) -> dict[str, Any]:
    return {
        "well_name": label,
        "wellbore_name": None,
        "wellbore_label": label,
        "well_key": key,
        "wellbore_suffix": suffix,
    }


def _station(
    label: str,
    key: str,
    md: float,
    incl: float | None = 10.0,
    azi: float | None = 45.0,
    state: str = "unreviewed",
    suffix: str | None = None,
) -> dict[str, Any]:
    attrs = [attr("trajectory_station.md", str(md), "m", number=md)]
    if incl is not None:
        attrs.append(attr("trajectory_station.incl", str(incl), "deg", number=incl))
    if azi is not None:
        attrs.append(attr("trajectory_station.azi", str(azi), "deg", number=azi))
    return rec("trajectory_station", _subj(label, key, suffix), attrs, state=state)


def _header(label: str, key: str, status_text: str | None, name: str = "S1") -> dict[str, Any]:
    a = attr("survey_report_header.survey_status", name)
    a["text"] = status_text
    if status_text is None:
        a["unknown_reason"] = "the file does not state whether the survey is planned or as-built"
    return rec("survey_report_header", _subj(label, key), [a])


def _surface(label: str, key: str, e: float | None, n: float | None) -> dict[str, Any]:
    attrs = []
    for k, v in (("easting", e), ("northing", n)):
        attrs.append(
            attr(f"well_surface_location.{k}", None if v is None else str(v), "m", number=v)
        )
    return rec("well_surface_location", _subj(label, key), attrs)


def _stations(label: str, key: str, n: int = 3) -> list[dict[str, Any]]:
    return [_station(label, key, 100.0 * (i + 1), 5.0 * i, 30.0) for i in range(n)]


def _resolve(world: World, pid: str) -> None:
    with session_scope(world.factory) as session:
        resolve_project(session, UUID(pid))


def _get(world: World, path: str) -> dict[str, Any]:
    r = world.api.client.get(path)
    assert r.status_code == 200, r.text
    return dict(r.json())


def _bore_id(world: World, pid: str, name: str) -> str:
    listing = _get(world, f"/api/v1/projects/{pid}/identity")
    return next(
        b["wellbore_id"] for w in listing["wells"] for b in w["wellbores"] if b["name"] == name
    )


def _cat(exposure: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in exposure["categories"] if c["category"] == name)


def _issue(
    world: World,
    pid: str,
    doc: Doc,
    code: str,
    severity: str,
    ordinals: list[int],
    keys: list[str],
    blocked: list[str],
) -> None:
    world.sql(
        "INSERT INTO extraction_issue (issue_id, project_id, run_id, producer_key, code, severity,"
        " message, attribute_keys, record_ordinals, locators, blocked_operations) VALUES"
        " (:i, :p, :r, :k, :c, :s, 'm', :ak, :ro, CAST(:l AS jsonb), :b)",
        i=uuid4(),
        p=UUID(pid),
        r=doc.run_id,
        k=f"k-{uuid4()}",
        c=code,
        s=severity,
        ak=keys,
        ro=ordinals,
        l=json.dumps([{"kind": "text", "line_start": 7, "line_end": 7}]),
        b=blocked,
    )


def test_wellbore_data_exposure(world: World) -> None:
    pid = world.project()
    f12, f11 = ("15/9-F-12", "15/9-F-12"), ("15/9-F-11", "15/9-F-11")
    traj = world.add_doc(
        pid,
        "survey.txt",
        [_header(*f12, "as_built"), *_stations(*f12, 4), *_stations(*f11, 2)],
    )
    perf = world.add_doc(
        pid,
        "perf.dat",
        [
            rec(
                "perforation_interval",
                _subj(*f12),
                [attr("perforation.top_md", "10", "m", number=10.0)],
            )
        ],
    )
    world.add_doc(
        pid,
        "prod.xlsx",
        [
            rec(
                "production_day",
                _subj(*f12),
                [attr("production_day.bore_oil_vol", "1", number=1.0)],
                state="conflicting",
            )
        ],
    )
    world.add_doc(pid, "loc.txt", [_surface(*f12, 1000.0, 2000.0)])
    _resolve(world, pid)
    # an interval conflict on the perforation record and a document-level gap on the survey
    _issue(world, pid, perf, "INTERVAL_CONFLICT", "warning", [0], ["perforation.top_md"], [])
    _issue(world, pid, traj, "MISSING_REFERENCE", "warning", [], ["trajectory_station.tvd"], [])
    bore = _bore_id(world, pid, "15/9-F-12")
    ev = _get(world, f"/api/v1/projects/{pid}/identity/wellbores/{bore}/evidence")
    exp = ev["exposure"]
    assert [c["category"] for c in exp["categories"]] == [
        "trajectory",
        "surface_location",
        "logs",
        "production",
        "equipment_completion",
        "perforations",
        "other",
    ]
    t = _cat(exp, "trajectory")
    assert t["present"] and t["record_count"] == 5  # header + 4 stations; F-11 stays apart
    st = next(g for g in t["groups"] if g["kind"] == "trajectory_station")
    assert st["record_count"] == 4 and len(st["sample"]) == 3 and st["sample_truncated"] is True
    assert st["survey_status"] == "as_built" and st["evidence_class"] == "source_record"
    sample_attr = st["sample"][0]["attributes"][0]
    assert sample_attr["locator"]["document_id"] == str(traj.document_id)
    assert sample_attr["locator"]["line_start"] == 1 and sample_attr["validation_state"]
    assert [g["code"] for g in t["gaps"]] == ["MISSING_REFERENCE"]
    assert t["gaps"][0]["scope"] == "document"
    p = _cat(exp, "perforations")
    assert [c["code"] for c in p["conflicts"]] == ["INTERVAL_CONFLICT"]
    assert p["conflicts"][0]["scope"] == "record"
    assert p["conflicts"][0]["locators"][0]["document_id"] == str(perf.document_id)
    assert _cat(exp, "production")["conflicting_record_count"] == 1
    logs = _cat(exp, "logs")
    assert logs["present"] is False and logs["gap_reasons"] == ["NO_RECORDS"]
    assert _cat(exp, "surface_location")["present"] is True
    assert exp["gate"]["location_state"] == "located"
    # project view keeps well and wellbore distinct and carries the gate
    full = _get(world, f"/api/v1/projects/{pid}/identity/exposure")
    assert {w["name"] for w in full["wells"]} == {"15/9-F-11", "15/9-F-12"}
    assert full["gate"]["can_start"] is True
    # the F-11 conflict/gap above never leaks to F-11
    f11_exp = next(
        b for w in full["wells"] for b in w["wellbores"] if b["wellbore_name"] == "15/9-F-11"
    )
    assert _cat(f11_exp, "perforations")["present"] is False
    assert _cat(f11_exp, "production")["present"] is False


def test_wellbore_exposure_is_project_scoped_and_proposals_are_not_facts(world: World) -> None:
    pid, other = world.project("A"), world.project("B")
    doc = world.add_doc(pid, "survey.txt", _stations("15/9-F-12", "15/9-F-12"))
    world.add_doc(other, "o.txt", _stations("15/9-F-12", "15/9-F-12"))
    _resolve(world, pid)
    _resolve(world, other)
    bore = _bore_id(world, pid, "15/9-F-12")
    foreign = _bore_id(world, other, "15/9-F-12")
    r = world.api.client.get(f"/api/v1/projects/{pid}/identity/wellbores/{foreign}/evidence")
    assert r.status_code == 404
    assert world.api.client.get(f"/api/v1/projects/{uuid4()}/identity/exposure").status_code == 404
    unit = uuid4()
    world.sql(
        "INSERT INTO agent_work_unit (unit_id, project_id, source_revision_id, unit_key, question,"
        " state, stop_reason, finished_at) VALUES (:u, :p, :rev, 'u1', 'q', 'succeeded', 'done',"
        " now())",
        u=unit,
        p=UUID(pid),
        rev=doc.revision_id,
    )
    for key, method, state, validation in (
        ("c1", "model_read", "candidate", "unverified"),
        ("c2", "model_proposal", "accepted", "valid"),
    ):
        world.sql(
            "INSERT INTO extraction_candidate (project_id, unit_id, source_revision_id, document_id,"
            " wellbore_id, candidate_key, method, validation_state, state, label, attributes,"
            " locator, model_id, prompt_version, harness_version) VALUES (:p, :u, :rev, :d, :w,"
            " :k, :m, :v, :s, 'label', CAST(:a AS jsonb), CAST(:l AS jsonb), 'm', 'p', 'h')",
            p=UUID(pid),
            u=unit,
            rev=doc.revision_id,
            d=doc.document_id,
            w=UUID(bore),
            k=key,
            m=method,
            v=validation,
            s=state,
            a=json.dumps({"kind": "equipment", "category": "packer"}),
            l=json.dumps({"kind": "pdf_page", "page": 3}),
        )
    exp = _get(world, f"/api/v1/projects/{pid}/identity/wellbores/{bore}/evidence")["exposure"]
    eq = _cat(exp, "equipment_completion")
    assert eq["groups"] == [] and eq["present"] is True and eq["proposal_total"] == 2
    assert eq["accepted_proposal_count"] == 1
    by_key = {p["state"]: p for p in eq["proposals"]}
    assert by_key["candidate"]["is_accepted_fact"] is False
    assert by_key["accepted"]["is_accepted_fact"] is True
    assert by_key["candidate"]["locator"]["document_id"] == str(doc.document_id)


def test_reconstruction_start_gate(world: World) -> None:
    pid = world.project()
    gate_url = f"/api/v1/projects/{pid}/identity/start-gate"
    # nothing identified
    g = _get(world, gate_url)
    assert g["can_start"] is False and g["unmet"][0]["code"] == "NO_WELLBORE_IDENTIFIED"
    assert [c["met"] for c in g["conditions"]] == [False, False]

    # F-1: identified but no trajectory; F-2: planned only; F-3: unstated; F-4: too few/invalid
    world.add_doc(pid, "perf.dat", [rec("perforation_interval", _subj("15/9-F-1", "15/9-F-1"), [])])
    world.add_doc(
        pid,
        "plan.txt",
        [_header("15/9-F-2", "15/9-F-2", "planned"), *_stations("15/9-F-2", "15/9-F-2")],
    )
    world.add_doc(
        pid, "unk.txt", [_header("15/9-F-3", "15/9-F-3", None), *_stations("15/9-F-3", "15/9-F-3")]
    )
    world.add_doc(
        pid,
        "bad.txt",
        [
            _station("15/9-F-4", "15/9-F-4", 100.0),
            _station("15/9-F-5", "15/9-F-5", 100.0, incl=None),
            _station("15/9-F-5", "15/9-F-5", 200.0, incl=None),
            _station("15/9-F-6", "15/9-F-6", 300.0),
            _station("15/9-F-6", "15/9-F-6", 200.0),
            _station("15/9-F-7", "15/9-F-7", 100.0, state="invalid"),
            _station("15/9-F-7", "15/9-F-7", 200.0),
        ],
    )
    _resolve(world, pid)
    g = _get(world, gate_url)
    assert g["can_start"] is False and g["unmet"][0]["code"] == "NO_VALIDATED_TRAJECTORY"
    assert [c["code"] for c in g["conditions"] if not c["met"]] == ["VALIDATED_TRAJECTORY"]
    by = {w["wellbore_name"]: w for w in g["wellbores"]}
    codes = {n: {u["code"] for u in w["unmet"]} for n, w in by.items()}
    assert codes["15/9-F-1"] == {"NO_TRAJECTORY_RECORDS"}
    assert codes["15/9-F-2"] == {"TRAJECTORY_PLANNED_ONLY"}
    assert codes["15/9-F-3"] == {"TRAJECTORY_STATUS_UNSTATED"}
    assert codes["15/9-F-4"] == {"TRAJECTORY_TOO_FEW_STATIONS"}
    assert codes["15/9-F-5"] == {"TRAJECTORY_INVALID_STATIONS"}
    assert codes["15/9-F-6"] == {"TRAJECTORY_MD_NOT_MONOTONIC"}
    assert "TRAJECTORY_INVALID_STATIONS" in codes["15/9-F-7"]
    assert g["qualifying_wellbore_ids"] == []

    # a validated as-built trajectory without a surface location starts, with a warning only
    good = world.add_doc(
        pid,
        "good.txt",
        [_header("15/9-F-8", "15/9-F-8", "as_built"), *_stations("15/9-F-8", "15/9-F-8")],
    )
    _resolve(world, pid)
    g = _get(world, gate_url)
    assert g["can_start"] is True and g["unmet"] == []
    f8 = next(w for w in g["wellbores"] if w["wellbore_name"] == "15/9-F-8")
    assert g["qualifying_wellbore_ids"] == [f8["wellbore_id"]]
    assert f8["unlocated"] is True and f8["location_state"] == "unlocated"
    assert "SURFACE_LOCATION_MISSING" in {w["code"] for w in g["warnings"]}
    assert f8["trajectory_sets"][0]["validated"] and f8["trajectory_sets"][0]["reasons"] == []

    # an error finding that blocks geometry on that trajectory withdraws the gate
    _issue(
        world,
        pid,
        good,
        "SUSPICIOUS_VALUE",
        "error",
        [1],
        ["trajectory_station.md"],
        ["physical_geometry"],
    )
    g = _get(world, gate_url)
    assert g["can_start"] is False
    f8 = next(w for w in g["wellbores"] if w["wellbore_name"] == "15/9-F-8")
    assert {u["code"] for u in f8["unmet"]} == {"TRAJECTORY_BLOCKING_ISSUE"}
    world.sql("DELETE FROM extraction_issue WHERE run_id = :r", r=good.run_id)

    # a sourced surface location clears the warning; an incomplete one does not
    loc = world.add_doc(pid, "loc.txt", [_surface("15/9-F-8", "15/9-F-8", 1.0, None)])
    _resolve(world, pid)
    g = _get(world, gate_url)
    assert g["can_start"] is True
    assert "SURFACE_LOCATION_INCOMPLETE" in {w["code"] for w in g["warnings"]}
    world.sql("UPDATE extraction_run SET superseded = true WHERE run_id = :r", r=loc.run_id)
    world.add_doc(pid, "loc2.txt", [_surface("15/9-F-8", "15/9-F-8", 1.0, 2.0)])
    _resolve(world, pid)
    g = _get(world, gate_url)
    f8 = next(w for w in g["wellbores"] if w["wellbore_name"] == "15/9-F-8")
    assert f8["unlocated"] is False and g["warnings"] == []


def test_gate_is_read_only_and_deterministic(world: World) -> None:
    pid = world.project()
    world.add_doc(
        pid,
        "a.txt",
        [_header("15/9-F-8", "15/9-F-8", "as_built"), *_stations("15/9-F-8", "15/9-F-8")],
    )
    _resolve(world, pid)
    before = world.sql("SELECT count(*) FROM wellbore")[0][0]
    one = _get(world, f"/api/v1/projects/{pid}/identity/start-gate")
    two = _get(world, f"/api/v1/projects/{pid}/identity/start-gate")
    assert one == two and one["can_start"] is True
    assert world.sql("SELECT count(*) FROM wellbore")[0][0] == before

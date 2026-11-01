"""TASK-056 QA D1: the exposure caps are reported (totals and truncation flags), never silent."""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from tests.identity.test_wellbore_exposure import (
    _bore_id,
    _cat,
    _get,
    _issue,
    _resolve,
    _stations,
)
from tests.retrieval.support import World


def test_caps_are_reported_not_silent(world: World) -> None:
    pid = world.project("A")
    doc = world.add_doc(pid, "survey.txt", _stations("15/9-F-12", "15/9-F-12"))
    _resolve(world, pid)
    bore = _bore_id(world, pid, "15/9-F-12")
    for _ in range(130):
        _issue(world, pid, doc, "some_note", "info", [], ["trajectory_station.md"], [])
    unit = uuid4()
    world.sql(
        "INSERT INTO agent_work_unit (unit_id, project_id, source_revision_id, unit_key, question,"
        " state, stop_reason, finished_at) VALUES (:u, :p, :rev, 'u1', 'q', 'succeeded', 'done',"
        " now())",
        u=unit,
        p=UUID(pid),
        rev=doc.revision_id,
    )
    world.sql(
        "INSERT INTO extraction_candidate (project_id, unit_id, source_revision_id, document_id,"
        " wellbore_id, candidate_key, method, validation_state, state, label, attributes,"
        " locator, model_id, prompt_version, harness_version)"
        " SELECT :p, :u, :rev, :d, :w, 'c' || g, 'model_proposal',"
        " 'valid', CASE WHEN g % 2 = 0 THEN 'accepted' ELSE 'candidate' END, 'label',"
        " CAST(:a AS jsonb), CAST(:l AS jsonb), 'm', 'p', 'h' FROM generate_series(1, 5100) g",
        p=UUID(pid),
        u=unit,
        rev=doc.revision_id,
        d=doc.document_id,
        w=UUID(bore),
        a=json.dumps({"kind": "equipment", "category": "packer"}),
        l=json.dumps({"kind": "pdf_page", "page": 3}),
    )
    exp = _get(world, f"/api/v1/projects/{pid}/identity/wellbores/{bore}/evidence")["exposure"]
    eq = _cat(exp, "equipment_completion")
    assert eq["proposal_total"] == 5100 and eq["accepted_proposal_count"] == 2550
    assert eq["proposals_truncated"] is True and len(eq["proposals"]) == 25
    tr = _cat(exp, "trajectory")
    returned = len(tr["conflicts"]) + len(tr["gaps"]) + len(tr["findings"])
    assert tr["findings_total"] == 130 and tr["findings_truncated"] is True
    assert returned == 100
    logs = _cat(exp, "logs")
    assert logs["findings_total"] == 0 and logs["findings_truncated"] is False
    assert logs["proposals_truncated"] is False

"""TASK-087 B-3: the chosen survey set names its document, filename and (PDF) page."""

from __future__ import annotations

from typing import Any

from tests.retrieval.support import World
from tests.wellpath.test_trajectory_route import F5, _bore, _get, _hdr, _st


def _paged(md: float, page: int) -> dict[str, Any]:
    r = _st(F5, md, 0.0, 0.0, tvd=md)
    r["locator"] = {"kind": "pdf_table", "page": page, "table_id": "t1"}
    return r


def test_survey_set_carries_document_filename_and_page(world: World) -> None:
    pid = world.project()
    doc = world.add_doc(pid, "ssr.pdf", [_hdr(F5, "as_built"), _paged(0.0, 4), _paged(500.0, 4)])
    r = _get(world, pid, _bore(world, pid, "15/9-F-5"))
    assert r.status_code == 200, r.text
    ref = r.json()["survey_set"]
    assert ref["document_id"] == str(doc.document_id)
    assert ref["filename"] == "ssr.pdf" and ref["page"] == 4


def test_non_paged_source_has_no_page(world: World) -> None:
    pid = world.project()
    rows = [
        _hdr(F5, "as_built"),
        _st(F5, 0.0, 0.0, 0.0, tvd=0.0),
        _st(F5, 500.0, 0.0, 0.0, tvd=500.0),
    ]
    world.add_doc(pid, "survey.txt", rows)
    ref = _get(world, pid, _bore(world, pid, "15/9-F-5")).json()["survey_set"]
    assert ref["page"] is None and ref["filename"] == "survey.txt" and ref["document_id"]

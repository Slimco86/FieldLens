"""Opt-in (``-m local_data``): page triage and rendering on the approved real completion PDFs.

Covers ONLY: triage selects the known equipment/perforation pages of the text-layer reports, a
scanned report has no text layer (nothing scored), and rendering stays within the size cap and the
orientation rules (no model call, nothing leaves the host; files are read in place)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from fieldlens.candidates.pages import PageRenderer
from fieldlens.candidates.triage import triage

pytestmark = pytest.mark.local_data
_ENV = os.environ.get("FIELDLENS_LOCAL_DATA_ROOT")
if not _ENV or not Path(_ENV).is_dir():
    pytest.skip("FIELDLENS_LOCAL_DATA_ROOT is not set to a directory", allow_module_level=True)
BASE = Path(_ENV) / "Well_logs_pr_WELL"
PV13 = BASE / "15_9-F-12/14.DIV.REPORTS/COMPLETION_REPORT_3.PDF"
PV17 = BASE / "15_9-F-14/14.DIV.REPORTS/FWR_Completion_F14.pdf"
PV11 = BASE / "15_9-F-12/14.DIV.REPORTS/COMPLETION_REPORT_1.PDF"


class _Store:
    def path_for(self, key: str) -> Path:
        return Path(key)


@pytest.mark.skipif(not PV13.exists(), reason="PV-13 not present")
def test_triage_and_render_text_layer_report() -> None:
    r = PageRenderer(_Store())  # type: ignore[arg-type]
    result = triage(r.all_page_texts(str(PV13)))
    assert len(result.selected) <= 12 and {58, 17} <= set(result.selected)
    img = r.render("pv13", str(PV13), 58)
    assert max(img.width, img.height) == 1600 and img.orientation == "text_layer"
    assert r.render("pv13", str(PV13), 58).cache_hit


@pytest.mark.skipif(not PV11.exists(), reason="PV-11 not present")
def test_triage_finds_perforation_tables() -> None:
    r = PageRenderer(_Store())  # type: ignore[arg-type]
    assert {74, 136} <= set(triage(r.all_page_texts(str(PV11))).selected)


@pytest.mark.skipif(not PV17.exists(), reason="PV-17 not present")
def test_scanned_report_has_no_text_layer_and_is_not_rotated_by_default() -> None:
    r = PageRenderer(_Store())  # type: ignore[arg-type]
    result = triage(r.all_page_texts(str(PV17)))
    assert result.selected == [] and result.strategy == "no_text_layer"
    assert result.unscored_pages == result.pages_total
    img = r.render("pv17", str(PV17), 36)
    assert img.orientation == "none" and img.rotation_applied == 0

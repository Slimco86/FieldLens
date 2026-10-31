"""Shared constants for the TASK-042 completion-document spike (experiment, not product code)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path("/mnt/c/Users/slimc/Downloads/Hackathon_Data/Well_logs_pr_WELL")
SCRATCH = Path(".local/spike042")

# The ONLY seven files the owner approved for the provider (October 31).
DOCS: dict[str, tuple[str, str]] = {
    "PV-11": ("F-12", "15_9-F-12/14.DIV.REPORTS/COMPLETION_REPORT_1.PDF"),
    "PV-12": ("F-12", "15_9-F-12/14.DIV.REPORTS/COMPLETION_REPORT_2.PDF"),
    "PV-13": ("F-12", "15_9-F-12/14.DIV.REPORTS/COMPLETION_REPORT_3.PDF"),
    "PV-14": ("F-12", "15_9-F-12/14.DIV.REPORTS/COMPLETION_LOG_MD_PLOT_2.PDF"),
    "PV-17": ("F-14", "15_9-F-14/14.DIV.REPORTS/FWR_Completion_F14.pdf"),
    "PV-18": ("F-14", "15_9-F-14/14.DIV.REPORTS/completion_log_F14.pdf"),
    "PV-21": ("F-5", "15_9-F-5/14.DIV.REPORTS/COMPLETION_REPORT_1.PDF"),
}


def doc_path(pv: str) -> Path:
    return ROOT / DOCS[pv][1]

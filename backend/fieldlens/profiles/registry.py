"""Profile registry: content-based selection and versions.

Selection looks only at content (XML root + namespace, workbook sheets/headers, LAS ``~V``/``~A``,
table headers, PDF text); filename and upload category are passed through as hints and ignored.
A profile version bump makes every run of that profile stale (derived records are re-derived)."""

from __future__ import annotations

from pathlib import Path

from .dat_tables import PerforationTableProfile, PickTableProfile
from .las import LasProfile
from .pdf_survey import SurveyReportProfile
from .production import ProductionWorkbookProfile
from .types import Profile
from .witsml import WitsmlProfile

PROFILES: tuple[Profile, ...] = (  # type: ignore[assignment]
    WitsmlProfile("trajectory"),
    WitsmlProfile("tubular"),
    WitsmlProfile("bha_run"),
    WitsmlProfile("wb_geometry"),
    ProductionWorkbookProfile(),
    LasProfile(),
    PerforationTableProfile(),
    PickTableProfile(),
    SurveyReportProfile(),
)
_BY_NAME = {p.name: p for p in PROFILES}


def by_name(name: str) -> Profile | None:
    return _BY_NAME.get(name)


def current_version(name: str) -> str | None:
    profile = _BY_NAME.get(name)
    return None if profile is None else profile.version


def detect(path: Path, format_family: str, filename: str) -> list[Profile]:
    """Every profile whose content check passes (normally exactly one)."""
    found: list[Profile] = []
    for profile in PROFILES:
        if format_family not in profile.families:
            continue
        try:
            if profile.detect(path, format_family, filename):
                found.append(profile)
        except Exception:  # noqa: S112 - detection must never take the worker down
            continue
    return found

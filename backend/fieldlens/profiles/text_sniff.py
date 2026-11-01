"""Content sniffers for plain-text survey exports, shared by upload intake and the profiles.

Intake marks a text file ``pending_extraction`` when any known survey-text layout is recognized
by content (never the file name); each layout has its own profile."""

from __future__ import annotations

from collections.abc import Iterable

from .compass_text import sniff_compass_text
from .statoil_survey_text import sniff_statoil_survey_text

SURVEY_TEXT_SNIFFERS = (sniff_compass_text, sniff_statoil_survey_text)


def sniff_survey_text(lines: Iterable[str]) -> bool:
    materialized = list(lines)
    return any(sniff(materialized) for sniff in SURVEY_TEXT_SNIFFERS)

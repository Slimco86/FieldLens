"""The shared label rule (pure) and its retrieval consumers stay in step."""

from __future__ import annotations

import pytest

from fieldlens.identity.labels import BoreLabel, parse_bore_label
from fieldlens.retrieval import identifiers
from fieldlens.retrieval.text import norm_identifier


@pytest.mark.parametrize(
    ("label", "hint", "expected"),
    [
        ("NO 15/9-F-11 B", None, BoreLabel("15/9", "F-11", "B")),
        ("NO 15/9-F-11", "B", BoreLabel("15/9", "F-11", "B")),
        ("15/9-F5", None, BoreLabel("15/9", "F-5", None)),
        ("F-12", None, BoreLabel(None, "F-12", None)),
        ("F-12 A", None, BoreLabel(None, "F-12", "A")),
        ("NO 15/9-19 BT2", None, BoreLabel("15/9", "19", "BT2")),
        ("NO 15/9-19 SR", None, BoreLabel("15/9", "19", "SR")),
        ("NO 15/9-C-2 AHT2", None, BoreLabel("15/9", "C-2", "AHT2")),
        ("NO 15/9-F-12 pilot", None, BoreLabel("15/9", "F-12", "PILOT")),
        ("NO 15/5-7 A", None, BoreLabel("15/5", "7", "A")),
    ],
)
def test_bore_label_rule(label: str, hint: str | None, expected: BoreLabel) -> None:
    assert parse_bore_label(label, hint) == expected


@pytest.mark.parametrize(
    "label", ["Volve F", "Volve", "", "12", "19", "Hugin Fm. Top", "15/9", "NO 15/9-F-12 a b c d"]
)
def test_field_level_and_free_text_labels_are_not_wells(label: str) -> None:
    assert parse_bore_label(label) is None


def test_contradicting_suffix_hint_does_not_parse() -> None:
    assert parse_bore_label("NO 15/9-F-11 B", "A") is None


def test_canonical_names() -> None:
    bore = parse_bore_label("no 15/9-f-11 b")
    assert bore is not None
    assert (bore.well_name, bore.wellbore_name) == ("15/9-F-11", "15/9-F-11 B")


def test_retrieval_uses_the_shared_rule_unchanged() -> None:
    assert norm_identifier("  NO  15/9-F-12 ") == "no 15/9-f-12"
    assert identifiers.aliases("NO 15/9-F-12") == ["no 15/9-f-12", "15/9-f-12", "f-12"]
    assert identifiers.has_suffix("15/9-F-12 A") and not identifiers.has_suffix("15/9-F-12")
    # retrieval's historic rule does not treat numeric-only wells' suffixes as sidetracks; the
    # identity rule does (kept separate on purpose so stored retrieval identifiers do not move)
    assert not identifiers.has_suffix("15/9-19 BT2")
    assert parse_bore_label("15/9-19 BT2") == BoreLabel("15/9", "19", "BT2")

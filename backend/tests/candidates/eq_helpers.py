"""Helpers for the equipment-candidate tests (offline stub provider, synthetic pages)."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from fieldlens.candidates.equipment_prompt import EQUIPMENT_QUESTION
from fieldlens.candidates.harness import ExtractionHarness, UnitOutcome, UnitRequest
from tests.candidates.conftest import World
from tests.candidates.helpers import loc
from tests.candidates.support import FixtureProvider, json_response


def equip(doc: UUID, page: int | None = 1, **over: Any) -> dict[str, Any]:
    """A valid equipment candidate (production packer with a printed MD depth)."""
    base: dict[str, Any] = {
        "kind": "equipment",
        "category": "packer",
        "label_text": "Production packer",
        "top_depth": {"value_text": "3064.39", "unit": "m", "reference_text": "MD"},
        "locator": loc(doc, page=page) if page is not None else loc(doc),
    }
    base.update(over)
    return base


def run_equip(
    world: World,
    items: list[dict[str, Any]],
    *,
    doc: UUID,
    page: int | None = 1,
    line_range: tuple[int, int] | None = None,
    rotation: int | None = None,
    subject: str | None = None,
    provider: FixtureProvider | None = None,
    harness: ExtractionHarness | None = None,
    question: str = EQUIPMENT_QUESTION,
    **config: Any,
) -> tuple[UnitOutcome, FixtureProvider]:
    p = provider or FixtureProvider(lambda req, n: json_response(items))
    h = harness or world.harness(p, **config)
    out = h.run_unit(
        UnitRequest(
            world.project_id,
            world.revision_id,
            doc,
            question,
            "equipment",
            page=page,
            line_range=line_range,
            rotation=rotation,
            document_subject=subject,
        )
    )
    return out, p


def eq_rows(world: World) -> list[dict[str, Any]]:
    raw = world.rows(
        "select state, method, validation_state, reason_codes, label, wellbore_id, "
        "conflicts_with_record_id, validator_results::text, attributes::text, "
        "locator::text, prompt_version from extraction_candidate "
        "where attributes->>'kind' = 'equipment' order by created_at, unit_id, ordinal"
    )
    keys = (
        "state method validation_state reasons label wellbore_id conflict validators "
        "attributes locator prompt"
    ).split()
    out = [dict(zip(keys, r, strict=True)) for r in raw]
    for r in out:
        r["attrs"] = json.loads(r["attributes"])
    return out

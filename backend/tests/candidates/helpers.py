from __future__ import annotations

from typing import Any
from uuid import UUID

from fieldlens.candidates.harness import ExtractionHarness, UnitOutcome, UnitRequest
from tests.candidates.conftest import SUBJECT, World
from tests.candidates.support import FixtureProvider, json_response


def loc(doc: UUID, a: int = 2, b: int | None = None, page: int | None = None) -> dict[str, Any]:
    if page is not None:
        return {"document_id": str(doc), "page": page}
    return {"document_id": str(doc), "line_start": a, "line_end": b or a}


def meas(world: World, **over: Any) -> dict[str, Any]:
    """A valid top_md candidate on line 2 of the perforation table; override to break it."""
    base: dict[str, Any] = {
        "kind": "measurement",
        "attribute_key": "perforation.top_md",
        "value_text": "4160.00",
        "unit": "m",
        "quote": "4160.00",
        "locator": loc(world.perf_doc),
        "subject": SUBJECT,
    }
    base.update(over)
    return base


def page_item(doc: UUID, page: int, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "kind": "page_read",
        "item_type": "packer",
        "name": "Production packer",
        "sizes_text": [],
        "depth_text": "3064.39 m MD",
        "quote": "Production packer 3064.39 m MD Baker",
        "locator": loc(doc, page=page),
        "subject": SUBJECT,
    }
    base.update(over)
    return base


def run_cands(
    world: World,
    candidates: list[dict[str, Any]],
    *,
    question: str = "What are the perforation depths?",
    doc: UUID | None = None,
    line_range: tuple[int, int] | None = (1, 3),
    kind: str = "measurement",
    page: int | None = None,
    provider: FixtureProvider | None = None,
    harness: ExtractionHarness | None = None,
    **config: Any,
) -> tuple[UnitOutcome, FixtureProvider]:
    p = provider or FixtureProvider(lambda req, n: json_response(candidates))
    h = harness or world.harness(p, **config)
    out = h.run_unit(
        UnitRequest(
            world.project_id,
            world.revision_id,
            doc or world.perf_doc,
            question,
            kind,  # type: ignore[arg-type]
            page=page,
            line_range=line_range,
        )
    )
    return out, p


def rows(world: World) -> list[dict[str, Any]]:
    with_ = world.rows(
        "select state, method, validation_state, reason_codes, label, wellbore_id, "
        "conflicts_with_record_id, validator_results::text, attributes::text, quote, "
        "locator::text from extraction_candidate order by created_at, unit_id, ordinal"
    )
    keys = (
        "state method validation_state reasons label wellbore_id conflict validators "
        "attributes quote locator"
    ).split()
    return [dict(zip(keys, r, strict=True)) for r in with_]

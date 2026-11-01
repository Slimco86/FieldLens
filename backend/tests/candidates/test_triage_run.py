"""AX-14: page triage (no model call), bounded read concurrency, recorded timing."""

from __future__ import annotations

import json
import re
from typing import Any

from fieldlens.candidates.triage import DEFAULT_MAX_PAGES, triage
from tests.candidates.conftest import World
from tests.candidates.helpers import page_item
from tests.candidates.support import FixtureProvider, first_user_text, json_response

EQUIP = "Completion string packer tubing perforation liner hanger gas lift mandrel " * 2
FILLER = "Daily drilling report mud weight rig crew shift handover " * 3


def test_page_triage() -> None:
    texts = ["Contents\nCompletion schematic ........ 5\nPerforation intervals ...... 8"]
    texts += [FILLER] * 3 + [EQUIP + " schematic"] + [FILLER] * 2 + [EQUIP]  # pages 5 and 8
    texts += [f"{EQUIP} variant {i}" for i in range(12)]
    texts += [FILLER] * 5
    result = triage(texts)
    assert len(result.pages) == DEFAULT_MAX_PAGES == 12  # capped
    assert result.strategy == "toc+keyword" and result.toc_entries == 2
    assert 1 not in result.selected  # the contents page itself is not a page to read
    assert result.selected[:2] == [5, 8]  # printed contents boost the pages it names
    assert all(not texts[p - 1].startswith("Daily") for p in result.selected)
    assert triage(texts, max_pages=5).selected == result.selected[:5]  # configurable
    assert result.pages_total == len(texts) and result.unscored_pages == 0
    # no text layer at all: nothing can be scored, and the result says so
    blank = triage(["", "  ", ""])
    assert blank.selected == [] and blank.strategy == "no_text_layer" and blank.unscored_pages == 3
    sampled = triage([""] * 40, max_pages=5, blind_sample=True)
    assert len(sampled.selected) == 5 and sampled.strategy == "blind_sample"
    # partially layered documents report what could not be scored
    mixed = triage(["", EQUIP, FILLER])
    assert mixed.selected == [2] and mixed.unscored_pages == 1 and mixed.notes


def test_page_triage_on_pdf_makes_no_model_call(world: World) -> None:
    provider = FixtureProvider(lambda r, n: json_response([]))
    h = world.harness(provider)
    doc = world.reader.require(world.project_id, world.revision_id, world.big_doc)
    result = triage(world.reader.page_texts(doc))
    assert provider.calls == []
    assert result.pages_total == 14 and 1 not in result.selected and 14 not in result.selected
    assert len(result.selected) == 12
    # a scan with no usable layer selects nothing and the run is visibly not a success
    summary = h.run_document(world.project_id, world.revision_id, world.scan_doc, "q")
    assert summary.state == "failed" and summary.stop_reason == "no_pages_selected"
    assert provider.calls == [] and summary.pages == []


def _page_responder(world: World) -> Any:
    def respond(req: Any, n: int) -> Any:
        page = int(re.search(r'"page":(\d+)', first_user_text(req)).group(1))  # type: ignore[union-attr]
        return json_response([page_item(world.big_doc, page)])

    return respond


def test_concurrency_bound(world: World) -> None:
    provider = FixtureProvider(_page_responder(world), latency_s=0.05)
    h = world.harness(provider)
    summary = h.run_document(
        world.project_id, world.revision_id, world.big_doc, "equipment on this page?"
    )
    assert summary.state == "succeeded" and len(summary.pages) == 12
    assert 2 <= provider.max_in_flight <= 3  # default read concurrency is 3
    assert all(c.effort == "low" for c in provider.calls)  # pages are read at effort low
    serial = FixtureProvider(_page_responder(world), latency_s=0.01)
    h2 = world.harness(serial)
    s2 = h2.run_document(
        world.project_id, world.revision_id, world.big_doc, "serial question", concurrency=1
    )
    assert s2.state == "succeeded" and serial.max_in_flight == 1
    # one more candidate per page, accepted: the text layer verifies each quote
    assert world.scalar("select count(*) from extraction_candidate where state='accepted'") == 24


def test_run_timing_recorded(world: World) -> None:
    provider = FixtureProvider(_page_responder(world), latency_s=0.2)  # stub-latency model
    h = world.harness(provider)
    summary = h.run_document(world.project_id, world.revision_id, world.big_doc, "timing?")
    assert summary.state == "succeeded"
    assert summary.wall_s < 300  # AX-14 budget for a 12-page document (stub latency model)
    assert summary.wall_s < 12 * 0.2  # concurrency 3 beats serial
    steps = world.rows(
        "select summary, detail::text from agent_step where unit_id=:u order by step_no",
        u=summary.run_unit_id,
    )
    details = [json.loads(s[1]) for s in steps]
    pages = [d for d in details if "latency_ms" in d and "page" in d]
    assert sorted(d["page"] for d in pages) == sorted(summary.triage.selected)  # type: ignore[union-attr]
    assert all(
        d["latency_ms"] >= 200 and d["in_tok"] == 1200 and d["out_tok"] == 300 for d in pages
    )
    assert all(d["cost_usd"] > 0 for d in pages)
    triage_step = details[0]
    assert triage_step["strategy"] == "toc+keyword" and len(triage_step["selected"]) == 12
    final = details[-1]
    assert final["wall_ms"] >= 1 and final["concurrency"] == 3 and final["effort"] == "low"
    assert final["in_tok"] == 12 * 1200 and final["out_tok"] == 12 * 300
    assert abs(final["cost_usd"] - sum(d["cost_usd"] for d in pages)) < 1e-6
    assert len(final["pages_read"]) == 12 and final["pages_failed"] == []
    # the same run again is served from the cache: no new provider call
    before = len(provider.calls)
    again = h.run_document(world.project_id, world.revision_id, world.big_doc, "timing?")
    assert again.pages_cached == 12 and len(provider.calls) == before

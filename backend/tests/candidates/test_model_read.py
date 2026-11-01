"""AX-13: model-read candidates (page image without a text layer) are marked, unverified, never
accepted, and never feed a calculation. Offline stub provider."""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from fieldlens.assistant.messages import ImagePart
from fieldlens.engineering.perforation.engine import PerforationHistory
from fieldlens.engineering.provenance import MARKER_REASON, is_model_proposal
from tests.candidates.conftest import SUBJECT, World
from tests.candidates.helpers import loc, meas, page_item, rows, run_cands
from tests.candidates.support import FixtureProvider, json_response


def _scan_item(world: World, **over: Any) -> dict[str, Any]:
    return page_item(world.scan_doc, 1, quote=None, depth_text="3064 m", **over)


def test_model_read_marked(world: World) -> None:
    provider = FixtureProvider(lambda r, n: json_response([_scan_item(world)]))
    out, _ = run_cands(
        world, [], provider=provider, doc=world.scan_doc, kind="page_read", page=1, line_range=None
    )
    assert out.state == "succeeded" and out.candidates == {"candidate": 1}
    (row,) = rows(world)
    assert row["method"] == "model_read" and row["validation_state"] == "unverified"
    assert row["state"] == "candidate" and row["label"] == "model-read, unverified"
    assert "model_read_unverified" in row["reasons"]
    assert json.loads(row["locator"])["kind"] == "pdf" and json.loads(row["locator"])["page"] == 1
    validators = json.loads(row["validators"])
    quote = next(v for v in validators if v["validator"] == "quote")
    assert quote["outcome"] == "skipped"  # skipped only for image-only evidence
    # the harness attached the page image (no text layer) to the model request
    parts = [p for m in provider.calls[0].messages for p in m.parts]
    assert any(isinstance(p, ImagePart) for p in parts)
    # a model-read value never counts as an accepted engineering fact
    assert world.scalar("select count(*) from extraction_candidate where state='accepted'") == 0


def test_model_read_measurement_is_never_accepted(world: World) -> None:
    item = {
        "kind": "measurement",
        "attribute_key": "packer.depth",
        "value_text": "3064",
        "unit": "m",
        "locator": loc(world.scan_doc, page=1),
        "subject": SUBJECT,
    }
    out, _ = run_cands(
        world, [item], doc=world.scan_doc, kind="page_read", page=1, line_range=None
    )
    assert out.state == "succeeded"
    (row,) = rows(world)
    assert row["method"] == "model_read" and row["state"] in ("candidate", "flagged")
    assert row["validation_state"] == "unverified"
    # unit/range validators still run on image-read values
    bad = dict(item, value_text="99999")
    out2, _ = run_cands(
        world, [bad], doc=world.scan_doc, kind="page_read", page=1, line_range=None, question="b"
    )
    assert out2.state == "succeeded"
    assert rows(world)[-1]["state"] == "rejected"


def test_quote_check_never_skipped_on_text_layer(world: World) -> None:
    """A text-layer page cannot use the image-only exemption: no quote means rejection."""
    no_quote = page_item(world.pdf_doc, 1, quote=None)
    wrong = page_item(world.pdf_doc, 1, quote="Subsea tree 5000 psi")
    out, _ = run_cands(
        world,
        [no_quote, wrong],
        doc=world.pdf_doc,
        kind="page_read",
        page=1,
        line_range=None,
    )
    assert out.state == "succeeded"
    first, second = rows(world)
    assert first["state"] == "rejected" and "quote_missing" in first["reasons"]
    assert second["state"] == "rejected" and "quote_not_in_span" in second["reasons"]
    assert first["method"] == "model_proposal" and second["method"] == "model_proposal"


def test_database_refuses_accepted_model_read(world: World) -> None:
    """The CHECK constraints are the last line of defence for AX-13."""
    run_cands(
        world, [_scan_item(world)], doc=world.scan_doc, kind="page_read", page=1, line_range=None
    )
    for sql in (
        "update extraction_candidate set state='accepted'",
        "update extraction_candidate set validation_state='valid'",
        "update extraction_candidate set method='model_proposal', state='accepted'",
        "update extraction_candidate set state='rejected', reason_codes='{}'",
        "update extraction_candidate set evidence_class='source_record'",
    ):
        with pytest.raises(IntegrityError):
            world.scalar(sql)


def test_model_read_not_in_calculations(world: World) -> None:
    """Calculation entry points reject the model-proposal marker."""
    marked = [
        {"event_id": "e1", "evidence_class": "model_proposal", "kind": "perforate"},
        {"event_id": "e2", "extraction_method": "model_read", "kind": "perforate"},
        {"event_id": "e3", "validation_state": "unverified", "kind": "perforate"},
        {"event_id": "e4", "method": "model_proposal", "kind": "perforate"},
    ]
    history = PerforationHistory.build(marked, wellbore_id="w1", md_datum="RKB")
    assert history.events == ()
    assert {r.code for r in history.rejections} == {MARKER_REASON}
    assert len(history.rejections) == 4
    # an unmarked (parsed) record is not touched by the guard (it fails for its own reasons)
    plain = PerforationHistory.build(
        [{"event_id": "p1", "kind": "perforate"}], wellbore_id="w1", md_datum="RKB"
    )
    assert MARKER_REASON not in {r.code for r in plain.rejections}
    assert is_model_proposal({"evidence_class": "model_proposal"})
    assert not is_model_proposal({"evidence_class": "source_record", "validation_state": "valid"})
    # a stored model-read candidate carries the marker its row exposes
    run_cands(
        world, [_scan_item(world)], doc=world.scan_doc, kind="page_read", page=1, line_range=None
    )
    row = world.rows("select evidence_class, method, validation_state from extraction_candidate")[0]
    marker = {"evidence_class": row[0], "extraction_method": row[1], "validation_state": row[2]}
    assert is_model_proposal(marker)
    assert PerforationHistory.build([{"event_id": "x", **marker}], wellbore_id="w", md_datum="RKB").events == ()

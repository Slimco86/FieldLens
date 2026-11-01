"""AX-1..AX-5: candidates are persisted with locators; validators decide, the model never does.
Offline stub provider, real PostgreSQL, synthetic documents."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fieldlens.candidates.harness import UnitRequest
from tests.candidates.conftest import SUBJECT, World
from tests.candidates.helpers import loc, meas, page_item, rows, run_cands
from tests.candidates.support import FixtureProvider, json_response


def test_candidates_persisted(world: World) -> None:
    """AX-1: table/unit class and page-image class persist typed candidates with locators."""
    cands = [
        meas(world),
        meas(world, attribute_key="perforation.base_md", value_text="4165.00", quote="4165.00"),
    ]
    out, provider = run_cands(world, cands)
    assert out.state == "succeeded" and out.candidates == {"accepted": 2}
    stored = rows(world)
    assert [r["state"] for r in stored] == ["accepted", "accepted"]
    first = stored[0]
    assert first["method"] == "model_proposal" and first["validation_state"] == "valid"
    attrs = json.loads(first["attributes"])
    assert attrs["kind"] == "measurement" and attrs["unit_as_written"] == "m"
    assert attrs["value_text"] == "4160.00" and attrs["normalized_number"] == 4160.0
    loc_ = json.loads(first["locator"])
    assert loc_["kind"] == "text" and loc_["line_start"] == 2
    assert first["wellbore_id"] is not None  # attached to the project wellbore identity
    # the locator resolves to the source span and the quote is in it
    doc = world.reader.require(world.project_id, world.revision_id, world.perf_doc)
    span = world.reader.read_lines(doc, loc_["line_start"], loc_["line_end"])
    assert first["quote"] in span.text
    # model, prompt and version ids and usage are recorded
    ids = world.rows("select model_id, prompt_version, harness_version from extraction_candidate")
    assert ids[0] == ("stub-model-1", "ax-prompt-1", "extract-1")
    unit = world.rows("select input_tokens, output_tokens, cost_usd, state from agent_work_unit")
    assert unit[0][0] == 1200 and unit[0][1] == 300 and unit[0][2] > 0 and unit[0][3] == "succeeded"
    assert len(provider.calls) == 1

    # page-image class on a text-layer PDF page (quote verified against the layer)
    out2, _ = run_cands(
        world,
        [page_item(world.pdf_doc, 1)],
        doc=world.pdf_doc,
        kind="page_read",
        page=1,
        line_range=None,
    )
    assert out2.state == "succeeded" and out2.candidates == {"accepted": 1}
    last = rows(world)[-1]
    assert json.loads(last["attributes"])["kind"] == "page_read"
    assert json.loads(last["locator"])["kind"] == "pdf"


BAD: list[tuple[str, dict[str, Any], str]] = [
    ("locator_doc", {"locator": {"document_id": "00000000-0000-0000-0000-00000000dead", "line_start": 2, "line_end": 2}}, "locator_not_found"),
    ("locator_range", {"locator": {"line_start": 900, "line_end": 901}}, "locator_not_found"),
    ("quote_not_in_span", {"quote": "9999.99"}, "quote_not_in_span"),
    ("quote_missing", {"quote": None}, "quote_missing"),
    ("value_not_in_quote", {"quote": "Hugin Fm."}, "value_not_in_quote"),
    ("unit_unparseable", {"unit": "furlongs"}, "unit_unparseable"),
    ("unit_dimension", {"unit": "psi"}, "unit_dimension_mismatch"),
    ("attribute_unknown", {"attribute_key": "foo.bar"}, "attribute_unknown"),
    ("md_as_tvd", {"depth_reference": "TVD"}, "md_tvd_confusion"),
    ("date_invented", {"effective_time_text": "1999-01-01"}, "date_not_in_source"),
]


@pytest.mark.parametrize(("name", "over", "reason"), BAD, ids=[b[0] for b in BAD])
def test_validators_reject(world: World, name: str, over: dict[str, Any], reason: str) -> None:
    """AX-2: each defect is rejected with a machine-readable reason; nothing becomes accepted."""
    over = dict(over)
    if "locator" in over and "document_id" not in over["locator"]:
        over["locator"] = {"document_id": str(world.perf_doc), **over["locator"]}
    out, _ = run_cands(world, [meas(world, **over)])
    assert out.state == "succeeded"  # the attempt worked; the candidate did not
    (row,) = rows(world)
    assert row["state"] == "rejected" and row["validation_state"] == "invalid", name
    assert reason in row["reasons"]
    assert world.scalar("select count(*) from extraction_candidate where state='accepted'") == 0


def test_validators_reject_out_of_range_and_compound(world: World) -> None:
    """Range (an OD of 3,605 m) and the MD/TVD compound pair (TASK-042 failure mode 2)."""
    out, _ = run_cands(
        world,
        [
            {
                "kind": "measurement",
                "attribute_key": "tubing.od",
                "value_text": "3605",
                "unit": "m",
                "quote": "Perforation top 3605 m",
                "locator": loc(world.pdf_doc, page=2),
                "subject": SUBJECT,
            },
            {
                "kind": "measurement",
                "attribute_key": "liner.top_md",
                "value_text": "3095/2742",
                "unit": "m",
                "quote": "Liner hanger 3095/2742 m MD/TVD",
                "locator": loc(world.pdf_doc, page=2),
                "subject": SUBJECT,
            },
        ],
        doc=world.pdf_doc,
        page=2,
        line_range=None,
    )
    assert out.state == "succeeded"
    stored = rows(world)
    assert "out_of_range" in stored[0]["reasons"] and stored[0]["state"] == "rejected"
    assert stored[1]["state"] == "rejected" and "compound_depth_pair" in stored[1]["reasons"]


def test_no_override_of_parsed(world: World) -> None:
    """AX-3: a disagreement with the parsed value is flagged; the parsed record is unchanged."""
    before = world.rows("select record_id, attributes::text from extracted_record order by 1")
    wrong = meas(world, value_text="4165.00", quote="4165.00")  # base MD claimed as top MD
    out, _ = run_cands(world, [wrong])
    assert out.state == "succeeded"
    (row,) = rows(world)
    assert row["state"] == "flagged" and "parsed_conflict" in row["reasons"]
    assert row["validation_state"] == "conflicting" and row["conflict"] is not None
    after = world.rows("select record_id, attributes::text from extracted_record order by 1")
    assert after == before  # the parsed value stays authoritative and unchanged
    assert world.scalar("select count(*) from extraction_candidate where state='accepted'") == 0
    # an agreeing proposal on the same line is accepted
    out2, _ = run_cands(world, [meas(world)], question="top md?")
    assert out2.candidates == {"accepted": 1}


def test_identity_and_reference_rules(world: World) -> None:
    """AX-5: unresolved subjects stay unattached; wrong-folder keeps the document's subject;
    MD is never TVD; no CRS, date or unit is invented."""
    # unknown wellbore and missing subject stay unattached and flagged
    out, _ = run_cands(
        world,
        [
            meas(world, subject={"wellbore_label": "15/9-F-77"}),
            meas(world, subject={}, attribute_key="perforation.base_md", value_text="4165.00", quote="4165.00"),
        ],
    )
    assert out.state == "succeeded"
    unresolved = rows(world)
    assert all(r["state"] == "flagged" and r["wellbore_id"] is None for r in unresolved)
    assert all("subject_unresolved" in r["reasons"] for r in unresolved)

    # an unqualified alias that is unique resolves to the qualified project wellbore
    out2, _ = run_cands(world, [meas(world, subject={"wellbore_label": "F-99"})], question="alias")
    assert out2.candidates == {"accepted": 1}

    # wrong folder / cross-well: perf98.dat's own records name F-98; the claim of F-99 is flagged
    cross = meas(world, locator=loc(world.perf98_doc), quote="3900.00", value_text="3900.00")
    out3, _ = run_cands(world, [cross], doc=world.perf98_doc, question="cross")
    assert out3.state == "succeeded"
    row = rows(world)[-1]
    assert row["state"] == "flagged" and "subject_document_mismatch" in row["reasons"]
    assert row["wellbore_id"] is None
    assert "15/9-F-98" in row["validators"]  # the document's actual subject is kept in the finding

    # MD is never TVD: the quote says TVD for an MD key, and a TVD key given an MD reference
    out4, _ = run_cands(
        world,
        [
            meas(world, quote="2772.90", value_text="2772.90", attribute_key="perforation.top_md"),
            meas(
                world,
                quote="2772.90",
                value_text="2772.90",
                attribute_key="perforation.top_tvd",
                depth_reference="MD",
            ),
        ],
        question="md vs tvd",
    )
    assert out4.state == "succeeded"
    tail = rows(world)[-2:]
    assert tail[1]["state"] == "rejected" and "md_tvd_confusion" in tail[1]["reasons"]

    # unit defaulted to meters is a warning, never a block, and is marked as defaulted
    out5, _ = run_cands(world, [meas(world, unit=None)], question="no unit")
    assert out5.candidates == {"accepted": 1}
    last = rows(world)[-1]
    assert json.loads(last["attributes"])["unit_defaulted"] is True
    assert "unit_defaulted_meters" in last["validators"]

    # the date is kept as written and must be in the quote
    out6, _ = run_cands(
        world,
        [meas(world, quote="2010-05-03", value_text="4160.00", effective_time_text="2010-05-03")],
        question="date",
    )
    assert out6.state == "succeeded"
    assert rows(world)[-1]["state"] == "rejected"  # value is not in that quote

    # no CRS is assumed: an easting without a stated CRS is flagged; with the stated CRS it passes
    east = {
        "kind": "measurement",
        "attribute_key": "wellhead.easting",
        "value_text": "478123.5",
        "unit": "m",
        "quote": "Easting 478123.5 m",
        "locator": loc(world.pdf_doc, page=4),
        "subject": SUBJECT,
    }
    out7, _ = run_cands(
        world,
        [east, {**east, "crs_text": "ED50 / UTM zone 31N", "value_text": "478123.5"}],
        doc=world.pdf_doc,
        page=4,
        line_range=None,
        question="coords",
    )
    assert out7.state == "succeeded"
    a, b = rows(world)[-2:]
    # the page text itself states the CRS, so both are decided on the stated reference only
    assert b["state"] == "accepted"
    assert a["state"] == "flagged" and "crs_not_stated" in a["reasons"]


def test_unit_request_ignores_filename_and_category_hints(world: World) -> None:
    """Upload categories/filenames are hints, not evidence: nothing of them reaches the prompt."""
    provider = FixtureProvider(lambda req, n: json_response([]))
    h = world.harness(provider)
    h.run_unit(
        UnitRequest(world.project_id, world.revision_id, world.perf_doc, "q", "measurement",
                    line_range=(1, 2))
    )
    text = json.dumps(
        [p.model_dump(mode="json") for m in provider.calls[0].messages for p in m.parts],
        default=str,
    )
    assert "perf.dat" not in text and "completion_equipment" not in text

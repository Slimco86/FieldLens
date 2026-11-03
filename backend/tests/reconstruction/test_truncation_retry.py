"""TASK-084: S3 runs at low effort, retry a truncated call once (larger bound, minimal effort)
inside the same ledger unit, and record real tokens and USD even when the stage fails."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fieldlens.assistant.messages import Usage
from fieldlens.assistant.stub import text_response, truncated_response
from fieldlens.config import Settings
from fieldlens.reconstruction.matching import MatchWellboresExecutor
from fieldlens.reconstruction.stages import StageContext
from tests.merge_proposals.support import FakeSource, count, group, make_proposer, seed
from tests.retrieval.support import World

ALIAS_TEXT = "Daily report. Well F12 (Volve) is the same well as 15/9-F-12.\n"
TRUNC = Usage(input_tokens=700, output_tokens=4096)


def _ctx(world: World, pid: UUID, wb: UUID | None = None) -> StageContext:
    return StageContext(
        factory=world.factory,
        settings=Settings(),
        project_id=pid,
        run_id=uuid4(),
        well_id=uuid4(),
        wellbore_id=wb or uuid4(),
        wellbore_name="x",
        source_revision="r",
        previous={},
        checkpoint=lambda: None,
    )


def _s3(world: World, script: list[Any]) -> tuple[UUID, MatchWellboresExecutor, Any, UUID]:
    pid, docs = seed(world)
    source = FakeSource(world, {docs["alias"]: ALIAS_TEXT, docs["base"]: "wells"})
    proposer, provider = make_proposer(world, source, script)
    return UUID(pid), MatchWellboresExecutor(proposer), provider, docs["alias"]


def _answer(doc: UUID) -> Any:
    ev = [
        {
            "member": "m1",
            "document_id": str(doc),
            "quote": "Well F12 (Volve) is the same well as 15/9-F-12",
        }
    ]
    return text_response(
        group("b1", "t", ["m1"], ev), usage=Usage(input_tokens=900, output_tokens=120)
    )


def test_s3_truncated_once_then_answers(world: World) -> None:
    pid, ex, provider, alias = _s3(world, [])
    provider._script.extend(
        [truncated_response('{"groups":[', TRUNC), _answer(alias), text_response('{"groups":[]}')]
    )
    result = ex.run(_ctx(world, pid))
    assert result.state == "succeeded", result
    assert result.counts["proposed"] == 1
    assert count(world, "merge_proposal") == 1  # no duplicate proposals from the retry
    first, second = provider.calls[0], provider.calls[1]
    assert (first.effort, first.max_output_tokens) == ("low", 4096)
    assert (second.effort, second.max_output_tokens) == ("minimal", 8192)
    # both attempts are in the ONE reservation and both are counted
    assert count(world, "spend_reservation") == 1
    assert result.input_tokens == 700 + 900 and result.output_tokens == 4096 + 120
    assert result.usd > 0


def test_s3_truncated_twice_fails_with_tokens_usd_and_readable_message(world: World) -> None:
    pid, ex, provider, _ = _s3(world, [])
    provider._script.extend([truncated_response("{", TRUNC), truncated_response("{", TRUNC)])
    result = ex.run(_ctx(world, pid))
    assert result.state == "failed" and result.error_code == "output_truncated"
    assert "ran out of output space" in (result.message or "")
    assert "a retry was already attempted" in (result.message or "")
    assert result.input_tokens == 1400 and result.output_tokens == 8192
    assert result.usd > 0
    assert len(provider.calls) == 2 and count(world, "spend_reservation") == 1
    assert count(world, "merge_proposal") == 0

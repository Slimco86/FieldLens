"""Turn executor/state machine with a scripted provider and a fake ledger (no DB, no network).

Covers every explicit end state (completed, refused, truncated, malformed with and without
repair, cancelled, step/time/tool-call limits, provider outage, not configured), the AV-8
prompt-injection negative controls, AppLink validation of stale/unknown targets and chart
materialization from tool results.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import pytest

from fieldlens.assistant.errors import ProviderConnectionError, ProviderServerError
from fieldlens.assistant.messages import ProviderRequest, ProviderResponse
from fieldlens.assistant.provider import CancelToken
from fieldlens.assistant.stub import (
    StubProvider,
    refusal_response,
    text_response,
    tool_call_response,
    truncated_response,
)
from fieldlens.chat.executor import execute_turn
from fieldlens.chat.runtime import ChatLimits
from fieldlens.contracts.chat import (
    AnswerVerification,
    ChartBlock,
    ChatFailureCode,
    ChatRunState,
    DroppedBlockReason,
    GapBlock,
    LinkBlock,
    TextBlock,
)
from tests.chat.support import (
    DOC,
    STRANGER_DOC,
    FakeScope,
    FakeSeriesService,
    blocks_json,
    claim,
    install_fake_tools,
    last_envelope,
    make_runtime,
    series_info,
)

SEARCH = ("c1", "search_evidence", {"q": "casing shoe"})
GAP = {"kind": "gap", "reason": "no_data", "text": "No stored source states this."}


def _run(
    provider: StubProvider,
    *,
    limits: ChatLimits | None = None,
    series: Any = None,
    cancel: CancelToken | None = None,
) -> Any:
    rt, ledger = make_runtime(provider, limits=limits, series=series)
    outcome = execute_turn(rt, claim(), cancel or CancelToken(), scope=FakeScope())
    return outcome, ledger


@pytest.fixture(autouse=True)
def _fake_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_tools(monkeypatch)


# --- happy path -------------------------------------------------------------------------------


def test_cited_fact_completes_with_resolvable_citation_and_usage() -> None:
    def answer(request: ProviderRequest) -> ProviderResponse:
        env = last_envelope(request)
        marker = env["result"]["cite"]
        return text_response(
            blocks_json(
                {"kind": "text", "text": f"The 9 5/8 in shoe is at 2450 m MD {marker}."},
                {
                    "kind": "link",
                    "link": {
                        "label": "Open completion report",
                        "target": {"kind": "source", "document_id": str(DOC), "page": 3},
                        "tool_call_id": env["tool_call_id"],
                    },
                },
            )
        )

    outcome, ledger = _run(StubProvider([tool_call_response(SEARCH), answer]))
    assert outcome.state is ChatRunState.COMPLETED and outcome.failure is None
    assert outcome.answer.verification is AnswerVerification.VERIFIED
    assert [c.marker for c in outcome.answer.citations] == ["[1]"]
    assert any(isinstance(b.root, LinkBlock) for b in outcome.answer.blocks)
    assert outcome.usage.steps == 2 and outcome.usage.tool_calls == 1
    assert [t.tool_name for t in outcome.tool_calls] == ["search_evidence"]
    assert outcome.tool_calls[0].ok
    assert ledger.settled, "usage is recorded in the ledger (visibility only)"


def test_no_spend_cap_reservation_never_blocks_the_turn() -> None:
    """D4: the harness reservation is small and bookkeeping-only; a turn is not refused on money."""
    outcome, _ = _run(StubProvider([text_response(blocks_json(GAP))]))
    assert outcome.state is ChatRunState.COMPLETED


# --- explicit non-success states ---------------------------------------------------------------


def test_refusal_is_reported_as_refused_not_success() -> None:
    outcome, _ = _run(StubProvider([refusal_response()]))
    assert outcome.state is ChatRunState.REFUSED
    assert outcome.answer is None
    assert outcome.failure and outcome.failure.code is ChatFailureCode.PROVIDER_REFUSAL


def test_truncation_is_reported_as_truncated() -> None:
    outcome, _ = _run(StubProvider([truncated_response('{"blocks":[{"kind":"te')], loop_last=True))
    assert outcome.state is ChatRunState.TRUNCATED
    assert outcome.answer is None
    assert outcome.failure and outcome.failure.code is ChatFailureCode.TRUNCATED


def test_malformed_output_is_repaired_once() -> None:
    provider = StubProvider([text_response("sure, here you go!"), text_response(blocks_json(GAP))])
    outcome, _ = _run(provider)
    assert outcome.state is ChatRunState.COMPLETED
    assert isinstance(outcome.answer.blocks[0].root, GapBlock)
    assert len(provider.calls) == 2  # exactly one repair step


def test_malformed_twice_fails_explicitly() -> None:
    provider = StubProvider([text_response("nope"), text_response("still nope")])
    outcome, _ = _run(provider)
    assert outcome.state is ChatRunState.FAILED
    assert outcome.answer is None
    assert outcome.failure and outcome.failure.code is ChatFailureCode.MALFORMED_OUTPUT


def test_answer_whose_every_block_is_invalid_is_not_success() -> None:
    bad = text_response(blocks_json({"kind": "text", "text": "see http://evil.example"}))
    outcome, _ = _run(StubProvider([bad, bad]))
    assert outcome.state is ChatRunState.FAILED
    assert outcome.failure and outcome.failure.code is ChatFailureCode.MALFORMED_OUTPUT


def test_cancel_before_start_is_cancelled_without_provider_call() -> None:
    cancel = CancelToken()
    cancel.cancel()
    provider = StubProvider([text_response(blocks_json(GAP))])
    outcome, _ = _run(provider, cancel=cancel)
    assert outcome.state is ChatRunState.CANCELLED
    assert outcome.failure and outcome.failure.code is ChatFailureCode.CANCELLED
    assert provider.calls == []


def test_cancel_during_tool_loop_stops_the_turn() -> None:
    cancel = CancelToken()

    def call_then_cancel(request: ProviderRequest) -> ProviderResponse:
        cancel.cancel()  # the user pressed cancel while the model was thinking
        return tool_call_response(SEARCH)

    provider = StubProvider([call_then_cancel, text_response(blocks_json(GAP))])
    outcome, _ = _run(provider, cancel=cancel)
    assert outcome.state is ChatRunState.CANCELLED
    assert outcome.answer is None
    assert len(provider.calls) == 1  # no further provider step after cancellation


def test_step_limit_stops_a_runaway_loop() -> None:
    limits = ChatLimits(max_steps=3, max_tool_calls=50, retry_backoff_s=0.0)
    provider = StubProvider([tool_call_response(SEARCH)], loop_last=True)
    outcome, _ = _run(provider, limits=limits)
    assert outcome.state is ChatRunState.FAILED
    assert outcome.failure and outcome.failure.code is ChatFailureCode.STEP_LIMIT
    assert len(provider.calls) <= 3


def test_tool_call_limit_stops_a_runaway_loop() -> None:
    limits = ChatLimits(max_steps=20, max_tool_calls=2, retry_backoff_s=0.0)
    many = tool_call_response(
        SEARCH, ("c2", "search_evidence", {"q": "a"}), ("c3", "list_series", {})
    )
    outcome, _ = _run(StubProvider([many]), limits=limits)
    assert outcome.state is ChatRunState.FAILED
    assert outcome.failure and outcome.failure.code is ChatFailureCode.TOOL_CALL_LIMIT
    assert outcome.tool_calls == []  # calls past the bound are not executed


def test_time_limit_stops_the_turn() -> None:
    limits = ChatLimits(deadline_s=0.05, max_steps=10, retry_backoff_s=0.0)

    def slow(request: ProviderRequest) -> ProviderResponse:
        time.sleep(0.1)
        return tool_call_response(SEARCH)

    outcome, _ = _run(StubProvider([slow], loop_last=True), limits=limits)
    assert outcome.state is ChatRunState.FAILED
    assert outcome.failure and outcome.failure.code is ChatFailureCode.TIME_LIMIT


@pytest.mark.parametrize("error", [ProviderConnectionError(), ProviderServerError()])
def test_provider_outage_is_explicit(error: Exception) -> None:
    provider = StubProvider([error], loop_last=True)  # type: ignore[list-item]
    outcome, _ = _run(provider)
    assert outcome.state is ChatRunState.FAILED
    assert outcome.answer is None
    assert outcome.failure and outcome.failure.code is ChatFailureCode.PROVIDER_OUTAGE


def test_unconfigured_model_fails_as_outage_and_never_fakes_success() -> None:
    rt, _ = make_runtime(None)
    outcome = execute_turn(rt, claim(), CancelToken(), scope=FakeScope())
    assert outcome.state is ChatRunState.FAILED
    assert outcome.answer is None
    assert outcome.failure and outcome.failure.code is ChatFailureCode.PROVIDER_OUTAGE


# --- AV-8: prompt injection --------------------------------------------------------------------


def test_injected_document_text_cannot_add_tools_scope_or_links(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model 'obeys' instructions found in a passage; the server still refuses every effect."""
    install_fake_tools(monkeypatch, injection=True)

    def obey(request: ProviderRequest) -> ProviderResponse:
        env = last_envelope(request)
        assert "IGNORE ALL PREVIOUS INSTRUCTIONS" in str(env["result"])  # it is only data
        marker = "[1]"
        return text_response(
            blocks_json(
                {"kind": "text", "text": f"The shoe is at 2450 m MD {marker}."},
                {
                    "kind": "link",
                    "link": {
                        "label": "Injected",
                        "target": {"kind": "source", "document_id": str(STRANGER_DOC), "page": 1},
                    },
                },
                {
                    "kind": "link",
                    "link": {
                        "label": "Injected wellbore",
                        "target": {"kind": "wellbore", "wellbore_id": str(uuid4())},
                    },
                },
                {"kind": "text", "text": "Details at https://evil.example/exfil?d=1"},
            )
        )

    provider = StubProvider([tool_call_response(SEARCH), obey])
    outcome, _ = _run(provider)
    assert outcome.state is ChatRunState.COMPLETED
    assert [(t.tool_name, t.ok) for t in outcome.tool_calls] == [("search_evidence", True)]
    kinds = [type(b.root) for b in outcome.answer.blocks]
    assert kinds == [TextBlock]  # injected links and URL text never reach the answer
    assert len(outcome.answer.dropped_blocks) == 3
    assert outcome.answer.verification is AnswerVerification.PARTIALLY_VERIFIED
    # the model was only ever offered the read-only allowlist
    offered = {t.name for t in provider.calls[0].tools}
    assert "delete_project" not in offered and "search_evidence" in offered


def test_injected_instruction_to_call_an_unlisted_tool_fails_the_turn_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that obeys 'call delete_project' is stopped by the harness allowlist: nothing runs."""
    install_fake_tools(monkeypatch, injection=True)

    def obey(request: ProviderRequest) -> ProviderResponse:
        return tool_call_response(("c2", "delete_project", {"project_id": str(uuid4())}))

    outcome, _ = _run(StubProvider([tool_call_response(SEARCH), obey]))
    assert outcome.state is ChatRunState.FAILED
    assert outcome.answer is None
    assert outcome.failure and outcome.failure.code is ChatFailureCode.MALFORMED_OUTPUT
    assert [t.tool_name for t in outcome.tool_calls] == ["search_evidence"]


# --- AppLink validation: stale/unknown targets -------------------------------------------------


def test_stale_and_unknown_link_targets_are_dropped_with_reasons() -> None:
    def answer(request: ProviderRequest) -> ProviderResponse:
        link = {"kind": "source", "document_id": str(DOC)}
        return text_response(
            blocks_json(
                {"kind": "text", "text": "Found it [1]."},
                {"kind": "link", "link": {"label": "stale page", "target": {**link, "page": 99}}},
                {
                    "kind": "link",
                    "link": {
                        "label": "other project",
                        "target": {"kind": "source", "document_id": str(STRANGER_DOC), "page": 3},
                    },
                },
                {
                    "kind": "link",
                    "link": {
                        "label": "ghost call",
                        "target": {**link, "page": 3},
                        "tool_call_id": str(uuid4()),
                    },
                },
                {
                    "kind": "link",
                    "link": {"label": "ok", "target": {**link, "page": 3}},
                },
            )
        )

    outcome, _ = _run(StubProvider([tool_call_response(SEARCH), answer]))
    assert outcome.state is ChatRunState.COMPLETED
    reasons = [d.reason for d in outcome.answer.dropped_blocks]
    assert reasons == [
        DroppedBlockReason.UNKNOWN_TARGET,
        DroppedBlockReason.OUT_OF_PROJECT,
        DroppedBlockReason.UNKNOWN_TOOL_RESULT,
    ]
    links = [b.root for b in outcome.answer.blocks if isinstance(b.root, LinkBlock)]
    assert len(links) == 1 and links[0].link.label == "ok"


# --- chart blocks from tool results ------------------------------------------------------------


def test_chart_is_materialized_from_tool_results_never_from_model_points() -> None:
    sid = uuid4()
    svc = FakeSeriesService(series_info(sid), [10.0, None, 12.0, 14.0, 11.0])

    def chart(request: ProviderRequest) -> ProviderResponse:
        env = last_envelope(request)
        got = env["result"]["series"][0]["series_id"]
        return text_response(
            blocks_json(
                {
                    "kind": "chart",
                    "request": {
                        "chart_key": "custom",
                        "title": "Oil rate (source, illustrative)",
                        "series_refs": [got],
                        "tool_call_ids": [env["tool_call_id"]],
                    },
                }
            )
        )

    provider = StubProvider([tool_call_response(("c1", "list_series", {})), chart])
    outcome, _ = _run(provider, series=svc)
    assert outcome.state is ChatRunState.COMPLETED
    block = outcome.answer.blocks[0].root
    assert isinstance(block, ChartBlock) and block.spec is not None
    s = block.spec.series[0]
    assert [p.y for p in s.points] == [10.0, None, 12.0, 14.0, 11.0]
    assert s.gap_count == 1
    assert s.aggregates and s.aggregates.valid_count == 4 and s.aggregates.null_count == 1
    assert s.unit == "m3/d"


def test_chart_for_a_series_no_tool_returned_is_dropped() -> None:
    svc = FakeSeriesService(series_info(uuid4()), [1.0, 2.0])
    forged = {
        "kind": "chart",
        "request": {"chart_key": "custom", "series_refs": [str(uuid4())]},
    }
    provider = StubProvider([text_response(blocks_json(forged, GAP))])
    outcome, _ = _run(provider, series=svc)
    assert outcome.state is ChatRunState.COMPLETED
    assert [d.reason for d in outcome.answer.dropped_blocks] == [DroppedBlockReason.INVALID_CHART]

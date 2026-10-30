"""MI-5: <=4 attempts, tool-call bound (default 6, configurable), deadline, output tokens, reserved cost, cancellation."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from fieldlens.assistant import errors
from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.messages import (
    ImagePart,
    Message,
    ProviderResponse,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from fieldlens.assistant.provider import CancelToken
from fieldlens.assistant.runner import RequestLimits
from fieldlens.assistant.stub import StubProvider, text_response, tool_call_response
from fieldlens.config import Settings
from tests.assistant_support import LOOKUP_TOOL, FakeClock, MakeUnit, user

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-page"


def _reads(n: int) -> list[object]:
    return [tool_call_response((f"c{i}", "read_page", {"page": i})) for i in range(n)]


def test_limits_default_to_mi5_and_tool_bound_is_configurable() -> None:
    defaults = RequestLimits.from_settings(Settings(_env_file=None))
    assert (defaults.max_attempts, defaults.max_tool_calls, defaults.deadline_s) == (4, 6, 90.0)
    assert (defaults.max_output_tokens, defaults.max_reserved_usd) == (4096, Decimal("0.50"))
    assert (
        RequestLimits.from_settings(
            Settings(_env_file=None, provider_max_tool_calls=10)
        ).max_tool_calls
        == 10
    )
    with pytest.raises(ValueError):
        Settings(_env_file=None, provider_max_attempts=5)  # bounds may only be lowered
    with pytest.raises(ValueError):
        Settings(_env_file=None, provider_max_tool_calls=0)


def test_default_tool_bound_stops_the_seventh_call_before_executing_it(make_unit: MakeUnit) -> None:
    # Three rounds of two calls each: 6 calls are allowed, the 7th/8th are not executed.
    rounds = [
        tool_call_response(("a1", "read_page", {"page": 1}), ("a2", "read_page", {"page": 2})),
        tool_call_response(("b1", "read_page", {"page": 3}), ("b2", "read_page", {"page": 4})),
        tool_call_response(("c1", "read_page", {"page": 5}), ("c2", "read_page", {"page": 6})),
        tool_call_response(("d1", "read_page", {"page": 7})),
    ]
    executed: list[str] = []
    stub = StubProvider(rounds, loop_last=True)
    with pytest.raises(errors.RequestLimitExceeded) as info:
        with make_unit(stub, tools=[LOOKUP_TOOL]) as unit:
            unit.run_tool_loop([user("go")], lambda call: executed.append(call.call_id) or "page")
    assert info.value.limit == "tool_calls" and len(executed) == 6 and unit.tool_calls == 6
    assert unit.closed is not None and unit.closed.tool_calls_used == 6


def test_configured_tool_bound_is_honoured(make_unit: MakeUnit) -> None:
    limits = RequestLimits(max_tool_calls=2, retry_backoff_s=0.0)
    stub = StubProvider([*_reads(3)], loop_last=True)
    executed: list[str] = []
    with pytest.raises(errors.RequestLimitExceeded):
        with make_unit(stub, tools=[LOOKUP_TOOL], limits=limits) as unit:
            unit.run_tool_loop([user("go")], lambda call: executed.append(call.call_id) or "x")
    assert len(executed) == 2


def test_tool_loop_round_trip_with_image_and_reasoning_replay(make_unit: MakeUnit) -> None:
    image = ImagePart.from_bytes("image/png", PNG)
    first = ProviderResponse(
        parts=(
            ReasoningPart(opaque="OPAQUE-1", item_id="rs_1"),
            ToolCallPart(call_id="call_1", name="read_page", arguments={"page": 2}),
        )
    )
    stub = StubProvider([first, text_response("done")])
    start = Message(role="user", parts=(TextPart(text="extract"), image))
    with make_unit(stub, tools=[LOOKUP_TOOL]) as unit:
        response, _ = unit.run_tool_loop([start], lambda call: "page two text")
    assert response.text() == "done" and unit.tool_calls == 1
    for request in stub.calls:  # the image part reaches both provider calls intact
        assert request.messages[0].parts[1] == image
    replayed = stub.calls[1].messages[1]
    assert (
        replayed.role == "assistant" and replayed.parts == first.parts
    )  # opaque reasoning replayed


def test_stub_default_echo_completes_a_tool_free_unit_with_images(make_unit: MakeUnit) -> None:
    image = ImagePart.from_bytes("image/png", PNG)
    with make_unit() as unit:
        response, history = unit.run_tool_loop(
            [Message(role="user", parts=(TextPart(text="read"), image))], lambda call: "unused"
        )
    assert image.sha256[:8] in response.text() and len(history) == 2


def test_tool_results_round_trip_ids(make_unit: MakeUnit) -> None:
    stub = StubProvider(
        [tool_call_response(("call_x", "read_page", {"page": 1})), text_response("done")]
    )
    with make_unit(stub, tools=[LOOKUP_TOOL]) as unit:
        response, history = unit.run_tool_loop([user("go")], lambda call: "page one")
    assert response.text() == "done"
    tool_message = history[2]
    assert tool_message.role == "tool"
    assert tool_message.parts == (ToolResultPart(call_id="call_x", content="page one"),)
    assert stub.calls[1].messages[-1] == tool_message  # the result reached the second request


def test_tool_failure_is_returned_as_error_result_not_raised(make_unit: MakeUnit) -> None:
    stub = StubProvider([tool_call_response(("c1", "read_page", {"page": 1})), text_response("ok")])

    def failing(_: object) -> str:
        raise RuntimeError("secret internal detail")

    with make_unit(stub, tools=[LOOKUP_TOOL]) as unit:
        _, history = unit.run_tool_loop([user("go")], failing)  # type: ignore[arg-type]
    result = history[2].parts[0]
    assert isinstance(result, ToolResultPart) and result.is_error and "secret" not in result.content


def test_attempt_bound_includes_the_retry(make_unit: MakeUnit) -> None:
    limits = RequestLimits(max_attempts=2, retry_backoff_s=0.0)
    stub = StubProvider([errors.ProviderRateLimited(), text_response("one"), text_response("two")])
    with make_unit(stub, limits=limits) as unit:
        assert unit.step([user("a")]).text() == "one"  # attempt 1 failed, attempt 2 succeeded
        with pytest.raises(errors.RequestLimitExceeded) as info:
            unit.step([user("b")])
    assert info.value.limit == "attempts" and len(stub.calls) == 2


def test_four_attempts_is_the_ceiling(make_unit: MakeUnit) -> None:
    stub = StubProvider([], loop_last=False)
    with make_unit(stub) as unit:
        unit.attempts = 4
        with pytest.raises(errors.RequestLimitExceeded):
            unit.step([user("x")])
    assert stub.calls == []


def test_deadline_is_enforced(make_unit: MakeUnit) -> None:
    clock = FakeClock()
    stub = StubProvider([text_response("late")])
    with make_unit(stub, clock=clock) as unit:
        clock.advance(91)
        with pytest.raises(errors.RequestLimitExceeded) as info:
            unit.step([user("x")])
    assert info.value.limit == "deadline" and stub.calls == []


def test_retry_does_not_wait_past_the_deadline(make_unit: MakeUnit) -> None:
    clock = FakeClock()
    failure = errors.ProviderRateLimited(retry_after_s=30)
    stub = StubProvider([failure, text_response("late")])
    limits = RequestLimits(deadline_s=10, retry_backoff_s=0.0)
    with pytest.raises(errors.ProviderRateLimited):
        with make_unit(stub, clock=clock, limits=limits) as unit:
            unit.step([user("x")])
    assert len(stub.calls) == 1


def test_request_carries_the_output_token_bound(make_unit: MakeUnit) -> None:
    stub = StubProvider([text_response("ok")])
    with make_unit(stub) as unit:
        unit.step([user("x")])
    assert stub.calls[0].max_output_tokens == 4096


def test_reserved_cost_ceiling_blocks_dispatch(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    huge = "x" * 400_000  # ~400k input tokens at USD 1/Mtok = 0.40 + output bound 0.016
    stub = StubProvider([text_response("ok", None), text_response("never")])
    with make_unit(stub) as unit:
        unit.step([user(huge)])  # fits within USD 0.50
        with pytest.raises(errors.RequestLimitExceeded) as info:
            unit.step([user(huge)])  # missing usage kept the estimate as liability: no headroom
    assert info.value.limit == "reserved_cost" and len(stub.calls) == 1
    assert ledger.status(period).committed_usd < Decimal("0.50")


def test_oversized_single_request_is_refused_before_dispatch(make_unit: MakeUnit) -> None:
    stub = StubProvider([text_response("never")])
    with pytest.raises(errors.RequestLimitExceeded):
        with make_unit(stub) as unit:
            unit.step([user("x" * 600_000)])
    assert stub.calls == [] and unit.closed is not None and unit.closed.state == "released"


def test_cancel_before_start_prevents_reservation_and_calls(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    token = CancelToken()
    token.cancel()
    stub = StubProvider()
    with pytest.raises(errors.RequestCancelled):
        with make_unit(stub, cancel=token):
            pass
    assert stub.calls == [] and ledger.status(period).committed_usd == 0


def test_cancel_between_steps_prevents_next_call_and_releases_reservation(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    token = CancelToken()
    stub = StubProvider()
    with pytest.raises(errors.RequestCancelled):
        with make_unit(stub, cancel=token) as unit:
            token.cancel()
            unit.step([user("x")])
    assert stub.calls == []
    assert unit.closed is not None and unit.closed.state == "released"
    assert ledger.status(period).committed_usd == 0


def test_cancel_during_a_call_discards_the_answer_but_keeps_the_usage(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    token = CancelToken()

    def cancelling(_: object) -> ProviderResponse:
        token.cancel()
        return text_response("answer", None)

    stub = StubProvider([cancelling])
    with pytest.raises(errors.RequestCancelled):
        with make_unit(stub, cancel=token) as unit:
            unit.step([user("x")])
    assert len(stub.calls) == 1
    assert unit.closed is not None and unit.closed.state == "liable"  # dispatched: liability kept
    assert ledger.status(period).committed_usd > 0


def test_cancel_in_tool_loop_stops_before_the_next_provider_call(make_unit: MakeUnit) -> None:
    token = CancelToken()
    stub = StubProvider([*_reads(3)], loop_last=True)

    def executor(_: object) -> str:
        token.cancel()
        return "x"

    with pytest.raises(errors.RequestCancelled):
        with make_unit(stub, tools=[LOOKUP_TOOL], cancel=token) as unit:
            unit.run_tool_loop([user("go")], executor)  # type: ignore[arg-type]
    assert len(stub.calls) == 1


def test_model_must_match_pricing(make_unit: MakeUnit) -> None:
    with pytest.raises(errors.ProviderUnavailable):
        make_unit(model="other-model")


def _db_tool_calls(engine: Engine, rid: UUID) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                text("SELECT tool_calls_used FROM spend_reservation WHERE reservation_id = :r"),
                {"r": rid},
            ).scalar_one()
        )


def test_tool_calls_are_persisted_per_call_even_if_the_round_is_cancelled(
    make_unit: MakeUnit, engine: Engine
) -> None:
    token = CancelToken()
    stub = StubProvider(
        [tool_call_response(("a", "read_page", {"page": 1}), ("b", "read_page", {"page": 2}))]
    )
    seen: list[int] = []

    def executor(call: object) -> str:
        seen.append(1)
        token.cancel()  # cancel mid-round: the second call is never executed
        return "x"

    with pytest.raises(errors.RequestCancelled):
        with make_unit(stub, tools=[LOOKUP_TOOL], cancel=token) as unit:
            unit.run_tool_loop([user("go")], executor)  # type: ignore[arg-type]
    assert unit.reservation is not None and len(seen) == 1
    assert _db_tool_calls(engine, unit.reservation.reservation_id) == unit.tool_calls == 1


def test_reentering_a_reservation_resumes_persisted_counters(
    make_unit: MakeUnit, engine: Engine
) -> None:
    stub = StubProvider([tool_call_response(("a", "read_page", {"page": 1})), text_response("ok")])
    with make_unit(stub, tools=[LOOKUP_TOOL], request_key="resume") as unit:
        unit.run_tool_loop([user("go")], lambda _: "x")  # type: ignore[arg-type,return-value]
    assert unit.attempts == 2 and unit.tool_calls == 1
    again = make_unit(StubProvider([]), tools=[LOOKUP_TOOL], request_key="resume")
    with again as unit2:
        assert unit2.attempts == 2 and unit2.tool_calls == 1

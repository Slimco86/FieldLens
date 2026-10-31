"""TASK-043: effort control, tool-aware input bound, cancel settlement, 4xx non-billable, reconcile.

Offline only: stub/fixture payloads; the MI-6 figures below are recorded live facts, not calls.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import httpx
import openai
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.assistant import errors
from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.messages import (
    Message,
    ProviderRequest,
    ProviderResponse,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    ToolSpec,
    Usage,
)
from fieldlens.assistant.meta import build_responses_payload, map_sdk_error
from fieldlens.assistant.provider import (
    CancelToken,
    Pricing,
    attempt_upper_bound_usd,
    estimate_input_tokens,
    load_pricing,
)
from fieldlens.assistant.runner import RequestLimits
from fieldlens.assistant.stub import (
    RecordingProvider,
    ReplayProvider,
    StubProvider,
    text_response,
)
from tests.assistant_support import MODEL, PRICING, MakeUnit, user

# -- 1. effort -----------------------------------------------------------------------------------


def _req(**kw: object) -> ProviderRequest:
    return ProviderRequest(model=MODEL, messages=(user("hi"),), **kw)  # type: ignore[arg-type]


def test_effort_default_is_omitted_and_fingerprint_is_backward_compatible() -> None:
    plain = _req()
    assert plain.effort is None
    assert "reasoning" not in build_responses_payload(plain)
    explicit = _req(effort="low")
    assert build_responses_payload(explicit)["reasoning"] == {"effort": "low"}
    assert plain.fingerprint() != explicit.fingerprint()
    assert _req(effort="low").fingerprint() != _req(effort="minimal").fingerprint()


@pytest.mark.parametrize("effort", ["minimal", "low", "medium", "high"])
def test_effort_values_reach_the_payload(effort: str) -> None:
    assert build_responses_payload(_req(effort=effort))["reasoning"] == {"effort": effort}


def test_unknown_effort_is_rejected() -> None:
    with pytest.raises(ValueError):
        _req(effort="extreme")


def test_work_unit_default_step_override_and_stub_records_effort(make_unit: MakeUnit) -> None:
    stub = StubProvider()
    with make_unit(stub, limits=RequestLimits(retry_backoff_s=0.0, default_effort="low")) as unit:
        unit.step([user("a")])
        unit.step([user("b")], effort="minimal")
    assert [c.effort for c in stub.calls] == ["low", "minimal"]
    stub2 = StubProvider()
    with make_unit(stub2, effort="medium") as unit2:  # per-unit choice beats the limits default
        unit2.step([user("a")])
    assert [c.effort for c in stub2.calls] == ["medium"]
    stub3 = StubProvider()
    with make_unit(stub3) as unit3:  # nothing chosen: provider default (unset)
        unit3.step([user("a")])
    assert stub3.calls[0].effort is None


def test_recording_and_replay_keep_the_requested_effort() -> None:
    cancel = CancelToken()
    recorder = RecordingProvider(StubProvider([text_response("x"), text_response("y")]))
    recorder.complete(_req(effort="low"), timeout_s=1, cancel=cancel)
    recorder.complete(_req(), timeout_s=1, cancel=cancel)
    assert [r["effort"] for r in recorder.recordings] == ["low", None]
    replay = ReplayProvider(recorder.recordings)
    assert replay.complete(_req(effort="low"), timeout_s=1, cancel=cancel).text() == "x"
    assert replay.calls[0].effort == "low"
    with pytest.raises(errors.ReplayMiss):  # a different effort is a different request
        replay.complete(_req(effort="minimal"), timeout_s=1, cancel=cancel)


# -- 2. input-token estimate ---------------------------------------------------------------------

# MI-6 live facts (muse-spark-1.3): a one-tool request estimated 245 billed 552 input tokens;
# the follow-up step (tool result + two replayed reasoning items) billed 992.
MI6_ONE_TOOL_OLD_ESTIMATE, MI6_ONE_TOOL_BILLED, MI6_FOLLOWUP_BILLED = 245, 552, 992
MI6_TOOL = ToolSpec(
    name="lookup_code",
    description="Return the secret code for a named label.",
    parameters={
        "type": "object",
        "properties": {"label": {"type": "string"}},
        "required": ["label"],
    },
)
MI6_PROMPT = Message(
    role="user",
    parts=(TextPart(text="Call lookup_code with label 'alpha', then state the code it returns."),),
)


def _mi6_first() -> ProviderRequest:
    return ProviderRequest(model=MODEL, messages=(MI6_PROMPT,), tools=(MI6_TOOL,))


def _mi6_followup(opaque: str) -> ProviderRequest:
    call = ToolCallPart(call_id="call_1", name="lookup_code", arguments={"label": "alpha"})
    return ProviderRequest(
        model=MODEL,
        tools=(MI6_TOOL,),
        messages=(
            MI6_PROMPT,
            Message(
                role="assistant",
                parts=(
                    ReasoningPart(opaque=opaque, item_id="rs_1"),
                    ReasoningPart(opaque=opaque, item_id="rs_2"),
                    call,
                ),
            ),
            Message(role="tool", parts=(ToolResultPart(call_id="call_1", content="code=4417"),)),
        ),
    )


def test_one_tool_request_bound_covers_the_billed_552() -> None:
    # Bytes-only counting reproduces the evidence under-count (245), the new bound does not.
    assert estimate_input_tokens(_mi6_first(), 8192) >= MI6_ONE_TOOL_BILLED
    legacy = len(
        json.dumps(MI6_TOOL.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    )
    assert legacy + len(MI6_PROMPT.parts[0].text.encode()) + 4 < MI6_ONE_TOOL_BILLED  # type: ignore[union-attr]


@pytest.mark.parametrize("opaque_len", [1, 40, 400, 4000])
def test_followup_bound_covers_the_billed_992_whatever_the_opaque_size(opaque_len: int) -> None:
    assert estimate_input_tokens(_mi6_followup("a" * opaque_len), 8192) >= MI6_FOLLOWUP_BILLED


def test_reservation_covers_measured_tool_steps_via_the_cost_bound() -> None:
    for request, billed in (
        (_mi6_first(), MI6_ONE_TOOL_BILLED),
        (_mi6_followup("a" * 40), MI6_FOLLOWUP_BILLED),
    ):
        bound = attempt_upper_bound_usd(request, PRICING, 8192)
        billed_usd = (
            Decimal(billed) * PRICING.input_usd_per_mtok
            + Decimal(request.max_output_tokens) * PRICING.output_usd_per_mtok
        ) / Decimal(1_000_000)
        assert bound >= billed_usd


def test_text_only_and_image_bounds_are_unchanged() -> None:
    from fieldlens.assistant.messages import ImagePart

    assert estimate_input_tokens(_req(), 8192) == 4 + len(b"hi")
    img = ProviderRequest(
        model=MODEL,
        messages=(Message(role="user", parts=(ImagePart.from_bytes("image/png", b"x" * 9),)),),
    )
    assert estimate_input_tokens(img, 8192) == 4 + 8192


# -- 3. cancel semantics -------------------------------------------------------------------------


def test_cancel_in_flight_settles_actual_usage_then_raises(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID, engine: Engine
) -> None:
    token = CancelToken()
    usage = Usage(input_tokens=19, cached_input_tokens=0, output_tokens=757)  # MI-6 cancel case

    def cancelling(_: object) -> ProviderResponse:
        token.cancel()  # the in-flight call is not aborted; it completes and bills
        return text_response("pong", usage)

    with pytest.raises(errors.RequestCancelled) as caught:
        with make_unit(StubProvider([cancelling]), cancel=token) as unit:
            unit.step([user("x")])
    assert caught.value.settled is True
    assert unit.closed is not None and unit.closed.state == "settled"  # not liable
    expected = (
        Decimal(19) * PRICING.input_usd_per_mtok + Decimal(757) * PRICING.output_usd_per_mtok
    ) / Decimal(1_000_000)
    assert unit.closed.committed_usd == expected.quantize(
        Decimal("0.000001"), rounding="ROUND_CEILING"
    )
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, billed_usd, output_tokens FROM provider_attempt")
        ).all()
    assert any(r.status == "completed" and r.output_tokens == 757 and r.billed_usd > 0 for r in row)


def test_cancel_before_dispatch_is_not_settled_and_bills_nothing() -> None:
    assert errors.RequestCancelled().settled is False


# -- 4. non-billable 4xx and liable reconciliation ------------------------------------------------


def _status_error(code: int) -> openai.APIStatusError:
    request = httpx.Request("POST", "https://example.invalid/v1/responses")
    response = httpx.Response(code, request=request, headers={})
    return openai.APIStatusError("x", response=response, body=None)


@pytest.mark.parametrize("code", [400, 404, 405, 413, 422])
def test_rejected_4xx_maps_to_non_chargeable(code: int) -> None:
    err = map_sdk_error(_status_error(code))
    assert isinstance(err, errors.ProviderRejected) and not err.chargeable
    assert isinstance(err, errors.ProviderMalformed) and not err.retryable


@pytest.mark.parametrize("code", [408, 409])
def test_ambiguous_4xx_stays_chargeable(code: int) -> None:
    err = map_sdk_error(_status_error(code))
    assert err.chargeable and not isinstance(err, errors.ProviderRejected)


def test_5xx_and_timeout_stay_chargeable() -> None:
    assert map_sdk_error(_status_error(503)).chargeable
    assert map_sdk_error(
        openai.APITimeoutError(request=httpx.Request("POST", "http://x"))
    ).chargeable


def test_rejected_request_releases_instead_of_staying_liable(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    with pytest.raises(errors.ProviderRejected):
        with make_unit(StubProvider([errors.ProviderRejected("404")])) as unit:
            unit.step([user("x")])
    assert unit.closed is not None
    assert unit.closed.state == "settled" and unit.closed.committed_usd == 0
    assert unit.closed.reconciliation_status == "not_needed"
    assert ledger.status(period).committed_usd == 0
    assert ledger.list_liable(period) == []


def test_timeout_and_5xx_stay_liable(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    for failure in (errors.ProviderTimeout("t"), errors.ProviderServerError("s")):
        with pytest.raises(type(failure)):
            with make_unit(StubProvider([failure, failure])) as unit:
                unit.step([user("x")])
        assert unit.closed is not None and unit.closed.state == "liable"
    assert len(ledger.list_liable(period)) == 2


def test_release_liable_records_reason_and_is_idempotent(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID, engine: Engine
) -> None:
    with pytest.raises(errors.ProviderTimeout):
        with make_unit(StubProvider([errors.ProviderTimeout("t")])) as unit:
            unit.step([user("x")])
    assert unit.closed is not None
    rid = unit.closed.reservation_id
    with pytest.raises(errors.ReservationStateError):
        ledger.release_liable(rid, "Not A Slug!")
    out = ledger.release_liable(rid, "dashboard_not_billed")
    assert out.state == "settled" and out.committed_usd == 0
    assert out.reconciliation_status == "reconciled"
    assert ledger.release_liable(rid, "dashboard_not_billed") == out
    assert ledger.list_liable(period) == []
    with pytest.raises(errors.ReservationStateError):
        ledger.reconcile(rid, Decimal("0.01"))
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT error_code, billed_usd, reconciled FROM provider_attempt")
        ).one()
    assert row.error_code == "provider_timeout>dashboard_not_billed"
    assert row.billed_usd == 0 and row.reconciled is True


def test_reconcile_to_actual_usage_with_reason(
    make_unit: MakeUnit, ledger: BudgetLedger, period: UUID
) -> None:
    with pytest.raises(errors.ProviderServerError):
        with make_unit(StubProvider([errors.ProviderServerError("s")] * 2)) as unit:
            unit.step([user("x")])
    assert unit.closed is not None
    out = ledger.reconcile(unit.closed.reservation_id, Decimal("0.002"), reason="dashboard_actual")
    assert out.state == "settled" and out.committed_usd == Decimal("0.002")
    assert ledger.status(period).committed_usd == Decimal("0.002")


def test_liable_state_survives_restart_and_can_be_reconciled_after(
    factory: sessionmaker[Session], ledger: BudgetLedger, period: UUID, pricing_id: UUID
) -> None:
    res = ledger.reserve(period, "crash-1", Decimal("0.5"), pricing_id, work_unit="u")
    ledger.begin_attempt(
        res.reservation_id, provider="meta", model=MODEL, estimated_usd=Decimal("0.01")
    )  # process "dies" here: attempt dispatched, never finished
    restarted = BudgetLedger(factory)  # new ledger object = fresh process, same database
    closed = restarted.recover_interrupted(period)
    assert [r.state for r in closed] == ["liable"]
    again = BudgetLedger(factory)
    [liable] = again.list_liable(period)
    assert liable.reservation_id == res.reservation_id and liable.committed_usd == Decimal("0.01")
    assert again.status(period).committed_usd == Decimal("0.01")
    out = again.release_liable(res.reservation_id, "dashboard_not_billed")
    assert out.committed_usd == 0 and BudgetLedger(factory).list_liable(period) == []


# -- 5. pricing as data --------------------------------------------------------------------------


def test_pricing_loads_from_a_data_file(tmp_path: Path) -> None:
    card = tmp_path / "rates.json"
    card.write_text(
        json.dumps(
            {
                "revision": "synthetic-card-1",
                "model": MODEL,
                "input_usd_per_mtok": "1.5",
                "output_usd_per_mtok": 6,
                "cached_input_usd_per_mtok": None,
            }
        ),
        encoding="utf-8",
    )
    assert load_pricing(card) == Pricing(
        revision="synthetic-card-1",
        model=MODEL,
        input_usd_per_mtok=Decimal("1.5"),
        output_usd_per_mtok=Decimal("6"),
    )
    card.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pricing(card)

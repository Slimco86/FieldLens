"""MI-6: opt-in live Meta smoke. Spends real (capped) credit; never part of default runs.

Run only with explicit authorization:
``MODEL_API_KEY=... FIELDLENS_LIVE_META=1 uv run pytest backend/tests/assistant/test_meta_live_smoke.py -m live_meta``
Inputs are synthetic. The ledger period cap (USD 1.00) is enforced by the reservation code.
The sanitized result (ids, token counts, costs, error codes) is written to
``FIELDLENS_LIVE_META_OUT`` (default ``.local/fieldlens/live_meta_result.json``), never keys/prompts.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import threading
import time
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import openai
import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine

from fieldlens.assistant import errors
from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.messages import (
    ImagePart,
    Message,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolSpec,
)
from fieldlens.assistant.meta import MetaProvider
from fieldlens.assistant.provider import CancelToken, Pricing, scrub
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.config import Settings
from fieldlens.persistence.session import create_session_factory
from tests import live_meta_support as lms

pytestmark = pytest.mark.live_meta

CEILING = Decimal("1.00")
# Owner rates are not recorded anywhere; these deliberately high placeholders only make the
# reservation bound conservative. Costs below are therefore upper-bound estimates.
RATES = {"in": Decimal("5.00"), "out": Decimal("25.00")}
PHASE = os.environ.get("FIELDLENS_LIVE_META_PHASE", "main")  # "main" or "followup"
OUT = Path(
    os.environ.get("FIELDLENS_LIVE_META_OUT", f".local/fieldlens/live_meta_{PHASE}_result.json")
)


@pytest.fixture
def live_network() -> Iterator[None]:
    """Lift the default loopback-only guard for this one test, then restore it."""
    saved = [(o, n, getattr(o, n)) for o, n, _ in lms.GUARD_UNDO]
    for owner, name, original in lms.GUARD_UNDO:
        setattr(owner, name, original)
    try:
        yield
    finally:
        for owner, name, patched in saved:
            setattr(owner, name, patched)


def _pricing(model: str, tag: str) -> Pricing:
    return Pricing(
        revision=f"mi6-conservative-placeholder-1-{tag}",
        model=model,
        input_usd_per_mtok=RATES["in"],
        output_usd_per_mtok=RATES["out"],
    )


def _user(*parts: Any) -> Message:
    return Message(role="user", parts=tuple(parts))


def test_meta_live_smoke(live_network: None) -> None:
    key = lms.STASHED_KEY.get("key")
    problem = lms.live_opt_in_problem(os.environ, key)
    if problem:
        pytest.fail(problem, pytrace=False)
    assert key is not None
    settings = Settings(MODEL_API_KEY=key)  # type: ignore[call-arg]
    # The real environment may point at another database: read the lane .env explicitly.
    lane_url = dotenv_values(Path(".env")).get("FIELDLENS_DATABASE_URL") or ""
    assert "fieldlens_task_005" in lane_url, "use the lane database only"
    model = settings.meta_model
    engine = create_engine(lane_url)
    ledger = BudgetLedger(create_session_factory(engine))
    period = ledger.ensure_period(
        "mi6-live-smoke",
        ledger_cap_usd=CEILING,
        warn_usd=Decimal("0.80"),
        unattended_block_usd=CEILING,
    )
    with contextlib.suppress(errors.ReservationStateError):  # already confirmed on a rerun
        ledger.confirm_balance(period, CEILING, "MI-6 smoke allowance (owner ceiling USD 1)")
    pricing = _pricing(model, "main")
    pricing_id = ledger.register_pricing(
        pricing, "MI-6 conservative placeholder, not provider rates"
    )

    real = openai.OpenAI(api_key=key, base_url=settings.meta_base_url, max_retries=0, timeout=60.0)
    client = lms.CapturingClient(real)
    provider = MetaProvider(settings, client=client)
    run_id = str(int(time.time()))
    limits = RequestLimits(max_output_tokens=1024, retry_backoff_s=1.0)
    results: dict[str, Any] = {
        "base_url": settings.meta_base_url,
        "configured_model": model,
        "protocol": "responses",
        "ceiling_usd": str(CEILING),
        "pricing_revision": pricing.revision,
        "placeholder_rates_usd_per_mtok": {k: str(v) for k, v in RATES.items()},
        "limits": {
            "max_attempts": limits.max_attempts,
            "max_tool_calls": limits.max_tool_calls,
            "deadline_s": limits.deadline_s,
            "max_output_tokens": limits.max_output_tokens,
            "reserved_usd": str(limits.max_reserved_usd),
            "image_token_bound": limits.image_token_bound,
        },
        "steps": {},
    }

    def run(name: str, fn: Any, **unit_kw: Any) -> None:
        mark = len(client.captures)
        entry: dict[str, Any] = {}
        results["steps"][name] = entry
        unit_args: dict[str, Any] = {
            "provider": provider,
            "ledger": ledger,
            "period_id": period,
            "pricing_id": pricing_id,
            "pricing": pricing,
            "model": model,
            "request_key": f"mi6-{run_id}-{name}",
            "work_unit": f"mi6-{name}",
            "limits": limits,
        }
        unit_args.update(unit_kw)
        began = time.monotonic()
        unit: WorkUnit | None = None
        try:
            with WorkUnit(**unit_args) as unit:
                try:
                    entry["outcome"] = fn(unit, entry)
                except errors.AssistantError as exc:
                    entry["outcome"] = "typed_error"
                    entry["error_code"] = exc.code
                    entry["error_type"] = type(exc).__name__
                    entry["error_message"] = scrub(str(exc), [key])
                entry["attempts"] = unit.attempts
                entry["tool_calls"] = unit.tool_calls
        except errors.AssistantError as exc:  # reserve/guard failure before dispatch
            entry["outcome"] = "typed_error_before_dispatch"
            entry["error_code"] = exc.code
        entry["elapsed_s"] = round(time.monotonic() - began, 2)
        entry["raw_captures"] = client.captures[mark:]
        if unit is not None and unit.closed is not None:
            entry["committed_usd"] = str(unit.closed.committed_usd)
            entry["reservation_state"] = unit.closed.state
        status = ledger.status(period)
        entry["period_committed_usd_after"] = str(status.committed_usd)
        assert status.committed_usd <= CEILING

    if PHASE == "main":
        # 1. models list (GET, free) and plain text
        try:
            listing = real.models.list()
            results["models_listed"] = sorted(m.id for m in listing.data)[:50]
        except openai.OpenAIError as exc:
            results["models_listed_error"] = _sdk_shape(exc, key)

        def text(unit: WorkUnit, entry: dict[str, Any]) -> str:
            response = unit.step([_user(TextPart(text="Reply with exactly the single word: pong"))])
            entry["response_model"] = response.model
            entry["text_len"] = len(response.text())
            entry["text_head"] = response.text()[:80]
            entry["has_provider_request_id"] = bool(response.provider_request_id)
            entry["usage"] = response.usage.model_dump() if response.usage else None
            return "ok"

        run("text", text)

        # 2. tool round trip
        tool = ToolSpec(
            name="lookup_code",
            description="Return the secret code for a named label.",
            parameters={
                "type": "object",
                "properties": {"label": {"type": "string"}},
                "required": ["label"],
            },
        )

        def tool_round(unit: WorkUnit, entry: dict[str, Any]) -> str:
            seen: list[str] = []

            def executor(call: ToolCallPart) -> str:
                seen.append(call.name)
                return "code=4417"

            response, history = unit.run_tool_loop(
                [
                    _user(
                        TextPart(
                            text="Call lookup_code with label 'alpha', then state the code it returns."
                        )
                    )
                ],
                executor,
            )
            entry["tools_executed"] = seen
            entry["final_mentions_code"] = "4417" in response.text()
            entry["reasoning_parts_replayed"] = sum(
                isinstance(p, ReasoningPart) for m in history for p in m.parts
            )
            entry["history_roles"] = [m.role for m in history]
            return "ok"

        run("tool_round_trip", tool_round, tools=(tool,))

        # 3a. cancellation raised while the call is in flight: answer discarded, usage retained
        cancel = CancelToken()

        def cancel_late(unit: WorkUnit, entry: dict[str, Any]) -> str:
            threading.Timer(0.2, cancel.cancel).start()
            unit.step([_user(TextPart(text="Count from 1 to 40 separated by spaces."))])
            return "completed_without_cancel"

        run("cancel_in_flight", cancel_late, cancel=cancel)

        # 3b. deliberate invalid request (unknown model) through the adapter's typed errors
        bogus = "mi6-nonexistent-model"
        bogus_pricing = _pricing(bogus, "bogus")

        def invalid(unit: WorkUnit, entry: dict[str, Any]) -> str:
            unit.step([_user(TextPart(text="hello"))])
            return "unexpected_success"

        run(
            "invalid_request_unknown_model",
            invalid,
            model=bogus,
            pricing=bogus_pricing,
            pricing_id=ledger.register_pricing(
                bogus_pricing, "MI-6 deliberate invalid-model probe"
            ),
        )

        # 4. image input: text-only baseline, then two synthetic sizes
        prompt = "Read the digits in the image. Answer with the digits only."
        expected = "7305"

        def baseline(unit: WorkUnit, entry: dict[str, Any]) -> str:
            response = unit.step([_user(TextPart(text=prompt))])
            entry["usage"] = response.usage.model_dump() if response.usage else None
            return "ok"

        run("image_baseline_text_only", baseline)
        for tag, scale in (("small", 8), ("large", 40)):
            raw = lms.digits_png(expected, scale)

            def image(
                unit: WorkUnit, entry: dict[str, Any], raw: bytes = raw, scale: int = scale
            ) -> str:
                part = ImagePart.from_bytes("image/png", raw)
                response = unit.step([_user(TextPart(text=prompt), part)])
                entry["png_bytes"] = len(raw)
                entry["png_base64_chars"] = len(base64.b64encode(raw))
                entry["png_px"] = [17 * scale, 7 * scale]
                entry["answer"] = response.text()[:60]
                entry["read_correctly"] = expected in response.text()
                entry["usage"] = response.usage.model_dump() if response.usage else None
                return "ok"

            run(f"image_{tag}", image)

        # 5. embeddings endpoint probe (own tiny ledger reservation)
        emb_key = f"mi6-{run_id}-embeddings"
        reservation = ledger.reserve(
            period, emb_key, Decimal("0.01"), pricing_id, work_unit="mi6-emb"
        )
        number = ledger.begin_attempt(
            reservation.reservation_id,
            provider="meta",
            model=model,
            estimated_usd=Decimal("0.001"),
            retry_of=None,
        )
        probe: dict[str, Any] = {}
        try:
            emb = real.embeddings.create(model=model, input="ping", timeout=30.0)
            probe["exists"] = True
            probe["dimension"] = len(emb.data[0].embedding) if emb.data else None
            probe["usage"] = emb.usage.model_dump() if emb.usage else None
            ledger.finish_attempt(
                reservation.reservation_id,
                number,
                status="completed",
                billed_usd=Decimal("0.000001"),
            )
        except openai.OpenAIError as exc:
            probe["exists"] = False
            probe["error"] = _sdk_shape(exc, key)
            ledger.finish_attempt(
                reservation.reservation_id,
                number,
                status="failed",
                billed_usd=Decimal("0"),
                error_code="embeddings_probe",
            )
        ledger.settle(reservation.reservation_id)
        results["embeddings_probe"] = probe

    if PHASE in ("followup", "followup2"):
        scale = int(os.environ.get("FIELDLENS_LIVE_META_SCALE", "40"))
        raw = lms.digits_png("7305", scale)
        digits_prompt = "Read the digits in the image. Answer with the digits only."

        def effort_probe(
            name: str, effort: str, content: list[dict[str, Any]], max_out: int
        ) -> None:
            res = ledger.reserve(
                period, f"mi6-{run_id}-{name}", Decimal("0.05"), pricing_id, work_unit="mi6-eff"
            )
            number = ledger.begin_attempt(
                res.reservation_id,
                provider="meta",
                model=model,
                estimated_usd=Decimal("0.05"),
                retry_of=None,
            )
            entry = results["steps"].setdefault(name, {})
            mark = len(client.captures)
            try:
                resp = client.responses.create(
                    model=model,
                    input=[{"role": "user", "content": content}],
                    max_output_tokens=max_out,
                    store=False,
                    reasoning={"effort": effort},
                    timeout=60.0,
                )
                usage = resp.usage
                assert usage is not None
                entry["outcome"] = "accepted"
                entry["response_status"] = resp.status
                entry["text_head"] = (resp.output_text or "")[:40]
                billed = (
                    Decimal(usage.input_tokens) * RATES["in"]
                    + Decimal(usage.output_tokens) * RATES["out"]
                ) / Decimal(1_000_000)
                ledger.finish_attempt(
                    res.reservation_id,
                    number,
                    status="completed",
                    billed_usd=billed,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )
            except openai.OpenAIError as exc:
                entry["outcome"] = "rejected"
                entry["error"] = _sdk_shape(exc, key)
                ledger.finish_attempt(
                    res.reservation_id,
                    number,
                    status="failed",
                    billed_usd=Decimal("0"),
                    error_code="effort_probe",
                )
            entry["raw_captures"] = client.captures[mark:]
            ledger.settle(res.reservation_id)

    if PHASE == "followup2":
        image_item = {
            "type": "input_image",
            "image_url": "data:image/png;base64," + base64.b64encode(raw).decode(),
        }
        effort_probe(
            f"image_scale{scale}_minimal_effort",
            "minimal",
            [{"type": "input_text", "text": digits_prompt}, image_item],
            1024,
        )

    if PHASE == "followup":
        big = RequestLimits(max_output_tokens=4096, retry_backoff_s=1.0)

        def image_big(unit: WorkUnit, entry: dict[str, Any]) -> str:
            response = unit.step(
                [_user(TextPart(text=digits_prompt), ImagePart.from_bytes("image/png", raw))]
            )
            entry["answer"] = response.text()[:60]
            entry["read_correctly"] = "7305" in response.text()
            entry["usage"] = response.usage.model_dump() if response.usage else None
            return "ok"

        run("image_large_4096_output", image_big, limits=big)
        pong = [{"type": "input_text", "text": "Reply with exactly the single word: pong"}]
        for effort in ("low", "minimal"):
            effort_probe(f"reasoning_effort_{effort}", effort, pong, 1024)

    final = ledger.status(period)
    results["period_committed_usd_total"] = str(final.committed_usd)
    results["period_available_usd"] = str(final.available_usd)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    blob = scrub(json.dumps(results, indent=2, sort_keys=True, default=str), [key])
    assert key not in blob
    OUT.write_text(blob)
    engine.dispose()
    assert final.committed_usd <= CEILING


def _sdk_shape(exc: openai.OpenAIError, key: str) -> dict[str, Any]:
    body = getattr(exc, "body", None)
    return {
        "type": type(exc).__name__,
        "status_code": getattr(exc, "status_code", None),
        "body": scrub(json.dumps(body, default=str)[:400], [key]) if body is not None else None,
    }

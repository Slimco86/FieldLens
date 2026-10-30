"""MI-2 and the credential rules: zero external requests, fail closed, secrets never leak."""

from __future__ import annotations

import json
import logging
import socket
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import openai
import pytest

from fieldlens.assistant import errors
from fieldlens.assistant.budget import BudgetLedger
from fieldlens.assistant.messages import ProviderRequest
from fieldlens.assistant.meta import MetaProvider, map_sdk_error
from fieldlens.assistant.provider import CancelToken, scrub
from fieldlens.assistant.runner import RequestLimits, WorkUnit
from fieldlens.assistant.stub import (
    RecordingProvider,
    ReplayProvider,
    StubProvider,
    text_response,
)
from fieldlens.config import Settings
from tests.assistant_support import MODEL, PRICING, MakeUnit, user

KEY = "sk-synthetic-NOT-A-REAL-KEY-0123456789"


def _settings(**kw: Any) -> Settings:
    if "meta_api_key" in kw:  # the only accepted name is the MODEL_API_KEY alias
        kw["MODEL_API_KEY"] = kw.pop("meta_api_key")
    return Settings(_env_file=None, **kw)


def test_only_model_api_key_names_the_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_API_KEY", "")
    monkeypatch.setenv("FIELDLENS_META_API_KEY", "ALIASVAL123")
    monkeypatch.setenv("META_API_KEY", "ALIASVAL123")
    assert Settings(_env_file=None).meta_api_key is None
    with pytest.raises(errors.ProviderUnavailable):
        MetaProvider(Settings(_env_file=None))


class ExplodingClient:
    """Stands in for the SDK client; any use means a paid call was attempted."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError("the provider client must not be used in default tests")


def test_missing_key_fails_closed_with_a_typed_error() -> None:
    with pytest.raises(errors.ProviderUnavailable, match="API key"):
        MetaProvider(_settings())
    with pytest.raises(errors.ProviderUnavailable):
        MetaProvider(_settings(meta_api_key="   "))


def test_provider_is_constructed_without_any_request_and_hides_the_key() -> None:
    provider = MetaProvider(_settings(meta_api_key=KEY))
    assert provider.name == "meta"
    assert KEY not in repr(provider) and KEY not in str(provider.__dict__.get("_base_url", ""))
    assert provider._client.max_retries == 0  # SDK auto-retry disabled; the runner owns the retry
    assert str(provider._client.base_url).startswith("https://api.meta.ai/v1")


def test_external_sockets_are_denied_in_default_tests() -> None:
    sock = socket.socket()
    try:
        with pytest.raises(Exception, match="external network blocked|name resolution blocked"):
            sock.connect(("api.meta.ai", 443))
    finally:
        sock.close()


def test_base_url_must_be_https_or_loopback() -> None:
    with pytest.raises(ValueError):
        _settings(meta_base_url="http://api.meta.ai/v1")
    assert _settings(meta_base_url="http://127.0.0.1:9/v1").meta_base_url.startswith(
        "http://127.0.0.1"
    )


def test_key_never_appears_in_settings_rendering() -> None:
    settings = _settings(meta_api_key=KEY)
    assert KEY not in repr(settings) and KEY not in str(settings.redacted())
    assert settings.redacted()["meta_api_key"] == "***"


def test_sdk_errors_map_to_fixed_messages_without_the_key() -> None:
    import httpx

    request = httpx.Request(
        "POST", "https://api.meta.ai/v1/responses", headers={"authorization": f"Bearer {KEY}"}
    )
    response = httpx.Response(401, request=request, headers={"retry-after": "7"})
    leaky = openai.AuthenticationError(f"bad key {KEY}", response=response, body={"key": KEY})
    mapped = map_sdk_error(leaky)
    assert (
        isinstance(mapped, errors.ProviderAuthError)
        and KEY not in str(mapped)
        and KEY not in repr(mapped)
    )
    limited = map_sdk_error(
        openai.RateLimitError(
            "slow",
            response=httpx.Response(429, request=request, headers={"retry-after": "7"}),
            body=None,
        )
    )
    assert isinstance(limited, errors.ProviderRateLimited) and limited.retry_after_s == 7.0
    server = map_sdk_error(
        openai.InternalServerError("x", response=httpx.Response(503, request=request), body=None)
    )
    assert isinstance(server, errors.ProviderServerError)
    assert isinstance(
        map_sdk_error(openai.APITimeoutError(request=request)), errors.ProviderTimeout
    )
    assert isinstance(
        map_sdk_error(openai.APIConnectionError(request=request)), errors.ProviderConnectionError
    )
    bad = map_sdk_error(
        openai.BadRequestError("x", response=httpx.Response(400, request=request), body=None)
    )
    assert isinstance(bad, errors.ProviderMalformed)


def test_meta_provider_complete_maps_exceptions_from_an_injected_client() -> None:
    import httpx

    class Failing:
        class responses:  # noqa: N801
            @staticmethod
            def create(**_: Any) -> Any:
                raise openai.APITimeoutError(
                    request=httpx.Request("POST", "https://api.meta.ai/v1/responses")
                )

    provider = MetaProvider(_settings(meta_api_key=KEY), client=Failing())
    with pytest.raises(errors.ProviderTimeout) as info:
        provider.complete(
            ProviderRequest(model=MODEL, messages=(user("hi"),)), timeout_s=1, cancel=CancelToken()
        )
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_cancelled_token_prevents_any_client_call() -> None:
    provider = MetaProvider(_settings(meta_api_key=KEY), client=ExplodingClient())
    token = CancelToken()
    token.cancel()
    with pytest.raises(errors.RequestCancelled):
        provider.complete(
            ProviderRequest(model=MODEL, messages=(user("hi"),)), timeout_s=1, cancel=token
        )


def test_scrub_removes_credential_shaped_text() -> None:
    text = f"Authorization: Bearer abcdef123456 key={KEY} api_key: hunter22hunter"
    cleaned = scrub(text, [KEY])
    assert KEY not in cleaned and "abcdef123456" not in cleaned and "hunter22hunter" not in cleaned


def test_no_balance_or_pricing_is_unavailable_before_dispatch(
    ledger: BudgetLedger, period: UUID, pricing_id: UUID
) -> None:
    stub = StubProvider()

    def unit(period_id: UUID, pricing_id: UUID) -> WorkUnit:
        return WorkUnit(
            provider=stub,
            ledger=ledger,
            period_id=period_id,
            pricing_id=pricing_id,
            pricing=PRICING,
            model=MODEL,
            request_key="k",
            work_unit="u",
            limits=RequestLimits(),
        )

    no_balance = ledger.ensure_period(
        "nb", ledger_cap_usd=Decimal("10"), warn_usd=Decimal("5"), unattended_block_usd=Decimal("8")
    )
    with pytest.raises(errors.ProviderUnavailable):
        with unit(no_balance, pricing_id):
            pass
    import uuid

    from sqlalchemy.exc import IntegrityError

    with pytest.raises(
        IntegrityError
    ):  # unknown pricing revision: FK rejects it, nothing dispatched
        with unit(period, uuid.uuid4()):
            pass
    assert stub.calls == []


def test_secrets_do_not_reach_logs_errors_or_attempt_rows(
    make_unit: MakeUnit, engine: Any, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    stub = StubProvider([errors.ProviderServerError("boom"), text_response("ok")])
    with make_unit(stub) as unit:
        unit.step([user(f"prompt text with {KEY}")])
    from sqlalchemy import text

    with engine.connect() as conn:
        dump = json.dumps(
            [list(map(str, r)) for r in conn.execute(text("SELECT * FROM provider_attempt")).all()]
        )
        dump += json.dumps(
            [list(map(str, r)) for r in conn.execute(text("SELECT * FROM spend_reservation")).all()]
        )
    assert KEY not in dump and KEY not in caplog.text


def test_replay_round_trip_and_fixture_hygiene(tmp_path: Path) -> None:
    request = ProviderRequest(model=MODEL, messages=(user("synthetic page"),))
    recorder = RecordingProvider(
        StubProvider([text_response("answer"), errors.ProviderTimeout("t")])
    )
    recorder.complete(request, timeout_s=1, cancel=CancelToken())
    with pytest.raises(errors.ProviderTimeout):
        recorder.complete(request, timeout_s=1, cancel=CancelToken())
    path = tmp_path / "rec.json"
    path.write_text(recorder.to_json())
    assert "synthetic page" not in path.read_text()  # recordings hold responses, never prompts
    replay = ReplayProvider.from_file(path)
    assert replay.complete(request, timeout_s=1, cancel=CancelToken()).text() == "answer"
    with pytest.raises(errors.ProviderTimeout):
        replay.complete(request, timeout_s=1, cancel=CancelToken())
    with pytest.raises(errors.ReplayMiss):
        replay.complete(request, timeout_s=1, cancel=CancelToken())
    other = ProviderRequest(model=MODEL, messages=(user("different"),))
    with pytest.raises(errors.ReplayMiss):
        ReplayProvider.from_file(path).complete(other, timeout_s=1, cancel=CancelToken())


def test_recorder_refuses_to_write_credential_like_content() -> None:
    request = ProviderRequest(model=MODEL, messages=(user("x"),))
    recorder = RecordingProvider(StubProvider([text_response(f"leak {KEY}")]))
    recorder.complete(request, timeout_s=1, cancel=CancelToken())
    with pytest.raises(errors.ProviderMalformed):
        recorder.to_json()


def test_replay_provider_drives_a_work_unit(make_unit: MakeUnit, tmp_path: Path) -> None:
    request_messages = [user("replay me")]
    probe = ProviderRequest(model=MODEL, messages=tuple(request_messages), max_output_tokens=4096)
    replay = ReplayProvider(
        [
            {
                "fingerprint": probe.fingerprint(),
                "response": text_response("recorded").model_dump(mode="json"),
            }
        ]
    )
    with make_unit(replay) as unit:
        assert unit.step(request_messages).text() == "recorded"

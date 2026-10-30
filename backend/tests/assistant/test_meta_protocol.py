"""MI-1: text, typed tool call/result IDs, refusal, truncation, opaque reasoning, image parts."""

from __future__ import annotations

import json
from typing import Any

import pytest

from fieldlens.assistant.errors import ProviderMalformed
from fieldlens.assistant.messages import (
    ImagePart,
    Message,
    ProviderRequest,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    validate_tool_arguments,
)
from fieldlens.assistant.meta import build_responses_payload, parse_responses_payload
from fieldlens.assistant.provider import CancelToken
from fieldlens.assistant.stub import StubProvider, tool_call_response
from tests.assistant_support import LOOKUP_TOOL, MODEL

PNG = b"\x89PNG\r\n\x1a\n" + b"synthetic-page"


def _payload(*output: dict[str, Any], status: str = "completed", **extra: Any) -> dict[str, Any]:
    return {
        "id": "resp_1",
        "model": MODEL,
        "status": status,
        "output": list(output),
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "input_tokens_details": {"cached_tokens": 40},
        },
        **extra,
    }


def _text(text: str) -> dict[str, Any]:
    return {"type": "message", "content": [{"type": "output_text", "text": text}]}


def test_parse_text_with_usage() -> None:
    response = parse_responses_payload(_payload(_text("hello")))
    assert response.status == "completed" and response.text() == "hello"
    assert response.usage is not None
    assert (
        response.usage.input_tokens,
        response.usage.cached_input_tokens,
        response.usage.output_tokens,
    ) == (100, 40, 20)
    assert response.provider_request_id == "resp_1"


def test_missing_usage_is_unavailable_not_zero() -> None:
    payload = _payload(_text("x"))
    del payload["usage"]
    assert parse_responses_payload(payload).usage is None


def test_parse_tool_call_ids_and_arguments() -> None:
    call = {
        "type": "function_call",
        "call_id": "call_7",
        "name": "read_page",
        "arguments": '{"page": 3}',
    }
    response = parse_responses_payload(_payload(call))
    assert [(c.call_id, c.name, c.arguments) for c in response.tool_calls()] == [
        ("call_7", "read_page", {"page": 3})
    ]


@pytest.mark.parametrize("arguments", ["{not json", "[1, 2]", None])
def test_malformed_tool_arguments_are_typed_errors(arguments: Any) -> None:
    call = {"type": "function_call", "call_id": "c1", "name": "read_page", "arguments": arguments}
    with pytest.raises(ProviderMalformed):
        parse_responses_payload(_payload(call))


def test_bad_schema_is_malformed() -> None:
    with pytest.raises(ProviderMalformed):
        parse_responses_payload({"status": "completed", "output": "nope"})
    with pytest.raises(ProviderMalformed):
        parse_responses_payload({"status": "weird", "output": []})
    with pytest.raises(ProviderMalformed):
        parse_responses_payload(
            _payload(
                {
                    "type": "function_call",
                    "call_id": "bad id!",
                    "name": "read_page",
                    "arguments": "{}",
                }
            )
        )


def test_refusal_and_truncation_statuses() -> None:
    refusal = parse_responses_payload(
        _payload({"type": "message", "content": [{"type": "refusal", "refusal": "no"}]})
    )
    assert refusal.status == "refusal"
    truncated = parse_responses_payload(
        _payload(
            _text("partial"),
            status="incomplete",
            incomplete_details={"reason": "max_output_tokens"},
        )
    )
    assert truncated.status == "truncated" and truncated.text() == "partial"
    filtered = parse_responses_payload(
        _payload(status="incomplete", incomplete_details={"reason": "content_filter"})
    )
    assert filtered.status == "refusal"


def test_opaque_reasoning_replays_verbatim_and_is_not_rendered() -> None:
    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "OPAQUE-BLOB-123"}
    response = parse_responses_payload(_payload(reasoning, _text("answer")))
    part = response.parts[0]
    assert isinstance(part, ReasoningPart) and part.opaque == "OPAQUE-BLOB-123"
    assert "OPAQUE-BLOB-123" not in repr(response) and "OPAQUE-BLOB-123" not in repr(part)
    request = ProviderRequest(
        model=MODEL, messages=(Message(role="assistant", parts=response.parts),)
    )
    sent = build_responses_payload(request)["input"]
    assert sent[0] == {
        "type": "reasoning",
        "id": "rs_1",
        "summary": [],
        "encrypted_content": "OPAQUE-BLOB-123",
    }
    assert sent[1]["content"][0] == {"type": "output_text", "text": "answer"}


def test_web_search_calls_are_counted_separately() -> None:
    response = parse_responses_payload(_payload({"type": "web_search_call"}, _text("x")))
    assert response.usage is not None and response.usage.web_search_queries == 1


def test_payload_has_image_parts_and_tool_round_trip() -> None:
    image = ImagePart.from_bytes("image/png", PNG)
    messages = (
        Message(role="system", parts=(TextPart(text="Read the page."),)),
        Message(role="user", parts=(TextPart(text="Extract."), image)),
        Message(
            role="assistant",
            parts=(ToolCallPart(call_id="c1", name="read_page", arguments={"page": 2}),),
        ),
        Message(role="tool", parts=(ToolResultPart(call_id="c1", content="page text"),)),
    )
    payload = build_responses_payload(
        ProviderRequest(model=MODEL, messages=messages, tools=(LOOKUP_TOOL,))
    )
    items = payload["input"]
    assert items[1]["content"][1]["type"] == "input_image"
    assert items[1]["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert items[2] == {
        "type": "function_call",
        "call_id": "c1",
        "name": "read_page",
        "arguments": '{"page": 2}',
    }
    assert items[3] == {"type": "function_call_output", "call_id": "c1", "output": "page text"}
    assert payload["store"] is False and payload["tools"][0]["name"] == "read_page"
    json.dumps(payload)  # serializable


def test_image_validation() -> None:
    with pytest.raises(ValueError):
        ImagePart(media_type="image/png", data_base64="!!not base64!!")
    with pytest.raises(ValueError):
        ImagePart(media_type="image/png", data_base64="")
    with pytest.raises(ProviderMalformed):
        build_responses_payload(
            ProviderRequest(
                model=MODEL,
                messages=(
                    Message(role="assistant", parts=(ImagePart.from_bytes("image/png", PNG),)),
                ),
            )
        )


def test_tool_argument_validation() -> None:
    assert validate_tool_arguments(LOOKUP_TOOL, {"page": 1}) is None
    assert validate_tool_arguments(LOOKUP_TOOL, {}) is not None
    assert validate_tool_arguments(LOOKUP_TOOL, {"page": "1"}) is not None
    assert validate_tool_arguments(LOOKUP_TOOL, {"page": True}) is not None
    assert validate_tool_arguments(LOOKUP_TOOL, {"page": 1, "extra": 1}) is not None


def test_stub_handles_image_parts_deterministically() -> None:
    image = ImagePart.from_bytes("image/png", PNG)
    request = ProviderRequest(
        model=MODEL, messages=(Message(role="user", parts=(TextPart(text="look"), image)),)
    )
    stub = StubProvider()
    first = stub.complete(request, timeout_s=5, cancel=CancelToken())
    again = StubProvider().complete(request, timeout_s=5, cancel=CancelToken())
    assert first == again and image.sha256[:8] in first.text() and f":{len(PNG)}" in first.text()


def test_stub_tool_call_round_trip_keeps_ids() -> None:
    stub = StubProvider(
        [
            tool_call_response(("call_a", "read_page", {"page": 1})),
        ]
    )
    first = stub.complete(
        ProviderRequest(
            model=MODEL,
            messages=(Message(role="user", parts=(TextPart(text="go"),)),),
            tools=(LOOKUP_TOOL,),
        ),
        timeout_s=5,
        cancel=CancelToken(),
    )
    call = first.tool_calls()[0]
    follow_up = ProviderRequest(
        model=MODEL,
        messages=(
            Message(role="assistant", parts=first.parts),
            Message(role="tool", parts=(ToolResultPart(call_id=call.call_id, content="ok"),)),
        ),
    )
    echoed = StubProvider().complete(follow_up, timeout_s=5, cancel=CancelToken())
    assert "call_a=ok" in echoed.text()

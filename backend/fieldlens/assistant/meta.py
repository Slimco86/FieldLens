"""OpenAI-compatible Meta client wrapper (Responses API against the configured base URL).

Constructed from server-side configuration only; a missing key fails closed with
``ProviderUnavailable`` before any client exists. SDK retries are disabled (the runner owns the
single retry). Default tests never call :meth:`MetaProvider.complete`; payload building, response
parsing and exception mapping are pure functions tested with fixture payloads. Error messages are
fixed strings: SDK exception text, request bodies and headers are never propagated.
No embeddings endpoint is used or assumed.
"""

from __future__ import annotations

import json
from typing import Any

import openai
from pydantic import ValidationError

from fieldlens.config import Settings

from .errors import (
    AssistantError,
    ProviderAuthError,
    ProviderConnectionError,
    ProviderMalformed,
    ProviderRateLimited,
    ProviderRejected,
    ProviderServerError,
    ProviderTimeout,
    ProviderUnavailable,
)
from .messages import (
    ImagePart,
    Message,
    ProviderRequest,
    ProviderResponse,
    ReasoningPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Usage,
)
from .provider import CancelToken

MAX_RETRY_AFTER_S = 30.0
# [Assumed: only 404 observed live (unknown model, embeddings); 405 by analogy.] Every other 4xx
# not handled earlier (400, 408, 409, 413, 422, ...) stays possibly billed until observed.
_REJECTED_BEFORE_PROCESSING = frozenset({404, 405})


def build_responses_payload(request: ProviderRequest) -> dict[str, Any]:
    """Responses-protocol request body. Stateless (``store`` false); no web search tool."""
    payload: dict[str, Any] = {
        "model": request.model,
        "input": [item for message in request.messages for item in _message_items(message)],
        "max_output_tokens": request.max_output_tokens,
        "store": False,
    }
    if request.effort is not None:
        payload["reasoning"] = {"effort": request.effort}
    if request.tools:
        payload["tools"] = [
            {
                "type": "function",
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
                "strict": False,
            }
            for t in request.tools
        ]
        payload["tool_choice"] = "auto"
    return payload


def _message_items(message: Message) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    content: list[dict[str, Any]] = []
    text_type = "output_text" if message.role == "assistant" else "input_text"

    def flush() -> None:
        if content:
            role = "user" if message.role == "tool" else message.role
            items.append({"role": role, "content": list(content)})
            content.clear()

    for part in message.parts:
        if isinstance(part, TextPart):
            content.append({"type": text_type, "text": part.text})
        elif isinstance(part, ImagePart):
            if message.role not in ("user", "system"):
                raise ProviderMalformed("image parts are only valid in user messages")
            content.append(
                {
                    "type": "input_image",
                    "image_url": f"data:{part.media_type};base64,{part.data_base64}",
                }
            )
        elif isinstance(part, ToolCallPart):
            flush()
            items.append(
                {
                    "type": "function_call",
                    "call_id": part.call_id,
                    "name": part.name,
                    "arguments": json.dumps(part.arguments, sort_keys=True),
                }
            )
        elif isinstance(part, ToolResultPart):
            flush()
            items.append(
                {"type": "function_call_output", "call_id": part.call_id, "output": part.content}
            )
        elif isinstance(part, ReasoningPart):
            flush()
            items.append(
                {
                    "type": "reasoning",
                    "id": part.item_id,
                    "summary": [],
                    "encrypted_content": part.opaque,
                }
            )
    flush()
    return items


def parse_responses_payload(payload: dict[str, Any]) -> ProviderResponse:
    """Map a Responses object (as a dict) to the adapter response; raise typed errors if bad."""
    try:
        return _parse(payload)
    except AssistantError:
        raise
    except (ValidationError, KeyError, TypeError, ValueError, AttributeError) as exc:
        raise ProviderMalformed("provider response did not match the expected schema") from exc


def _parse(payload: dict[str, Any]) -> ProviderResponse:
    status = payload.get("status")
    if status == "failed":
        raise ProviderServerError("provider reported a failed response")
    if status not in ("completed", "incomplete"):
        raise ProviderMalformed("unrecognized response status")
    parts: list[Any] = []
    refused = False
    web_queries = 0
    output = payload.get("output")
    if not isinstance(output, list):
        raise ProviderMalformed("response output is not a list")
    for item in output:
        kind = item.get("type")
        if kind == "message":
            for block in item.get("content", []):
                if block.get("type") == "output_text":
                    parts.append(TextPart(text=str(block["text"])))
                elif block.get("type") == "refusal":
                    refused = True
        elif kind == "function_call":
            try:
                arguments = json.loads(item["arguments"])
            except (json.JSONDecodeError, TypeError) as exc:
                raise ProviderMalformed("tool call arguments are not valid JSON") from exc
            if not isinstance(arguments, dict):
                raise ProviderMalformed("tool call arguments must be a JSON object")
            parts.append(
                ToolCallPart(call_id=item["call_id"], name=item["name"], arguments=arguments)
            )
        elif kind == "reasoning":
            opaque = item.get("encrypted_content")
            if isinstance(opaque, str) and opaque:
                parts.append(ReasoningPart(opaque=opaque, item_id=item.get("id")))
        elif kind == "web_search_call":
            web_queries += 1
    usage_raw = payload.get("usage")
    usage: Usage | None = None
    if isinstance(usage_raw, dict):
        details = usage_raw.get("input_tokens_details") or {}
        usage = Usage(
            input_tokens=usage_raw.get("input_tokens"),
            cached_input_tokens=details.get("cached_tokens"),
            output_tokens=usage_raw.get("output_tokens"),
            web_search_queries=web_queries or None,
        )
    elif web_queries:
        usage = Usage(web_search_queries=web_queries)
    reason = (payload.get("incomplete_details") or {}).get("reason")
    out_status = "completed"
    if refused or reason == "content_filter":
        out_status = "refusal"
    elif status == "incomplete":
        out_status = "truncated"
    return ProviderResponse(
        status=out_status,
        parts=tuple(parts),
        usage=usage,
        model=payload.get("model"),
        provider_request_id=payload.get("id"),
        refusal_text="declined" if out_status == "refusal" else None,
    )


def map_sdk_error(exc: Exception) -> AssistantError:
    """Fixed-message typed error for an SDK exception (its text is never propagated)."""
    if isinstance(exc, openai.APITimeoutError):
        return ProviderTimeout("provider call timed out")
    if isinstance(exc, openai.APIConnectionError):
        return ProviderConnectionError("provider connection failed")
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return ProviderAuthError("provider rejected the credentials or entitlement")
    if isinstance(exc, openai.RateLimitError):
        return ProviderRateLimited("provider rate limited", _retry_after(exc))
    if isinstance(exc, openai.APIStatusError):
        if exc.status_code >= 500:
            return ProviderServerError(f"provider server error ({exc.status_code})")
        if exc.status_code in _REJECTED_BEFORE_PROCESSING:
            # MI-6: the dashboard showed no billed request for the 404 probes (non-billable).
            return ProviderRejected(f"provider rejected the request ({exc.status_code})")
        return ProviderMalformed(f"provider rejected the request ({exc.status_code})")
    return ProviderMalformed("unexpected provider client error")


def _retry_after(exc: openai.APIStatusError) -> float | None:
    raw = exc.response.headers.get("retry-after") if exc.response is not None else None
    try:
        value = float(raw) if raw is not None else None
    except ValueError:
        return None
    if value is None or value < 0:
        return None
    return min(value, MAX_RETRY_AFTER_S)


class MetaProvider:
    """Calls the Meta OpenAI-compatible Responses endpoint. Not used by default tests."""

    name = "meta"

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        key = settings.meta_api_key
        if key is None or not key.get_secret_value().strip():
            raise ProviderUnavailable("API key is not configured (MODEL_API_KEY)")
        self._base_url = settings.meta_base_url
        self._model = settings.meta_model
        self._client = client or openai.OpenAI(
            api_key=key.get_secret_value(),
            base_url=settings.meta_base_url,
            max_retries=0,  # the application owns the single retry
            timeout=settings.provider_deadline_s,
        )

    def __repr__(self) -> str:
        return f"MetaProvider(base_url={self._base_url!r}, model={self._model!r}, api_key=***)"

    def complete(
        self, request: ProviderRequest, *, timeout_s: float, cancel: CancelToken
    ) -> ProviderResponse:
        cancel.raise_if_cancelled()
        payload = build_responses_payload(request)
        # Cancel semantics (MI-6): the synchronous SDK call is not aborted in flight. It runs to
        # completion and bills; the work unit then settles the actual usage and raises
        # RequestCancelled. Cancel therefore prevents later calls, not billing of this one.
        try:
            response = self._client.responses.create(**payload, timeout=timeout_s)
        except openai.OpenAIError as exc:
            raise map_sdk_error(exc) from None
        try:
            raw = response.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001 - any SDK shape problem is malformed output
            raise ProviderMalformed("provider response could not be read") from exc
        return parse_responses_payload(raw)

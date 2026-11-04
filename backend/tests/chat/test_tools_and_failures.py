"""Tool allowlist/argument validation, failure mapping and runtime availability (no DB)."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest

from fieldlens.assistant.errors import (
    ProviderAuthError,
    ProviderMalformed,
    ProviderRefusal,
    ProviderTruncated,
    ProviderUnavailable,
    RequestCancelled,
    RequestLimitExceeded,
)
from fieldlens.assistant.messages import ToolCallPart
from fieldlens.chat.evidence_pool import TurnEvidence, numbers_in
from fieldlens.chat.executor import failure_for
from fieldlens.chat.tools import TOOLS, ToolRunner
from fieldlens.contracts.chat import ChatContext, ChatFailureCode, ChatRunState

READ_ONLY_TOOLS = {
    "search_evidence",
    "get_source_coverage",
    "list_wellbores",
    "get_trajectory_summary",
    "compare_wellbores",
    "list_series",
    "get_series_summary",
    "list_draft_proposals",
}


def _runner() -> ToolRunner:
    return ToolRunner(
        project_id=uuid4(),
        factory=None,  # type: ignore[arg-type]  # never reached: validation fails first
        retrieval=None,
        series=None,
        context=ChatContext(),
        evidence=TurnEvidence(),
    )


def _call(name: str, args: dict[str, Any]) -> ToolCallPart:
    return ToolCallPart(call_id="c1", name=name, arguments=args)


def test_allowlist_is_exactly_the_read_only_set() -> None:
    assert set(TOOLS) == READ_ONLY_TOOLS
    for forbidden in ("run_sql", "execute", "shell", "fetch_url", "write", "publish", "update"):
        assert forbidden not in TOOLS


def test_tool_schemas_are_closed() -> None:
    for tool in TOOLS.values():
        assert tool.args.model_config.get("extra") == "forbid"


def test_unknown_tool_is_rejected_without_running() -> None:
    out = json.loads(_runner().execute(_call("run_sql", {"q": "drop table x"})))
    assert out["ok"] is False


@pytest.mark.parametrize(
    "args",
    [
        {},  # missing q
        {"q": "x", "project_id": str(uuid4())},  # a model cannot widen scope with extra args
        {"q": 5},
        {"q": "x", "limit": "many"},
    ],
)
def test_invalid_arguments_are_rejected(args: dict[str, Any]) -> None:
    out = json.loads(_runner().execute(_call("search_evidence", args)))
    assert out["ok"] is False


def test_no_tool_accepts_a_project_id_argument() -> None:
    for tool in TOOLS.values():
        assert "project_id" not in tool.args.model_fields


def test_numbers_in_collects_leaves_and_list_lengths() -> None:
    out: set[float] = set()
    numbers_in({"a": [1.5, {"b": 2}], "s": "x 7.25 y"}, out)
    assert {1.5, 2.0, 7.25}.issubset(out)


@pytest.mark.parametrize(
    ("exc", "state", "code"),
    [
        (RequestCancelled(), ChatRunState.CANCELLED, ChatFailureCode.CANCELLED),
        (ProviderRefusal(), ChatRunState.REFUSED, ChatFailureCode.PROVIDER_REFUSAL),
        (ProviderTruncated(), ChatRunState.TRUNCATED, ChatFailureCode.TRUNCATED),
        (RequestLimitExceeded("deadline"), ChatRunState.FAILED, ChatFailureCode.TIME_LIMIT),
        (RequestLimitExceeded("tool_calls"), ChatRunState.FAILED, ChatFailureCode.TOOL_CALL_LIMIT),
        (RequestLimitExceeded("attempts"), ChatRunState.FAILED, ChatFailureCode.STEP_LIMIT),
        (ProviderMalformed(), ChatRunState.FAILED, ChatFailureCode.MALFORMED_OUTPUT),
        (ProviderAuthError(), ChatRunState.FAILED, ChatFailureCode.PROVIDER_OUTAGE),
        (ProviderUnavailable("down"), ChatRunState.FAILED, ChatFailureCode.PROVIDER_OUTAGE),
        (RuntimeError("boom"), ChatRunState.FAILED, ChatFailureCode.INTERNAL),
    ],
)
def test_failure_mapping_is_explicit_never_success(
    exc: BaseException, state: ChatRunState, code: ChatFailureCode
) -> None:
    got_state, failure = failure_for(exc)
    assert got_state is state
    assert failure.code is code
    assert failure.message

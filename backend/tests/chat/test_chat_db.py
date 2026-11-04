"""Chat persistence, scoping, idempotency, in-flight guard, routes and runner on PostgreSQL.

UNRUN IN THE TASK-103 WORKTREE: no .env/database is available there, so these tests were written
against the existing fixtures (``migrated_url``/``engine``/``make_api``) and have NOT been
executed. Independent QA runs them from the main checkout. Every turn uses the scripted stub
provider: they spend no API credit and never touch the network.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import URL

import fieldlens.chat.runner as runner_module
from fieldlens.assistant.stub import StubProvider, text_response, tool_call_response
from fieldlens.chat.runner import ChatRunner
from fieldlens.chat.runtime import ChatLimits, build_chat_runtime
from fieldlens.contracts.chat import ChatRunState, ChatUsage
from tests.chat.support import blocks_json, install_fake_tools
from tests.conftest import settings_for
from tests.upload_support import Api, make_api

GAP = {"kind": "gap", "reason": "no_data", "text": "No stored source states this."}
SEARCH = ("c1", "search_evidence", {"q": "casing shoe"})


class Chat:
    """An API plus a chat runtime whose provider is a script; the runner is driven explicitly."""

    def __init__(self, api: Api, url: URL, provider: StubProvider, limits: ChatLimits | None):
        self.api = api
        self.app: Any = api.client.app
        settings = settings_for(url)
        self.rt = build_chat_runtime(
            self.app.state.session_factory,
            settings,
            None,
            None,
            provider=provider,
            limits=limits or ChatLimits(retry_backoff_s=0.0),
        )
        self.app.state.chat = self.rt
        self.runner = ChatRunner(self.rt, workers=1, poll_s=0.05)

    def base(self, project: str) -> str:
        return f"/api/v1/projects/{project}/chat"

    def conversation(self, project: str, title: str | None = None) -> str:
        r = self.api.client.post(
            f"{self.base(project)}/conversations", json={"title": title}, headers=self.api.headers
        )
        assert r.status_code == 201, r.text
        return str(r.json()["conversation_id"])

    def post(self, project: str, cid: str, message: str = "hello", **extra: Any) -> Any:
        return self.api.client.post(
            f"{self.base(project)}/conversations/{cid}/turns",
            json={"message": message, **extra},
            headers=self.api.headers,
        )

    def turn(self, project: str, cid: str, tid: str) -> dict[str, Any]:
        r = self.api.client.get(f"{self.base(project)}/conversations/{cid}/turns/{tid}")
        assert r.status_code == 200, r.text
        return dict(r.json())

    def cancel(self, project: str, cid: str, tid: str) -> Any:
        return self.api.client.post(
            f"{self.base(project)}/conversations/{cid}/turns/{tid}/cancel",
            headers=self.api.headers,
        )


@pytest.fixture
def make_chat(migrated_url: URL, tmp_path: Path) -> Any:
    def build(script: list[Any] | None = None, limits: ChatLimits | None = None) -> Chat:
        api = make_api(migrated_url, tmp_path)
        provider = StubProvider(script or [text_response(blocks_json(GAP))], loop_last=True)
        return Chat(api, migrated_url, provider, limits)

    return build


def test_turn_is_persisted_polled_and_completed(make_chat: Any) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    cid = chat.conversation(project)
    created = chat.post(project, cid, "What is TD?")
    assert created.status_code == 202
    body = created.json()
    assert body["state"] == "queued" and body["user_message"]["text"] == "What is TD?"
    assert chat.runner.run_one() is True
    done = chat.turn(project, cid, body["turn_id"])
    assert done["state"] == "completed" and done["failure"] is None
    assert done["assistant_message"]["answer"]["blocks"][0]["kind"] == "gap"
    assert done["usage"]["steps"] == 1
    detail = chat.api.client.get(f"{chat.base(project)}/conversations/{cid}").json()
    assert [t["turn_id"] for t in detail["turns"]] == [body["turn_id"]]
    listing = chat.api.client.get(f"{chat.base(project)}/conversations").json()
    assert listing["total"] == 1 and listing["items"][0]["turn_count"] == 1
    assert chat.runner.run_one() is False  # nothing left queued


def test_conversations_and_turns_are_project_scoped(make_chat: Any) -> None:
    chat: Chat = make_chat()
    mine, other = chat.api.project("mine"), chat.api.project("other")
    cid = chat.conversation(mine)
    tid = chat.post(mine, cid).json()["turn_id"]
    base = chat.base(other)
    client, headers = chat.api.client, chat.api.headers
    assert client.get(f"{base}/conversations/{cid}").status_code == 404
    assert client.get(f"{base}/conversations/{cid}/turns/{tid}").status_code == 404
    assert chat.post(other, cid).status_code == 404
    assert chat.cancel(other, cid, tid).status_code == 404
    assert client.get(f"{base}/conversations").json()["total"] == 0
    unknown = client.post(
        f"/api/v1/projects/{uuid4()}/chat/conversations", json={}, headers=headers
    )
    assert unknown.status_code == 404
    # the owner still sees it untouched
    assert chat.turn(mine, cid, tid)["state"] == "queued"


def test_context_cannot_reference_another_projects_wellbore(make_chat: Any) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    cid = chat.conversation(project)
    r = chat.post(project, cid, "x", context={"wellbore_id": str(uuid4())})
    assert r.status_code in {404, 422}


def test_idempotent_repeat_returns_the_original_turn(make_chat: Any) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    cid = chat.conversation(project)
    first = chat.post(project, cid, "same", idempotency_key="k1")
    again = chat.post(project, cid, "same", idempotency_key="k1")
    assert first.status_code == 202 and again.status_code == 200
    assert again.json()["turn_id"] == first.json()["turn_id"]
    different = chat.post(project, cid, "other text", idempotency_key="k1")
    assert different.status_code == 409
    listing = chat.api.client.get(f"{chat.base(project)}/conversations/{cid}").json()
    assert len(listing["turns"]) == 1


def test_one_in_flight_turn_per_conversation(make_chat: Any) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    cid = chat.conversation(project)
    assert chat.post(project, cid, "one").status_code == 202
    assert chat.post(project, cid, "two").status_code == 409  # still queued
    assert chat.runner.run_one() is True
    assert chat.post(project, cid, "three").status_code == 202  # free again once terminal
    # a different conversation is independent
    cid2 = chat.conversation(project)
    assert chat.post(project, cid2, "parallel").status_code == 202


def test_post_is_unavailable_when_the_assistant_is_not_wired(make_chat: Any) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    cid = chat.conversation(project)
    chat.app.state.chat = None
    assert chat.post(project, cid).status_code == 503


def test_mutations_require_the_session_token(make_chat: Any) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    r = chat.api.client.post(f"{chat.base(project)}/conversations", json={})
    assert r.status_code in {401, 403}


def test_cancelling_a_queued_turn_is_immediate_and_idempotent(make_chat: Any) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    cid = chat.conversation(project)
    tid = chat.post(project, cid).json()["turn_id"]
    first = chat.cancel(project, cid, tid)
    assert first.status_code == 200
    assert first.json()["state"] == "cancelled" and first.json()["failure"]["code"] == "cancelled"
    assert chat.cancel(project, cid, tid).json()["state"] == "cancelled"
    assert chat.runner.run_one() is False  # a cancelled turn is never claimed


def test_failed_provider_is_a_failed_turn_not_a_success(make_chat: Any) -> None:
    from fieldlens.assistant.errors import ProviderConnectionError

    chat: Chat = make_chat([ProviderConnectionError()])
    project = chat.api.project()
    cid = chat.conversation(project)
    tid = chat.post(project, cid).json()["turn_id"]
    chat.runner.run_one()
    done = chat.turn(project, cid, tid)
    assert done["state"] == "failed" and done["failure"]["code"] == "provider_outage"
    assert done["assistant_message"] is None


def test_running_turn_cancel_request_stops_the_runner(
    make_chat: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner_module, "HEARTBEAT_S", 0.05)
    install_fake_tools(monkeypatch)
    state: dict[str, Any] = {}

    def press_cancel(request: Any) -> Any:
        chat = state["chat"]
        r = chat.cancel(state["project"], state["cid"], state["tid"])
        assert r.status_code == 200 and r.json()["state"] == "running"  # flagged, not yet stopped
        time.sleep(0.5)  # the watcher thread (heartbeat 0.05 s) sets the cancel token meanwhile
        return tool_call_response(SEARCH)

    chat: Chat = make_chat([press_cancel, text_response(blocks_json(GAP))])
    project = chat.api.project()
    cid = chat.conversation(project)
    tid = chat.post(project, cid).json()["turn_id"]
    state.update(chat=chat, project=project, cid=cid, tid=tid)
    chat.runner.run_one()
    done = chat.turn(project, cid, tid)
    assert done["state"] == "cancelled" and done["failure"]["code"] == "cancelled"
    assert done["assistant_message"] is None


def test_lapsed_running_turn_is_recovered_as_interrupted(make_chat: Any, engine: Engine) -> None:
    chat: Chat = make_chat()
    project = chat.api.project()
    cid = chat.conversation(project)
    tid = chat.post(project, cid).json()["turn_id"]
    import fieldlens.chat.repository as repo

    claim = repo.claim_next(chat.rt.factory, "other-owner", 60.0)
    assert claim is not None and str(claim.turn_id) == tid
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE chat_turn SET lease_expires_at = now() - interval '1 minute' "
                "WHERE turn_id = :t"
            ),
            {"t": tid},
        )
    assert [str(t) for t in chat.runner.recover_once()] == [tid]
    done = chat.turn(project, cid, tid)
    assert done["state"] == "failed" and done["failure"]["code"] == "interrupted"
    # a late write from the dead worker is fenced out
    stale = repo.finalize(
        chat.rt.factory,
        claim,
        "other-owner",
        state=ChatRunState.COMPLETED,
        answer=None,
        failure=None,
        usage=ChatUsage(),
        tool_calls=[],
    )
    assert stale is False

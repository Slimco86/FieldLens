"""Project-scoped chat routes: conversations, queued turns (polled), cancel.

Posting a message only queues a persisted job; the answer is read by polling the turn. Responses are
never cached. State-changing routes carry the same host/origin/session-token guard as every other
mutation. Every id is checked against the path's project; another project's id is a plain 404.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from fieldlens import security
from fieldlens.chat import repository as repo
from fieldlens.contracts.chat import (
    ChatTurn,
    Conversation,
    ConversationDetail,
    ConversationList,
    CreateConversationRequest,
    CreateTurnRequest,
)
from fieldlens.contracts.errors import ContractError, ErrorCode, ErrorEnvelope


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _guard_mutation(request: Request) -> None:
    security.check_mutation(request, request.app.state.settings, request.app.state.session_token)


def _factory(request: Request) -> sessionmaker[Session]:
    factory = request.app.state.session_factory
    if factory is None:
        raise ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)
    result: sessionmaker[Session] = factory
    return result


def _unavailable() -> ContractError:
    return ContractError(ErrorCode.SERVICE_UNAVAILABLE, "storage is unavailable; try again", 503)


def build_chat_router() -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/projects/{project_id}/chat",
        tags=["chat"],
        responses={
            404: {"model": ErrorEnvelope},
            409: {"model": ErrorEnvelope},
            422: {"model": ErrorEnvelope},
            503: {"model": ErrorEnvelope},
        },
        dependencies=[Depends(_no_store)],
    )

    @router.post(
        "/conversations",
        response_model=Conversation,
        status_code=201,
        dependencies=[Depends(_guard_mutation)],
    )
    def create_conversation(
        project_id: UUID, body: CreateConversationRequest, request: Request
    ) -> Conversation:
        try:
            return repo.create_conversation(_factory(request), project_id, body.title)
        except OperationalError as exc:
            raise _unavailable() from exc

    @router.get("/conversations", response_model=ConversationList)
    def list_conversations(
        project_id: UUID,
        request: Request,
        limit: Annotated[int, Query(ge=1, le=200)] = 50,
        offset: Annotated[int, Query(ge=0, le=1_000_000)] = 0,
    ) -> ConversationList:
        try:
            return repo.list_conversations(_factory(request), project_id, limit, offset)
        except OperationalError as exc:
            raise _unavailable() from exc

    @router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
    def get_conversation(
        project_id: UUID, conversation_id: UUID, request: Request
    ) -> ConversationDetail:
        try:
            return repo.get_conversation(_factory(request), project_id, conversation_id)
        except OperationalError as exc:
            raise _unavailable() from exc

    @router.post(
        "/conversations/{conversation_id}/turns",
        response_model=ChatTurn,
        status_code=202,
        dependencies=[Depends(_guard_mutation)],
    )
    def post_turn(
        project_id: UUID,
        conversation_id: UUID,
        body: CreateTurnRequest,
        request: Request,
        response: Response,
    ) -> ChatTurn:
        if getattr(request.app.state, "chat", None) is None:
            raise ContractError(
                ErrorCode.SERVICE_UNAVAILABLE, "the assistant is not available", 503
            )
        try:
            turn, created = repo.create_turn(
                _factory(request),
                project_id,
                conversation_id,
                body,
            )
        except OperationalError as exc:
            raise _unavailable() from exc
        if not created:
            response.status_code = 200  # same idempotency key and request: the original turn
        return turn

    @router.get("/conversations/{conversation_id}/turns/{turn_id}", response_model=ChatTurn)
    def get_turn(
        project_id: UUID, conversation_id: UUID, turn_id: UUID, request: Request
    ) -> ChatTurn:
        try:
            return repo.get_turn(_factory(request), project_id, conversation_id, turn_id)
        except OperationalError as exc:
            raise _unavailable() from exc

    @router.post(
        "/conversations/{conversation_id}/turns/{turn_id}/cancel",
        response_model=ChatTurn,
        dependencies=[Depends(_guard_mutation)],
    )
    def cancel_turn(
        project_id: UUID, conversation_id: UUID, turn_id: UUID, request: Request
    ) -> ChatTurn:
        try:
            return repo.cancel_turn(_factory(request), project_id, conversation_id, turn_id)
        except OperationalError as exc:
            raise _unavailable() from exc

    return router

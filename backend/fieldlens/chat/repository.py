"""Persistence for conversations, turns and messages. Every query is parameterized Core SQL scoped by
``project_id``; a conversation or turn of another project is indistinguishable from a missing one.

Turn lifecycle writes are conditional on the state (and, once running, on the lease owner), so a
cancelled, recovered or purged turn can never be overwritten by a late worker.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, func, insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.contracts.chat import (
    TERMINAL_STATES,
    ChatAnswer,
    ChatContext,
    ChatFailure,
    ChatFailureCode,
    ChatMessage,
    ChatRole,
    ChatRunState,
    ChatToolCallSummary,
    ChatTurn,
    ChatUsage,
    Conversation,
    ConversationDetail,
    ConversationList,
    CreateTurnRequest,
)
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.identity import service as identity_service
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope

from .tables import chat_conversation, chat_message, chat_turn

C, T, G = chat_conversation, chat_turn, chat_message
MAX_HISTORY_TURNS = 6
MAX_TURNS_PER_CONVERSATION = 500
MAX_PAGE = 100
TITLE_CHARS = 80
_TERMINAL_VALUES = tuple(s.value for s in TERMINAL_STATES)
_IN_FLIGHT = (ChatRunState.QUEUED.value, ChatRunState.RUNNING.value)


def _now() -> Any:
    return func.clock_timestamp()


def _not_found(what: str) -> ContractError:
    return ContractError(ErrorCode.NOT_FOUND, f"{what} not found", 404)


def _conflict(message: str) -> ContractError:
    return ContractError(ErrorCode.CONFLICT, message, 409)


def request_hash(request: CreateTurnRequest) -> str:
    body = json.dumps(
        {"message": request.message, "context": request.context.model_dump(mode="json")},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()


# -- DTO assembly -----------------------------------------------------------------------------


def _conversation_dto(row: Any, turn_count: int) -> Conversation:
    return Conversation(
        conversation_id=row.conversation_id,
        project_id=row.project_id,
        title=row.title,
        turn_count=turn_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _message_dto(row: Any) -> ChatMessage:
    answer = ChatAnswer.model_validate(row.answer) if row.answer is not None else None
    return ChatMessage(
        message_id=row.message_id,
        conversation_id=row.conversation_id,
        turn_id=row.turn_id,
        role=ChatRole(row.role),
        text=row.text,
        answer=answer,
        created_at=row.created_at,
    )


def _turn_dto(row: Any, user: Any, assistant: Any | None) -> ChatTurn:
    return ChatTurn(
        turn_id=row.turn_id,
        conversation_id=row.conversation_id,
        project_id=row.project_id,
        state=ChatRunState(row.state),
        user_message=_message_dto(user),
        assistant_message=_message_dto(assistant) if assistant is not None else None,
        context=ChatContext.model_validate(row.context or {}),
        failure=ChatFailure.model_validate(row.failure) if row.failure else None,
        usage=ChatUsage.model_validate(row.usage or {}),
        tool_calls=[ChatToolCallSummary.model_validate(c) for c in (row.tool_calls or [])],
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


def _turns(session: Session, where: Any, limit: int = MAX_TURNS_PER_CONVERSATION) -> list[ChatTurn]:
    rows = session.execute(
        select(T).where(where).order_by(T.c.conversation_id, T.c.seq).limit(limit)
    ).all()
    if not rows:
        return []
    messages: dict[tuple[UUID, str], Any] = {}
    for msg in session.execute(select(G).where(G.c.turn_id.in_([r.turn_id for r in rows]))):
        messages[(msg.turn_id, msg.role)] = msg
    return [
        _turn_dto(r, messages[(r.turn_id, "user")], messages.get((r.turn_id, "assistant")))
        for r in rows
    ]


# -- conversations ----------------------------------------------------------------------------


def create_conversation(
    factory: sessionmaker[Session], project_id: UUID, title: str | None
) -> Conversation:
    with session_scope(factory) as s:
        identity_service.require_project(s, project_id)
        row = s.execute(insert(C).values(project_id=project_id, title=title).returning(C)).one()
        return _conversation_dto(row, 0)


def _require_conversation(
    session: Session, project_id: UUID, conversation_id: UUID, *, lock: bool = False
) -> Any:
    query = select(C).where(C.c.project_id == project_id, C.c.conversation_id == conversation_id)
    row = session.execute(query.with_for_update() if lock else query).one_or_none()
    if row is None:
        raise _not_found("conversation")
    return row


def list_conversations(
    factory: sessionmaker[Session], project_id: UUID, limit: int, offset: int
) -> ConversationList:
    limit = max(1, min(limit, MAX_PAGE))
    offset = max(0, offset)
    with session_scope(factory) as s:
        identity_service.require_project(s, project_id)
        total = s.execute(
            select(func.count()).select_from(C).where(C.c.project_id == project_id)
        ).scalar_one()
        counts = (
            select(T.c.conversation_id, func.count().label("n"))
            .where(T.c.project_id == project_id)
            .group_by(T.c.conversation_id)
            .subquery()
        )
        rows = s.execute(
            select(C, func.coalesce(counts.c.n, 0).label("n"))
            .outerjoin(counts, counts.c.conversation_id == C.c.conversation_id)
            .where(C.c.project_id == project_id)
            .order_by(C.c.updated_at.desc(), C.c.conversation_id.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        items = [_conversation_dto(r, int(r.n)) for r in rows]
    nxt = offset + len(items)
    return ConversationList(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        next_offset=nxt if nxt < total else None,
    )


def get_conversation(
    factory: sessionmaker[Session], project_id: UUID, conversation_id: UUID
) -> ConversationDetail:
    with session_scope(factory) as s:
        row = _require_conversation(s, project_id, conversation_id)
        turns = _turns(
            s, and_(T.c.project_id == project_id, T.c.conversation_id == conversation_id)
        )
        return ConversationDetail(conversation=_conversation_dto(row, len(turns)), turns=turns)


# -- turns ------------------------------------------------------------------------------------


def _validate_context_scope(session: Session, project_id: UUID, context: ChatContext) -> None:
    """UI selection narrows context and never widens scope: a wellbore of another project is
    rejected as if it did not exist."""
    if context.wellbore_id is not None:
        found = session.execute(
            select(m.wellbore.c.wellbore_id).where(
                m.wellbore.c.project_id == project_id,
                m.wellbore.c.wellbore_id == context.wellbore_id,
            )
        ).first()
        if found is None:
            raise ContractError(
                ErrorCode.VALIDATION_ERROR, "context wellbore is not in this project", 422
            )


def create_turn(
    factory: sessionmaker[Session],
    project_id: UUID,
    conversation_id: UUID,
    request: CreateTurnRequest,
) -> tuple[ChatTurn, bool]:
    """Queue a turn (user message + job row in one transaction). Returns ``(turn, created)``; a
    repeated idempotency key with the same request returns the original turn."""
    digest = request_hash(request)
    with session_scope(factory) as s:
        _require_conversation(s, project_id, conversation_id, lock=True)
        if request.idempotency_key is not None:
            prior = s.execute(
                select(T).where(
                    T.c.conversation_id == conversation_id,
                    T.c.idempotency_key == request.idempotency_key,
                )
            ).one_or_none()
            if prior is not None:
                if prior.request_hash != digest:
                    raise _conflict("idempotency key was used with a different request")
                [existing] = _turns(s, T.c.turn_id == prior.turn_id)
                return existing, False
        _validate_context_scope(s, project_id, request.context)
        busy = s.execute(
            select(func.count())
            .select_from(T)
            .where(T.c.conversation_id == conversation_id, T.c.state.in_(_IN_FLIGHT))
        ).scalar_one()
        if busy:
            raise _conflict("the previous turn of this conversation is still running")
        seq = (
            s.execute(
                select(func.coalesce(func.max(T.c.seq), 0)).where(
                    T.c.conversation_id == conversation_id
                )
            ).scalar_one()
            + 1
        )
        if seq > MAX_TURNS_PER_CONVERSATION:
            raise _conflict("this conversation reached its turn limit; start a new one")
        try:
            turn_id = s.execute(
                insert(T)
                .values(
                    project_id=project_id,
                    conversation_id=conversation_id,
                    seq=seq,
                    state=ChatRunState.QUEUED.value,
                    context=request.context.model_dump(mode="json", exclude_none=True),
                    idempotency_key=request.idempotency_key,
                    request_hash=digest,
                )
                .returning(T.c.turn_id)
            ).scalar_one()
        except IntegrityError as exc:  # concurrent duplicate key: serialized by the row lock
            raise _conflict("turn could not be queued") from exc
        s.execute(
            insert(G).values(
                project_id=project_id,
                conversation_id=conversation_id,
                turn_id=turn_id,
                role="user",
                text=request.message,
            )
        )
        s.execute(
            update(C)
            .where(C.c.conversation_id == conversation_id)
            .values(
                updated_at=_now(),
                title=func.coalesce(C.c.title, request.message.strip()[:TITLE_CHARS]),
            )
        )
        [created] = _turns(s, T.c.turn_id == turn_id)
        return created, True


def get_turn(
    factory: sessionmaker[Session], project_id: UUID, conversation_id: UUID, turn_id: UUID
) -> ChatTurn:
    with session_scope(factory) as s:
        found = _turns(
            s,
            and_(
                T.c.project_id == project_id,
                T.c.conversation_id == conversation_id,
                T.c.turn_id == turn_id,
            ),
        )
        if not found:
            raise _not_found("turn")
        return found[0]


def cancel_turn(
    factory: sessionmaker[Session], project_id: UUID, conversation_id: UUID, turn_id: UUID
) -> ChatTurn:
    """Queued turns cancel at once; a running turn gets ``cancel_requested`` and the worker stops
    it. A terminal turn is returned unchanged (idempotent)."""
    failure = ChatFailure(
        code=ChatFailureCode.CANCELLED, message="cancelled by the user", retryable=True
    ).model_dump(mode="json")
    with session_scope(factory) as s:
        scope = and_(
            T.c.project_id == project_id,
            T.c.conversation_id == conversation_id,
            T.c.turn_id == turn_id,
        )
        row = s.execute(select(T.c.state).where(scope).with_for_update()).one_or_none()
        if row is None:
            raise _not_found("turn")
        if row.state == ChatRunState.QUEUED.value:
            s.execute(
                update(T)
                .where(scope)
                .values(
                    state=ChatRunState.CANCELLED.value,
                    failure=failure,
                    cancel_requested=True,
                    completed_at=_now(),
                )
            )
        elif row.state == ChatRunState.RUNNING.value:
            s.execute(update(T).where(scope).values(cancel_requested=True))
        [out] = _turns(s, T.c.turn_id == turn_id)
        return out


# -- worker side ------------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryItem:
    role: ChatRole
    text: str


@dataclass(frozen=True)
class ClaimedTurn:
    turn_id: UUID
    project_id: UUID
    conversation_id: UUID
    message: str
    context: ChatContext
    history: tuple[HistoryItem, ...]


def _answer_text(answer: ChatAnswer) -> str:
    parts = [b.root.text for b in answer.blocks if b.root.kind == "text"]
    return "\n".join(parts)[:4000]


def claim_next(factory: sessionmaker[Session], owner: str, lease_s: float) -> ClaimedTurn | None:
    with session_scope(factory) as s:
        row = s.execute(
            select(T.c.turn_id, T.c.project_id, T.c.conversation_id, T.c.seq, T.c.context)
            .where(T.c.state == ChatRunState.QUEUED.value, T.c.cancel_requested.is_(False))
            .order_by(T.c.created_at, T.c.turn_id)
            .limit(1)
            .with_for_update(skip_locked=True)
        ).first()
        if row is None:
            return None
        s.execute(
            update(T)
            .where(T.c.turn_id == row.turn_id)
            .values(
                state=ChatRunState.RUNNING.value,
                lease_owner=owner,
                lease_expires_at=_now() + timedelta(seconds=lease_s),
                started_at=_now(),
            )
        )
        message = s.execute(
            select(G.c.text).where(G.c.turn_id == row.turn_id, G.c.role == "user")
        ).scalar_one()
        prior = _turns(
            s,
            and_(
                T.c.conversation_id == row.conversation_id,
                T.c.seq < row.seq,
                T.c.seq >= max(1, row.seq - MAX_HISTORY_TURNS),
            ),
        )
        history: list[HistoryItem] = []
        for turn in prior:
            if turn.user_message.text:
                history.append(HistoryItem(ChatRole.USER, turn.user_message.text))
            answer = turn.assistant_message.answer if turn.assistant_message else None
            if answer is not None and turn.state is ChatRunState.COMPLETED:
                text = _answer_text(answer)
                if text:
                    history.append(HistoryItem(ChatRole.ASSISTANT, text))
        return ClaimedTurn(
            turn_id=row.turn_id,
            project_id=row.project_id,
            conversation_id=row.conversation_id,
            message=message,
            context=ChatContext.model_validate(row.context or {}),
            history=tuple(history),
        )


def extend_lease(factory: sessionmaker[Session], turn_id: UUID, owner: str, lease_s: float) -> bool:
    with session_scope(factory) as s:
        res = s.execute(
            update(T)
            .where(
                T.c.turn_id == turn_id,
                T.c.state == ChatRunState.RUNNING.value,
                T.c.lease_owner == owner,
            )
            .values(lease_expires_at=_now() + timedelta(seconds=lease_s))
        )
        return bool(cast("CursorResult[Any]", res).rowcount)


def cancel_requested(factory: sessionmaker[Session], turn_id: UUID) -> bool:
    with session_scope(factory) as s:
        flag = s.execute(
            select(T.c.cancel_requested).where(T.c.turn_id == turn_id)
        ).scalar_one_or_none()
        return bool(flag)


def finalize(
    factory: sessionmaker[Session],
    claim: ClaimedTurn,
    owner: str,
    *,
    state: ChatRunState,
    answer: ChatAnswer | None,
    failure: ChatFailure | None,
    usage: ChatUsage,
    tool_calls: list[ChatToolCallSummary],
) -> bool:
    """Terminal write (turn row + optional assistant message) in one transaction, fenced by the
    lease owner. Returns False when the turn is no longer this worker's (recovered/purged)."""
    if state not in TERMINAL_STATES:
        raise ValueError("finalize needs a terminal state")
    with session_scope(factory) as s:
        res = s.execute(
            update(T)
            .where(
                T.c.turn_id == claim.turn_id,
                T.c.state == ChatRunState.RUNNING.value,
                T.c.lease_owner == owner,
            )
            .values(
                state=state.value,
                failure=failure.model_dump(mode="json") if failure else None,
                usage=usage.model_dump(mode="json", exclude_none=True),
                tool_calls=[c.model_dump(mode="json") for c in tool_calls],
                lease_owner=None,
                lease_expires_at=None,
                completed_at=_now(),
            )
        )
        if not cast("CursorResult[Any]", res).rowcount:
            return False
        if answer is not None:
            s.execute(
                insert(G).values(
                    project_id=claim.project_id,
                    conversation_id=claim.conversation_id,
                    turn_id=claim.turn_id,
                    role="assistant",
                    answer=answer.model_dump(mode="json", by_alias=True),
                )
            )
        s.execute(
            update(C).where(C.c.conversation_id == claim.conversation_id).values(updated_at=_now())
        )
        return True


def recover(factory: sessionmaker[Session], is_dead_owner: Any) -> list[UUID]:
    """A running turn whose lease lapsed or whose worker died is ``failed/interrupted`` (never
    resumed, because a resumed turn would call the provider a second time)."""
    failure = ChatFailure(
        code=ChatFailureCode.INTERRUPTED,
        message="the worker stopped before this turn finished; ask again",
        retryable=True,
    ).model_dump(mode="json")
    out: list[UUID] = []
    with session_scope(factory) as s:
        now = s.execute(select(_now())).scalar_one()
        rows = s.execute(
            select(T.c.turn_id, T.c.lease_owner, T.c.lease_expires_at)
            .where(T.c.state == ChatRunState.RUNNING.value)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            lapsed = row.lease_expires_at is None or row.lease_expires_at < now
            dead = row.lease_owner is not None and is_dead_owner(row.lease_owner)
            if lapsed or dead:
                s.execute(
                    update(T)
                    .where(T.c.turn_id == row.turn_id)
                    .values(
                        state=ChatRunState.FAILED.value,
                        failure=failure,
                        lease_owner=None,
                        lease_expires_at=None,
                        completed_at=now,
                    )
                )
                out.append(row.turn_id)
    return out


__all__ = [
    "ClaimedTurn",
    "HistoryItem",
    "cancel_requested",
    "cancel_turn",
    "claim_next",
    "create_conversation",
    "create_turn",
    "extend_lease",
    "finalize",
    "get_conversation",
    "get_turn",
    "list_conversations",
    "recover",
    "request_hash",
]

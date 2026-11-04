"""Project assistant chat tables (migration 0020 is authoritative).

Conversations belong to one project; turns and messages carry ``project_id`` and reference their
conversation through a composite ``(project_id, conversation_id)`` key, so a row can never point
into another project. A turn is the persisted job the UI polls: ``state`` moves
``queued -> running -> terminal`` through conditional (owner-fenced) updates only.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from fieldlens.persistence.models import metadata

TURN_STATES = ("queued", "running", "completed", "failed", "cancelled", "refused", "truncated")
MAX_ANSWER_JSON_BYTES = 1_048_576

chat_conversation = Table(
    "chat_conversation",
    metadata,
    Column(
        "conversation_id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("project_id", UUID(as_uuid=True), ForeignKey("project.project_id"), nullable=False),
    Column("title", String(256), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    UniqueConstraint("project_id", "conversation_id", name="uq_chat_conversation_project_scope"),
    CheckConstraint("title IS NULL OR char_length(btrim(title)) >= 1", name="title_nonblank"),
    Index("ix_chat_conversation_project_updated", "project_id", text("updated_at DESC")),
)

chat_turn = Table(
    "chat_turn",
    metadata,
    Column(
        "turn_id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("seq", Integer, nullable=False),
    Column("state", String(16), nullable=False, server_default=text("'queued'")),
    Column("context", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("idempotency_key", String(128), nullable=True),
    Column("request_hash", String(64), nullable=True),
    Column("failure", JSONB, nullable=True),
    Column("usage", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    Column("tool_calls", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("lease_owner", Text, nullable=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("cancel_requested", Boolean, nullable=False, server_default=text("false")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("started_at", DateTime(timezone=True), nullable=True),
    Column("completed_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(
        ["project_id", "conversation_id"],
        ["chat_conversation.project_id", "chat_conversation.conversation_id"],
        name="fk_chat_turn_conversation_scope",
    ),
    UniqueConstraint("conversation_id", "seq", name="uq_chat_turn_seq"),
    UniqueConstraint("project_id", "turn_id", name="uq_chat_turn_project_scope"),
    CheckConstraint(
        "state IN (" + ", ".join(f"'{s}'" for s in TURN_STATES) + ")", name="state_known"
    ),
    CheckConstraint("seq >= 1", name="seq_positive"),
    CheckConstraint(
        "(state IN ('queued', 'running')) = (completed_at IS NULL)", name="completed_iff_terminal"
    ),
    Index(
        "uq_chat_turn_idempotency",
        "conversation_id",
        "idempotency_key",
        unique=True,
        postgresql_where=text("idempotency_key IS NOT NULL"),
    ),
    Index("ix_chat_turn_queue", "created_at", postgresql_where=text("state = 'queued'")),
)

chat_message = Table(
    "chat_message",
    metadata,
    Column(
        "message_id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    ),
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("turn_id", UUID(as_uuid=True), nullable=False),
    Column("role", String(16), nullable=False),
    Column("text", Text, nullable=True),
    Column("answer", JSONB, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    ForeignKeyConstraint(
        ["project_id", "conversation_id"],
        ["chat_conversation.project_id", "chat_conversation.conversation_id"],
        name="fk_chat_message_conversation_scope",
    ),
    ForeignKeyConstraint(
        ["project_id", "turn_id"],
        ["chat_turn.project_id", "chat_turn.turn_id"],
        name="fk_chat_message_turn_scope",
    ),
    UniqueConstraint("turn_id", "role", name="uq_chat_message_turn_role"),
    CheckConstraint("role IN ('user', 'assistant')", name="role_known"),
    CheckConstraint(
        "(role = 'user' AND text IS NOT NULL AND char_length(btrim(text)) >= 1 "
        "AND answer IS NULL) OR (role = 'assistant' AND text IS NULL AND answer IS NOT NULL)",
        name="role_shape",
    ),
    CheckConstraint(
        f"answer IS NULL OR octet_length(answer::text) <= {MAX_ANSWER_JSON_BYTES}",
        name="answer_bounded",
    ),
)

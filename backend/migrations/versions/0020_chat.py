"""Project assistant chat: conversations, turns (polled jobs) and messages (TASK-103, FL-027).

Revision ID: 0020_chat
Revises: 0019_asset_spec

Every row carries ``project_id``; children reference their conversation/turn through composite
project-scoped keys. The project purge lists the three tables (``chat_message``, ``chat_turn``,
``chat_conversation``). No spend column exists: chat usage is reported only (owner decision D4).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_chat"
down_revision: str | None = "0019_asset_spec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

F = op.f
UUID = postgresql.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)
STATES = ("queued", "running", "completed", "failed", "cancelled", "refused", "truncated")


def upgrade() -> None:
    op.create_table(
        "chat_conversation",
        sa.Column(
            "conversation_id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("title", sa.String(256), nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("conversation_id", name=F("pk_chat_conversation")),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.project_id"],
            name=F("fk_chat_conversation_project_id_project"),
        ),
        sa.UniqueConstraint(
            "project_id", "conversation_id", name=F("uq_chat_conversation_project_scope")
        ),
        sa.CheckConstraint(
            "title IS NULL OR char_length(btrim(title)) >= 1",
            name=F("ck_chat_conversation_title_nonblank"),
        ),
    )
    op.create_index(
        "ix_chat_conversation_project_updated",
        "chat_conversation",
        ["project_id", sa.text("updated_at DESC")],
    )
    op.create_table(
        "chat_turn",
        sa.Column("turn_id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("state", sa.String(16), server_default=sa.text("'queued'"), nullable=False),
        sa.Column(
            "context", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("failure", postgresql.JSONB, nullable=True),
        sa.Column("usage", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column(
            "tool_calls", postgresql.JSONB, server_default=sa.text("'[]'::jsonb"), nullable=False
        ),
        sa.Column("lease_owner", sa.Text, nullable=True),
        sa.Column("lease_expires_at", TS, nullable=True),
        sa.Column("cancel_requested", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", TS, nullable=True),
        sa.Column("completed_at", TS, nullable=True),
        sa.PrimaryKeyConstraint("turn_id", name=F("pk_chat_turn")),
        sa.ForeignKeyConstraint(
            ["project_id", "conversation_id"],
            ["chat_conversation.project_id", "chat_conversation.conversation_id"],
            name=F("fk_chat_turn_conversation_scope"),
        ),
        sa.UniqueConstraint("conversation_id", "seq", name=F("uq_chat_turn_seq")),
        sa.UniqueConstraint("project_id", "turn_id", name=F("uq_chat_turn_project_scope")),
        sa.CheckConstraint(
            "state IN (" + ", ".join(f"'{s}'" for s in STATES) + ")",
            name=F("ck_chat_turn_state_known"),
        ),
        sa.CheckConstraint("seq >= 1", name=F("ck_chat_turn_seq_positive")),
        sa.CheckConstraint(
            "(state IN ('queued', 'running')) = (completed_at IS NULL)",
            name=F("ck_chat_turn_completed_iff_terminal"),
        ),
    )
    op.create_index(
        "uq_chat_turn_idempotency",
        "chat_turn",
        ["conversation_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.create_index(
        "ix_chat_turn_queue",
        "chat_turn",
        ["created_at"],
        postgresql_where=sa.text("state = 'queued'"),
    )
    op.create_table(
        "chat_message",
        sa.Column("message_id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("project_id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("turn_id", UUID, nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("answer", postgresql.JSONB, nullable=True),
        sa.Column("created_at", TS, server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("message_id", name=F("pk_chat_message")),
        sa.ForeignKeyConstraint(
            ["project_id", "conversation_id"],
            ["chat_conversation.project_id", "chat_conversation.conversation_id"],
            name=F("fk_chat_message_conversation_scope"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id", "turn_id"],
            ["chat_turn.project_id", "chat_turn.turn_id"],
            name=F("fk_chat_message_turn_scope"),
        ),
        sa.UniqueConstraint("turn_id", "role", name=F("uq_chat_message_turn_role")),
        sa.CheckConstraint("role IN ('user', 'assistant')", name=F("ck_chat_message_role_known")),
        sa.CheckConstraint(
            "(role = 'user' AND text IS NOT NULL AND char_length(btrim(text)) >= 1 "
            "AND answer IS NULL) OR (role = 'assistant' AND text IS NULL AND answer IS NOT NULL)",
            name=F("ck_chat_message_role_shape"),
        ),
        sa.CheckConstraint(
            "answer IS NULL OR octet_length(answer::text) <= 1048576",
            name=F("ck_chat_message_answer_bounded"),
        ),
    )


def downgrade() -> None:
    op.drop_table("chat_message")
    op.drop_index("ix_chat_turn_queue", table_name="chat_turn")
    op.drop_index("uq_chat_turn_idempotency", table_name="chat_turn")
    op.drop_table("chat_turn")
    op.drop_index("ix_chat_conversation_project_updated", table_name="chat_conversation")
    op.drop_table("chat_conversation")

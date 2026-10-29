"""Project persistence. Every lookup is qualified by ``project_id``; nothing here joins
another project's rows, and a project name/description is stored as opaque text."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import RowMapping, func, insert, select, tuple_, update
from sqlalchemy.orm import Session

from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.identity import Project
from fieldlens.persistence.models import project as project_table

_COLUMNS = (
    project_table.c.project_id,
    project_table.c.name,
    project_table.c.description,
    project_table.c.created_at,
    project_table.c.updated_at,
    project_table.c.latest_source_revision_id,
    project_table.c.active_model_revision_id,
)


def _to_project(row: RowMapping) -> Project:
    return Project.model_validate(dict(row))


def encode_cursor(created_at: datetime, project_id: UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(project_id)], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        created_raw, id_raw = json.loads(base64.urlsafe_b64decode(padded.encode()))
        created_at = datetime.fromisoformat(created_raw)
        if created_at.tzinfo is None:
            raise ValueError("naive cursor timestamp")
        return created_at, UUID(id_raw)
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ContractError(ErrorCode.VALIDATION_ERROR, "cursor is malformed", 422) from exc


def list_page(session: Session, limit: int, cursor: str | None) -> tuple[list[Project], str | None]:
    """Newest first with a (created_at, project_id) keyset; one extra row detects a next page."""
    query = select(*_COLUMNS)
    if cursor is not None:
        created_at, project_id = decode_cursor(cursor)
        query = query.where(
            tuple_(project_table.c.created_at, project_table.c.project_id)
            < tuple_(created_at, project_id)
        )
    query = query.order_by(project_table.c.created_at.desc(), project_table.c.project_id.desc())
    rows = session.execute(query.limit(limit + 1)).mappings().all()
    items = [_to_project(r) for r in rows[:limit]]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].project_id)
        if len(rows) > limit and items
        else None
    )
    return items, next_cursor


def get(session: Session, project_id: UUID, *, for_update: bool = False) -> Project | None:
    query = select(*_COLUMNS).where(project_table.c.project_id == project_id)
    if for_update:
        query = query.with_for_update()
    row = session.execute(query).mappings().one_or_none()
    return _to_project(row) if row is not None else None


def create(session: Session, name: str, description: str) -> Project:
    row = (
        session.execute(
            insert(project_table).values(name=name, description=description).returning(*_COLUMNS)
        )
        .mappings()
        .one()
    )
    return _to_project(row)


def update_fields(session: Session, project_id: UUID, values: dict[str, str]) -> Project:
    row = (
        session.execute(
            update(project_table)
            .where(project_table.c.project_id == project_id)
            .values(**values, updated_at=func.clock_timestamp())
            .returning(*_COLUMNS)
        )
        .mappings()
        .one()
    )
    return _to_project(row)

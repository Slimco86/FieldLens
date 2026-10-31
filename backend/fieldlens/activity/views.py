"""Read models for the activity log. Every query is qualified by ``project_id``."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from fieldlens.contracts.activity import (
    AgentStep,
    AgentUnitDetail,
    AgentUnitPage,
    AgentUnitQuery,
    AgentUnitSummary,
    AgentUsage,
)
from fieldlens.contracts.context import PageInfo
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import EvidenceLink
from fieldlens.persistence import models as m
from fieldlens.projects.repository import decode_cursor, encode_cursor

_T = m.agent_work_unit


def _summary(row: Any) -> AgentUnitSummary:
    return AgentUnitSummary(
        unit_id=row["unit_id"],
        project_id=row["project_id"],
        source_revision_id=row["source_revision_id"],
        unit_key=row["unit_key"],
        question=row["question"],
        state=row["state"],
        stop_reason=row["stop_reason"],
        stop_detail=row["stop_detail"],
        attempt_count=row["attempt_count"],
        step_count=row["step_count"],
        tool_call_count=row["tool_call_count"],
        candidate_count=row["candidate_count"],
        usage=AgentUsage(
            input_tokens=row["input_tokens"],
            cached_input_tokens=row["cached_input_tokens"],
            output_tokens=row["output_tokens"],
            cost_usd=Decimal(row["cost_usd"]),
        ),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        finished_at=row["finished_at"],
    )


def require_project(session: Session, project_id: UUID) -> None:
    found = session.execute(
        select(m.project.c.project_id).where(m.project.c.project_id == project_id)
    ).first()
    if found is None:
        raise ContractError(ErrorCode.NOT_FOUND, "project not found", 404)


def list_units(session: Session, project_id: UUID, query: AgentUnitQuery) -> AgentUnitPage:
    require_project(session, project_id)
    stmt = select(_T).where(_T.c.project_id == project_id)
    if query.state is not None:
        stmt = stmt.where(_T.c.state == query.state.value)
    if query.source_revision_id is not None:
        stmt = stmt.where(_T.c.source_revision_id == query.source_revision_id)
    if query.cursor is not None:
        created_at, unit_id = decode_cursor(query.cursor)
        stmt = stmt.where(tuple_(_T.c.created_at, _T.c.unit_id) < tuple_(created_at, unit_id))
    rows = (
        session.execute(
            stmt.order_by(_T.c.created_at.desc(), _T.c.unit_id.desc()).limit(query.limit + 1)
        )
        .mappings()
        .all()
    )
    items = [_summary(r) for r in rows[: query.limit]]
    more = len(rows) > query.limit and items
    return AgentUnitPage(
        items=items,
        page=PageInfo(
            limit=query.limit,
            next_cursor=encode_cursor(items[-1].created_at, items[-1].unit_id) if more else None,
        ),
    )


def get_unit(session: Session, project_id: UUID, unit_id: UUID) -> AgentUnitDetail:
    require_project(session, project_id)
    row = (
        session.execute(select(_T).where(_T.c.project_id == project_id, _T.c.unit_id == unit_id))
        .mappings()
        .first()
    )
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "agent unit not found", 404)
    steps = (
        session.execute(
            select(m.agent_step)
            .where(m.agent_step.c.project_id == project_id, m.agent_step.c.unit_id == unit_id)
            .order_by(m.agent_step.c.step_no)
        )
        .mappings()
        .all()
    )
    return AgentUnitDetail(
        unit=_summary(row),
        steps=[
            AgentStep(
                step_id=r["step_id"],
                step_no=r["step_no"],
                kind=r["kind"],
                outcome=r["outcome"],
                tool_name=r["tool_name"],
                summary=r["summary"],
                detail=r["detail"],
                evidence=[EvidenceLink.model_validate(e) for e in r["evidence"]],
                truncated=r["truncated"],
                created_at=r["created_at"],
            )
            for r in steps
        ],
    )

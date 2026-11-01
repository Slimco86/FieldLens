"""Fenced candidate persistence and read models (project-scoped)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.activity.service import FenceLost, UnitFinalized, UnitHandle
from fieldlens.contracts.candidates import (
    CandidateQuery,
    ExtractionCandidate,
    ExtractionCandidatePage,
)
from fieldlens.contracts.context import PageInfo
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import EvidenceLink
from fieldlens.persistence import models as m
from fieldlens.persistence.session import session_scope
from fieldlens.projects.repository import decode_cursor, encode_cursor

from .tables import extraction_candidate as T


def insert_candidates(
    factory: sessionmaker[Session], handle: UnitHandle, rows: list[dict[str, Any]]
) -> int:
    """Insert rows for a running unit this attempt still owns. A replayed ``candidate_key`` is
    skipped (fenced retry never duplicates). Returns the number newly inserted."""
    if not rows:
        return 0
    with session_scope(factory) as s:
        unit = (
            s.execute(
                select(m.agent_work_unit.c.fence_counter, m.agent_work_unit.c.state)
                .where(
                    m.agent_work_unit.c.project_id == handle.project_id,
                    m.agent_work_unit.c.unit_id == handle.unit_id,
                )
                .with_for_update()
            )
            .mappings()
            .one()
        )
        if unit["fence_counter"] != handle.fence:
            raise FenceLost("attempt superseded")
        if unit["state"] != "running":
            raise UnitFinalized(f"unit is {unit['state']}")
        stmt = (
            pg_insert(T)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["unit_id", "candidate_key"])
            .returning(T.c.candidate_id)
        )
        return len(s.execute(stmt).all())


def _candidate(row: Any) -> ExtractionCandidate:
    link = EvidenceLink.model_validate(
        {
            "document_id": row["document_id"],
            "source_revision_id": row["source_revision_id"],
            "locator": row["locator"],
        }
    )
    return ExtractionCandidate.model_validate(
        {
            "candidate_id": row["candidate_id"],
            "project_id": row["project_id"],
            "unit_id": row["unit_id"],
            "source_revision_id": row["source_revision_id"],
            "document_id": row["document_id"],
            "wellbore_id": row["wellbore_id"],
            "subject": row["subject"],
            "method": row["method"],
            "evidence_class": row["evidence_class"],
            "validation_state": row["validation_state"],
            "state": row["state"],
            "label": row["label"],
            "reason_codes": list(row["reason_codes"]),
            "validator_results": row["validator_results"],
            "attributes": row["attributes"],
            "quote": row["quote"],
            "evidence": link,
            "conflicts_with_record_id": row["conflicts_with_record_id"],
            "model_id": row["model_id"],
            "prompt_version": row["prompt_version"],
            "harness_version": row["harness_version"],
            "created_at": row["created_at"],
        }
    )


def list_candidates(
    session: Session,
    project_id: UUID,
    query: CandidateQuery,
    *,
    document_id: UUID | None = None,
    unit_id: UUID | None = None,
) -> ExtractionCandidatePage:
    found = session.execute(
        select(m.project.c.project_id).where(m.project.c.project_id == project_id)
    ).first()
    if found is None:
        raise ContractError(ErrorCode.NOT_FOUND, "project not found", 404)
    stmt = select(T).where(T.c.project_id == project_id)
    doc = document_id or query.document_id
    if doc is not None:
        stmt = stmt.where(T.c.document_id == doc)
    if unit_id is not None:
        stmt = stmt.where(T.c.unit_id == unit_id)
    if query.state is not None:
        stmt = stmt.where(T.c.state == query.state.value)
    if query.method is not None:
        stmt = stmt.where(T.c.method == query.method.value)
    if query.cursor is not None:
        created_at, candidate_id = decode_cursor(query.cursor)
        stmt = stmt.where(
            tuple_(T.c.created_at, T.c.candidate_id) < tuple_(created_at, candidate_id)
        )
    rows = (
        session.execute(
            stmt.order_by(T.c.created_at.desc(), T.c.candidate_id.desc()).limit(query.limit + 1)
        )
        .mappings()
        .all()
    )
    items = [_candidate(r) for r in rows[: query.limit]]
    more = len(rows) > query.limit and items
    return ExtractionCandidatePage(
        items=items,
        page=PageInfo(
            limit=query.limit,
            next_cursor=encode_cursor(items[-1].created_at, items[-1].candidate_id)
            if more
            else None,
        ),
    )


def document_in_project(session: Session, project_id: UUID, document_id: UUID) -> None:
    row = session.execute(
        select(m.source_document.c.document_id).where(
            m.source_document.c.project_id == project_id,
            m.source_document.c.document_id == document_id,
        )
    ).first()
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "document not found", 404)

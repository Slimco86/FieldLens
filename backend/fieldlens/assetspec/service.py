"""Persistence and service for wellbore asset specs.

No draft/accept gate: the latest VALID generation is ``current``; an invalid or empty generation is
rejected (422 with findings) and leaves the current one untouched. Earlier valid generations stay as
``superseded`` history (revision number).

MERGE/REVERT HOOK POINT: :func:`invalidate_current` is the one function the identity-merge apply /
revert code (TASK-076) calls inside its own transaction for each affected wellbore id; it marks the
current spec ``invalidated`` (history is kept) so a stale scene is never shown. It is not wired yet.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from fieldlens.contracts.asset_spec import (
    AssetSpecGenerateRequest,
    AssetSpecHistory,
    FindingCode,
    SpecFinding,
    SpecState,
    VisualAssetSpecRecord,
)
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.persistence import models as m

from . import designer
from .tables import wellbore_asset_spec as T
from .validator import validate_spec

_MD_UNIT_M = 1.0


def _record(row: Any) -> VisualAssetSpecRecord:
    return VisualAssetSpecRecord.model_validate(
        {
            "spec_id": row["spec_id"],
            "revision": row["revision"],
            "state": row["state"],
            "created_at": row["created_at"],
            "spec": row["spec"],
        }
    )


def _require_wellbore(session: Session, project_id: UUID, wellbore_id: UUID) -> None:
    found = session.execute(
        select(m.wellbore.c.wellbore_id).where(
            m.wellbore.c.project_id == project_id, m.wellbore.c.wellbore_id == wellbore_id
        )
    ).first()
    if found is None:
        raise ContractError(ErrorCode.NOT_FOUND, "wellbore not found", 404)


def get_current(session: Session, project_id: UUID, wellbore_id: UUID) -> VisualAssetSpecRecord:
    _require_wellbore(session, project_id, wellbore_id)
    row = (
        session.execute(
            select(T).where(
                T.c.project_id == project_id,
                T.c.wellbore_id == wellbore_id,
                T.c.state == SpecState.CURRENT.value,
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "no asset spec for this wellbore yet", 404)
    return _record(row)


def history(session: Session, project_id: UUID, wellbore_id: UUID) -> AssetSpecHistory:
    _require_wellbore(session, project_id, wellbore_id)
    rows = (
        session.execute(
            select(T)
            .where(T.c.project_id == project_id, T.c.wellbore_id == wellbore_id)
            .order_by(T.c.revision.desc())
            .limit(200)
        )
        .mappings()
        .all()
    )
    return AssetSpecHistory(items=[_record(r) for r in rows])


def _reject(findings: list[SpecFinding], message: str) -> ContractError:
    return ContractError(
        ErrorCode.VALIDATION_ERROR,
        message,
        422,
        {"findings": [f.model_dump(mode="json") for f in findings][:50]},
    )


def store_validated(
    session: Session,
    project_id: UUID,
    wellbore_id: UUID,
    raw: dict[str, Any],
    *,
    md_range_m: tuple[float, float] | None,
) -> VisualAssetSpecRecord:
    """Validate ``raw`` and, only if usable, make it the current revision (atomic)."""
    outcome = validate_spec(raw, md_range_m=md_range_m)
    spec = outcome.spec
    if spec is None:
        raise _reject(outcome.findings, "the generated spec is not valid")
    if spec.project_id != project_id or spec.wellbore_id != wellbore_id:
        raise _reject(
            [SpecFinding(code=FindingCode.HEADER_INVALID, message="spec targets another wellbore")],
            "the generated spec is not valid",
        )
    if not spec.components:
        raise _reject(outcome.findings, "no usable components; the current spec is unchanged")
    # serialize concurrent generations for the project (also blocks a concurrent purge)
    session.execute(
        select(m.project.c.project_id).where(m.project.c.project_id == project_id).with_for_update()
    ).first()
    nxt = session.execute(
        select(func.coalesce(func.max(T.c.revision), 0) + 1).where(
            T.c.project_id == project_id, T.c.wellbore_id == wellbore_id
        )
    ).scalar_one()
    session.execute(
        update(T)
        .where(
            T.c.project_id == project_id,
            T.c.wellbore_id == wellbore_id,
            T.c.state == SpecState.CURRENT.value,
        )
        .values(state=SpecState.SUPERSEDED.value)
    )
    row = (
        session.execute(
            T.insert()
            .values(
                project_id=project_id,
                wellbore_id=wellbore_id,
                revision=nxt,
                state=SpecState.CURRENT.value,
                source_revision=spec.source_revision,
                generator_provider=spec.generator.provider,
                generator_model=spec.generator.model,
                spec=spec.model_dump(mode="json"),
            )
            .returning(*T.c)
        )
        .mappings()
        .one()
    )
    return _record(row)


def generate_stub(
    session: Session, project_id: UUID, wellbore_id: UUID, body: AssetSpecGenerateRequest
) -> VisualAssetSpecRecord:
    _require_wellbore(session, project_id, wellbore_id)
    raw = designer.design(session, project_id, wellbore_id)
    rng = None if body.md_min is None or body.md_max is None else (body.md_min, body.md_max)
    return store_validated(session, project_id, wellbore_id, raw, md_range_m=rng)


def invalidate_current(session: Session, project_id: UUID, wellbore_id: UUID) -> bool:
    """Merge/revert hook (see module docstring). True when a current spec was invalidated."""
    res = session.execute(
        update(T)
        .where(
            T.c.project_id == project_id,
            T.c.wellbore_id == wellbore_id,
            T.c.state == SpecState.CURRENT.value,
        )
        .values(state=SpecState.INVALIDATED.value)
    )
    return bool(getattr(res, "rowcount", 0))

"""Persistence and service for wellbore asset specs.

No draft/accept gate: the latest VALID generation is ``current``; an invalid or empty generation is
rejected (422 with findings) and leaves the current one untouched. Earlier valid generations stay as
``superseded`` history (revision number).

MERGE/REVERT HOOK POINT: :func:`invalidate_current` is the one function the identity-merge apply /
revert code (TASK-076) calls inside its own transaction for each affected wellbore id; it marks the
current spec ``invalidated`` (history is kept) so a stale scene is never shown. It is not wired yet.
"""

from __future__ import annotations

import copy
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
from .readable import READABLE_EVIDENCE_FIELDS, enrich_specs
from .tables import wellbore_asset_spec as T
from .validator import validate_spec

_MD_UNIT_M = 1.0


def _records(session: Session, project_id: UUID, rows: list[Any]) -> list[VisualAssetSpecRecord]:
    """Stored rows as records with readable evidence composed at read time (2 batched queries)."""
    specs = enrich_specs(session, project_id, [r["spec"] for r in rows])
    return [
        VisualAssetSpecRecord.model_validate(
            {
                "spec_id": r["spec_id"],
                "revision": r["revision"],
                "state": r["state"],
                "created_at": r["created_at"],
                "spec": spec,
            }
        )
        for r, spec in zip(rows, specs, strict=True)
    ]


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
    return _records(session, project_id, [row])[0]


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
    return AssetSpecHistory(items=_records(session, project_id, list(rows)))


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
    return store_validated_checked(
        session, project_id, wellbore_id, raw, md_range_m=md_range_m, skip_unchanged=False
    )[0]


def _stored(spec: dict[str, Any]) -> dict[str, Any]:
    """The spec as persisted: read-time evidence fields (filename/locator/statement) are never
    stored, so stored specs stay byte-compatible with those written before they existed."""
    for component in spec.get("components") or []:
        for ev in component.get("evidence") or []:
            for key in READABLE_EVIDENCE_FIELDS:
                ev.pop(key, None)
    return spec


def _content(spec: dict[str, Any]) -> tuple[Any, Any]:
    """What makes two specs the same design: components and findings (not times or run ids)."""
    stripped = _stored(copy.deepcopy(spec))
    return stripped.get("components"), stripped.get("findings")


def store_validated_checked(
    session: Session,
    project_id: UUID,
    wellbore_id: UUID,
    raw: dict[str, Any],
    *,
    md_range_m: tuple[float, float] | None,
    skip_unchanged: bool,
) -> tuple[VisualAssetSpecRecord, bool]:
    """As :func:`store_validated`; returns ``(record, created)``. With ``skip_unchanged`` a spec
    whose components/findings equal the current one's creates no revision (the current record is
    returned). A merge-invalidated or missing current spec is never "unchanged"."""
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
    if skip_unchanged:
        cur = (
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
        if cur is not None and _content(cur["spec"]) == _content(spec.model_dump(mode="json")):
            return _records(session, project_id, [cur])[0], False
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
                spec=_stored(spec.model_dump(mode="json")),
            )
            .returning(*T.c)
        )
        .mappings()
        .one()
    )
    return _records(session, project_id, [row])[0], True


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

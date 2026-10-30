"""Read models: persisted extraction rows -> contract DTOs (locators validated, ids attached)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldlens.contracts.context import PageInfo, SourceEventTime
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import Coverage, CoverageStatus, EvidenceLink, Locator
from fieldlens.contracts.extraction import (
    ExtractedAttribute,
    ExtractedRecord,
    ExtractedRecordPage,
    ExtractionError,
    ExtractionReport,
    ExtractionStatus,
    WellboreIdentity,
)
from fieldlens.contracts.quality import BlockedOperation, IssueCode, IssueSeverity, QualityIssue
from fieldlens.persistence import models as m
from fieldlens.profiles import registry

_PRODUCER = "fieldlens-native-profiles"


def _link(
    locator: dict[str, Any], document_id: UUID, revision_id: UUID, record_id: UUID | None = None
) -> EvidenceLink:
    loc = Locator.model_validate(
        {**locator, "document_id": document_id, "source_revision_id": revision_id}
    )
    return EvidenceLink(
        document_id=document_id, source_revision_id=revision_id, record_id=record_id, locator=loc
    )


def _time(raw: dict[str, Any] | None) -> SourceEventTime | None:
    if not raw:
        return None
    zone = raw.get("timezone")
    instant = None
    if zone and raw["precision"] == "instant":
        try:
            parsed = datetime.fromisoformat(raw["literal"].replace(" ", "T"))
            if parsed.tzinfo is not None:
                instant = parsed.astimezone(UTC)
        except ValueError:
            instant = None
    return SourceEventTime(
        literal=raw["literal"],
        precision=raw["precision"],
        timezone=zone,
        earliest_effective=instant,
        latest_effective=instant,
    )


def _coverage(raw: dict[str, Any] | None) -> Coverage | None:
    if raw is None:
        return None
    total, inspected = raw.get("total"), raw.get("inspected")
    complete = total is not None and inspected == total and not raw.get("reasons")
    reasons = list(raw.get("reasons") or [])
    status = (
        CoverageStatus.COMPLETE
        if complete
        else (CoverageStatus.PARTIAL if total is not None else CoverageStatus.UNKNOWN)
    )
    if status is CoverageStatus.UNKNOWN and inspected is not None and not reasons:
        reasons = ["total unknown"]
    if status is CoverageStatus.PARTIAL and not reasons and inspected != total:
        reasons = ["not all units inspected"]
    return Coverage(
        status=status,
        unit=raw.get("unit"),
        inspected=inspected,
        total=total,
        missing_ranges=list(raw.get("missing_ranges") or []),
        reasons=reasons,
    )


def _record(row: Any, revision_id: UUID) -> ExtractedRecord:
    doc = row.document_id
    attrs = [
        ExtractedAttribute(
            key=a["key"],
            original_text=a.get("original_text"),
            number=a.get("number"),
            text=a.get("text"),
            unit=a.get("unit"),
            unit_status=a["unit_status"],
            reference=a.get("reference"),
            unknown_reason=a.get("unknown_reason"),
            normalized_number=a.get("normalized_number"),
            normalized_unit=a.get("normalized_unit"),
            validation_state=a["validation_state"],
            evidence=_link(a["locator"], doc, revision_id, row.record_id),
        )
        for a in row.attributes
    ]
    return ExtractedRecord(
        record_id=row.record_id,
        ordinal=row.ordinal,
        kind=row.kind,
        subject={k: (None if v is None else str(v)) for k, v in row.subject.items()},
        effective_time=_time(row.effective_time),
        report_time=_time(row.report_time),
        validation_state=row.validation_state,
        evidence=_link(row.locator, doc, revision_id, row.record_id),
        attributes=attrs,
    )


def _blocked(raw: Any) -> list[BlockedOperation]:
    """Unique, known operations in stored order; unknown values are dropped, never a 500."""
    out: list[BlockedOperation] = []
    for value in raw or []:
        try:
            op = BlockedOperation(value)
        except ValueError:
            continue
        if op not in out:
            out.append(op)
    return out


def _fallback_issue(row: Any, run: Any) -> QualityIssue:
    """A stored finding that no longer validates is surfaced, not hidden and not fatal."""
    return QualityIssue(
        issue_id=row.issue_id,
        context={
            "kind": "source",
            "project_id": run.project_id,
            "source_revision_id": run.source_revision_id,
        },
        code=IssueCode.EXTRACTION_PARTIAL,
        severity=IssueSeverity.WARNING,
        message=f"A stored finding ({row.code}) could not be displayed in full: {row.message}"[
            :2000
        ],
        producer_name=run.profile_name or _PRODUCER,
        producer_version=run.profile_version or "0",
        producer_key=row.producer_key,
        created_at=row.created_at,
    )


def _issue(row: Any, run: Any, ids: dict[int, UUID]) -> QualityIssue:
    links = []
    for loc in row.locators:
        try:
            links.append(_link(loc, run.document_id, run.source_revision_id))
        except ValueError:
            continue
    return QualityIssue(
        issue_id=row.issue_id,
        context={
            "kind": "source",
            "project_id": run.project_id,
            "source_revision_id": run.source_revision_id,
        },
        code=IssueCode(row.code),
        severity=IssueSeverity(row.severity),
        message=row.message,
        record_ids=[ids[o] for o in row.record_ordinals if o in ids],
        attribute_keys=list(row.attribute_keys),
        evidence_links=links,
        blocked_operations=_blocked(row.blocked_operations),
        producer_name=run.profile_name or _PRODUCER,
        producer_version=run.profile_version or "0",
        producer_key=row.producer_key,
        created_at=row.created_at,
    )


def _current_run(session: Session, project_id: UUID, document_id: UUID) -> Any | None:
    return session.execute(
        select(m.extraction_run).where(
            m.extraction_run.c.project_id == project_id,
            m.extraction_run.c.document_id == document_id,
            m.extraction_run.c.superseded.is_(False),
        )
    ).first()


def require_document(session: Session, project_id: UUID, document_id: UUID) -> UUID:
    """Return the document's latest revision id or raise 404 (no cross-project leakage)."""
    row = session.execute(
        select(m.source_revision_document.c.source_revision_id)
        .join(
            m.source_revision,
            m.source_revision.c.source_revision_id
            == m.source_revision_document.c.source_revision_id,
        )
        .where(
            m.source_revision_document.c.project_id == project_id,
            m.source_revision_document.c.document_id == document_id,
        )
        .order_by(m.source_revision.c.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise ContractError(ErrorCode.NOT_FOUND, "document not found", 404)
    return UUID(str(row))


def report(session: Session, project_id: UUID, document_id: UUID) -> ExtractionReport:
    revision = require_document(session, project_id, document_id)
    run = _current_run(session, project_id, document_id)
    if run is None:
        return ExtractionReport(
            project_id=project_id, document_id=document_id, source_revision_id=revision
        )
    issue_rows = session.execute(
        select(m.extraction_issue)
        .where(m.extraction_issue.c.run_id == run.run_id)
        .order_by(
            m.extraction_issue.c.severity,
            m.extraction_issue.c.code,
            m.extraction_issue.c.producer_key,
        )
    ).all()
    wanted = sorted({o for r in issue_rows for o in (r.record_ordinals or [])})
    ids: dict[int, UUID] = {}
    for start in range(0, len(wanted), 1000):
        ids.update(
            {
                r.ordinal: r.record_id
                for r in session.execute(
                    select(m.extracted_record.c.ordinal, m.extracted_record.c.record_id).where(
                        m.extracted_record.c.run_id == run.run_id,
                        m.extracted_record.c.ordinal.in_(wanted[start : start + 1000]),
                    )
                )
            }
        )
    issues = []
    for r in issue_rows:
        try:
            issues.append(_issue(r, run, ids))
        except (ValueError, KeyError, TypeError):
            issues.append(_fallback_issue(r, run))
    current = registry.current_version(run.profile_name) if run.profile_name else None
    summary = run.summary or {}
    return ExtractionReport(
        project_id=project_id,
        document_id=document_id,
        source_revision_id=run.source_revision_id,
        run_id=run.run_id,
        status=ExtractionStatus(run.status),
        profile_name=run.profile_name,
        profile_version=run.profile_version,
        method=run.method,
        content_sha256=run.content_sha256,
        stale=current is not None and current != run.profile_version,
        attempt_no=run.attempt_no,
        coverage=_coverage(run.coverage),
        record_counts=dict(summary.get("record_counts", {})),
        wellbores=list(summary.get("wellbores", [])),
        wellbore_identities=[WellboreIdentity(**i) for i in summary.get("wellbore_identities", [])],
        coverage_notes=list(summary.get("coverage_notes", [])),
        issues=issues,
        error=ExtractionError(**run.error) if run.error else None,
        queued_at=run.queued_at,
        finished_at=run.finished_at,
        detail=dict(summary.get("detail", {})),
    )


def records(
    session: Session,
    project_id: UUID,
    document_id: UUID,
    kind: str | None,
    limit: int,
    cursor: str | None,
) -> ExtractedRecordPage:
    require_document(session, project_id, document_id)
    run = _current_run(session, project_id, document_id)
    if run is None or run.status not in ("succeeded", "partial"):
        return ExtractedRecordPage(items=[], page=PageInfo(limit=limit), total=0)
    try:
        after = int(cursor) if cursor else -1
    except ValueError as exc:
        raise ContractError(ErrorCode.VALIDATION_ERROR, "invalid cursor", 422) from exc
    base = [m.extracted_record.c.run_id == run.run_id]
    if kind:
        base.append(m.extracted_record.c.kind == kind)
    total = session.execute(
        select(func.count()).select_from(m.extracted_record).where(*base)
    ).scalar_one()
    rows = session.execute(
        select(m.extracted_record)
        .where(*base, m.extracted_record.c.ordinal > after)
        .order_by(m.extracted_record.c.ordinal)
        .limit(limit + 1)
    ).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return ExtractedRecordPage(
        items=[_record(r, run.source_revision_id) for r in rows],
        page=PageInfo(limit=limit, next_cursor=str(rows[-1].ordinal) if more and rows else None),
        total=total,
    )

"""Import publication and project-scoped source reads. Every statement is project-qualified and
parameterized; document identity within a project is its SHA-256 (never across projects)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import RowMapping, and_, func, insert, select, tuple_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fieldlens.contracts.context import PageInfo
from fieldlens.contracts.errors import ContractError, ErrorCode
from fieldlens.contracts.evidence import Coverage
from fieldlens.contracts.imports import (
    ClassificationUpdate,
    DocumentClassification,
    DocumentPage,
    ImportAccepted,
    ImportMetadata,
    SourceDocumentItem,
    SourceRevisionPage,
    SourceRevisionSummary,
)
from fieldlens.evidence.storage import blob_key
from fieldlens.ingestion.inspect import CLASSIFICATION_METHOD, CLASSIFICATION_VERSION
from fieldlens.ingestion.upload import ReceivedUpload
from fieldlens.persistence import models as m
from fieldlens.projects.errors import deleting_error
from fieldlens.projects.repository import decode_cursor, encode_cursor


def _conflict(message: str, **details: Any) -> ContractError:
    return ContractError(ErrorCode.CONFLICT, message, 409, details or None)


def not_found(what: str = "project") -> ContractError:
    return ContractError(ErrorCode.NOT_FOUND, f"{what} not found", 404)


def fingerprint_of(metadata: ImportMetadata, received: ReceivedUpload) -> str:
    """Request identity for idempotency: bytes + hints + replacement + expected parent."""
    payload = {
        "parent": str(metadata.expected_parent_source_revision_id),
        "files": [
            {
                "sha256": f.sha256,
                "categories": [c.value for c in meta.categories],
                "tags": meta.tags,
                "replaces": str(meta.replaces_document_id),
            }
            for f, meta in zip(received.files, metadata.files, strict=True)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def manifest_hash(members: dict[UUID, str]) -> str:
    lines = sorted(f"{doc_id}:{sha}" for doc_id, sha in members.items())
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def lock_project(session: Session, project_id: UUID) -> UUID | None:
    """Serialize imports per project; returns the latest source revision id (None = no revision)."""
    row = session.execute(
        select(m.project.c.latest_source_revision_id, m.project.c.deletion_state)
        .where(m.project.c.project_id == project_id)
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise not_found()
    if row[1] != "none":  # TASK-071: no import enters a project that is being deleted
        raise deleting_error()
    latest: UUID | None = row[0]
    return latest


def project_latest(session: Session, project_id: UUID) -> UUID | None:
    row = session.execute(
        select(m.project.c.latest_source_revision_id).where(m.project.c.project_id == project_id)
    ).one_or_none()
    if row is None:
        raise not_found()
    latest: UUID | None = row[0]
    return latest


def _accepted_from_batch(session: Session, batch: RowMapping) -> ImportAccepted:
    status = session.execute(
        select(m.source_revision.c.status).where(
            and_(
                m.source_revision.c.project_id == batch["project_id"],
                m.source_revision.c.source_revision_id == batch["source_revision_id"],
            )
        )
    ).scalar_one()
    return ImportAccepted(
        source_revision_id=batch["source_revision_id"],
        job_id=batch["job_id"],
        status=status,
        deduplicated=batch["deduplicated"],
        replayed=True,
        document_ids=list(batch["document_ids"]),
        created_document_ids=[],
    )


def publish_import(
    session: Session,
    project_id: UUID,
    metadata: ImportMetadata,
    received: ReceivedUpload,
    publish_blobs: Callable[[], None] | None = None,
) -> ImportAccepted:
    """One transaction: documents, classification, staging revision, membership, job, batch.
    The project's latest-source pointer is NOT touched here; only a verified job moves it."""
    latest = lock_project(session, project_id)
    fingerprint = fingerprint_of(metadata, received)

    if metadata.idempotency_key is not None:
        batch = (
            session.execute(
                select(m.import_batch).where(
                    and_(
                        m.import_batch.c.project_id == project_id,
                        m.import_batch.c.idempotency_key == metadata.idempotency_key,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if batch is not None:
            if batch["fingerprint"] != fingerprint:
                raise _conflict(
                    "idempotency key was already used with a different request",
                    reason="idempotency_key_reuse",
                )
            return _accepted_from_batch(session, batch)

    if metadata.expected_parent_source_revision_id != latest:
        raise _conflict(
            "the project's source revision changed; refresh and retry",
            reason="stale_parent",
            current_source_revision_id=str(latest) if latest else None,
        )
    staging = session.execute(
        select(m.source_revision.c.source_revision_id).where(
            and_(
                m.source_revision.c.project_id == project_id,
                m.source_revision.c.status == "staging",
            )
        )
    ).first()
    if staging is not None:
        raise _conflict(
            "another import is still being processed for this project",
            reason="import_in_progress",
            source_revision_id=str(staging[0]),
        )

    parent: dict[UUID, str] = {}
    if latest is not None:
        rows = session.execute(
            select(m.source_document.c.document_id, m.source_document.c.sha256)
            .select_from(
                m.source_revision_document.join(
                    m.source_document,
                    and_(
                        m.source_document.c.project_id == m.source_revision_document.c.project_id,
                        m.source_document.c.document_id == m.source_revision_document.c.document_id,
                    ),
                )
            )
            .where(
                and_(
                    m.source_revision_document.c.project_id == project_id,
                    m.source_revision_document.c.source_revision_id == latest,
                )
            )
        ).all()
        parent = {r[0]: r[1] for r in rows}

    # Resolve documents by (project, sha256): same bytes reuse the existing document.
    doc_for_sha: dict[str, UUID] = {}
    created: list[UUID] = []
    document_ids: list[UUID] = []
    for staged, hints in zip(received.files, metadata.files, strict=True):
        doc_id = doc_for_sha.get(staged.sha256)
        if doc_id is None:
            existing = session.execute(
                select(m.source_document.c.document_id).where(
                    and_(
                        m.source_document.c.project_id == project_id,
                        m.source_document.c.sha256 == staged.sha256,
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                existing = _insert_document(session, project_id, staged, hints)
                created.append(existing)
            doc_id = existing
            doc_for_sha[staged.sha256] = doc_id
        document_ids.append(doc_id)

    members = dict(parent)
    replaces_by_doc: dict[UUID, UUID] = {}
    for doc_id, staged, hints in zip(document_ids, received.files, metadata.files, strict=True):
        target = hints.replaces_document_id
        if target is not None:
            if target not in parent:
                raise ContractError(
                    ErrorCode.VALIDATION_ERROR,
                    "replacement target is not a member of the expected parent revision",
                    422,
                    {"reason": "replacement_target_not_in_parent"},
                )
            if target == doc_id:
                raise ContractError(
                    ErrorCode.VALIDATION_ERROR,
                    "replacement bytes are identical to the replaced document",
                    422,
                    {"reason": "replacement_identical"},
                )
            members.pop(target, None)
            replaces_by_doc[doc_id] = target
        members[doc_id] = staged.sha256

    if latest is not None and set(members) == set(parent) and not replaces_by_doc:
        # Every file already belongs to the current revision: no new records, no job.
        if metadata.idempotency_key is not None:
            session.execute(
                insert(m.import_batch).values(
                    project_id=project_id,
                    idempotency_key=metadata.idempotency_key,
                    fingerprint=fingerprint,
                    source_revision_id=latest,
                    job_id=None,
                    deduplicated=True,
                    document_ids=document_ids,
                )
            )
        status = session.execute(
            select(m.source_revision.c.status).where(
                m.source_revision.c.source_revision_id == latest
            )
        ).scalar_one()
        return ImportAccepted(
            source_revision_id=latest,
            job_id=None,
            status=status,
            deduplicated=True,
            replayed=False,
            document_ids=document_ids,
            created_document_ids=[],
        )

    try:
        revision_id = session.execute(
            insert(m.source_revision)
            .values(
                project_id=project_id,
                parent_source_revision_id=latest,
                manifest_hash=manifest_hash(members),
                status="staging",
            )
            .returning(m.source_revision.c.source_revision_id)
        ).scalar_one()
        session.execute(
            insert(m.source_revision_document),
            [
                {
                    "project_id": project_id,
                    "source_revision_id": revision_id,
                    "document_id": doc_id,
                    "replaces_document_id": replaces_by_doc.get(doc_id),
                }
                for doc_id in members
            ],
        )
        job_id = session.execute(
            insert(m.ingest_job)
            .values(
                project_id=project_id,
                kind="storage_verification",
                source_revision_id=revision_id,
                status="queued",
                stage="queued",
            )
            .returning(m.ingest_job.c.job_id)
        ).scalar_one()
        session.execute(
            insert(m.import_batch).values(
                project_id=project_id,
                idempotency_key=metadata.idempotency_key,
                fingerprint=fingerprint,
                source_revision_id=revision_id,
                job_id=job_id,
                deduplicated=False,
                document_ids=document_ids,
            )
        )
        session.flush()
    except IntegrityError as exc:
        raise _conflict(
            "another import is still being processed for this project",
            reason="import_in_progress",
        ) from exc
    if publish_blobs is not None:
        publish_blobs()  # only after every validation passed, while the project lock is held
    return ImportAccepted(
        source_revision_id=revision_id,
        job_id=job_id,
        status="staging",
        deduplicated=False,
        replayed=False,
        document_ids=document_ids,
        created_document_ids=created,
    )


def unreferenced_shas(session: Session, project_id: UUID, shas: list[str]) -> list[str]:
    """Under the project lock, the subset of ``shas`` that no document of the project references
    (race-safe basis for removing a blob a rejected import created)."""
    lock_project(session, project_id)
    referenced = set(
        session.execute(
            select(m.source_document.c.sha256).where(
                and_(
                    m.source_document.c.project_id == project_id,
                    m.source_document.c.sha256.in_(shas),
                )
            )
        ).scalars()
    )
    return [s for s in shas if s not in referenced]


def _insert_document(session: Session, project_id: UUID, staged: Any, hints: Any) -> UUID:
    doc_id: UUID = session.execute(
        insert(m.source_document)
        .values(
            project_id=project_id,
            sha256=staged.sha256,
            size_bytes=staged.size,
            original_filename=staged.filename,
            detected_media_type=staged.detected.media_type,
            format_family=staged.detected.format_family,
            origin_metadata={
                "origin": "multipart_upload",
                **({"text_encoding": staged.detected.encoding} if staged.detected.encoding else {}),
            },
            storage_key=blob_key(project_id, staged.sha256),
        )
        .returning(m.source_document.c.document_id)
    ).scalar_one()
    session.execute(
        insert(m.document_processing).values(
            project_id=project_id,
            document_id=doc_id,
            storage_state="pending_verification",
            extraction_state=staged.detected.extraction_state,
        )
    )
    categories = [c.value for c in hints.categories]
    origin = "upload_hint" if categories else "none"
    session.execute(
        insert(m.document_classification).values(
            project_id=project_id,
            document_id=doc_id,
            user_categories=categories,
            suggested_categories=list(staged.detected.suggested_categories),
            tags=list(hints.tags),
            categories_origin=origin,
            classification_method=CLASSIFICATION_METHOD,
            classification_version=CLASSIFICATION_VERSION,
            metadata_version=1,
        )
    )
    session.execute(
        insert(m.document_classification_event).values(
            project_id=project_id,
            document_id=doc_id,
            metadata_version=1,
            origin=origin,
            categories=categories,
            tags=list(hints.tags),
        )
    )
    return doc_id


# --- reads -----------------------------------------------------------------------------------


def list_documents(
    session: Session,
    project_id: UUID,
    source_revision_id: UUID | None,
    limit: int,
    cursor: str | None,
) -> DocumentPage:
    latest = project_latest(session, project_id)
    revision_id = source_revision_id or latest
    if revision_id is None:
        return DocumentPage(items=[], page=PageInfo(limit=limit, next_cursor=None))
    if source_revision_id is not None:
        owned = session.execute(
            select(m.source_revision.c.source_revision_id).where(
                and_(
                    m.source_revision.c.project_id == project_id,
                    m.source_revision.c.source_revision_id == source_revision_id,
                )
            )
        ).first()
        if owned is None:
            raise not_found("source revision")
    sd, srd, dp, dc = (
        m.source_document,
        m.source_revision_document,
        m.document_processing,
        m.document_classification,
    )
    query = (
        select(
            sd.c.document_id,
            sd.c.project_id,
            sd.c.sha256,
            sd.c.size_bytes,
            sd.c.original_filename,
            sd.c.detected_media_type,
            sd.c.format_family,
            sd.c.origin_metadata,
            sd.c.created_at,
            dp.c.storage_state,
            dp.c.extraction_state,
            dp.c.detail,
            srd.c.replaces_document_id,
            dc.c.user_categories,
            dc.c.suggested_categories,
            dc.c.tags,
            dc.c.categories_origin,
            dc.c.classification_method,
            dc.c.classification_version,
            dc.c.metadata_version,
            dc.c.updated_at.label("classification_updated_at"),
        )
        .select_from(
            srd.join(
                sd,
                and_(sd.c.project_id == srd.c.project_id, sd.c.document_id == srd.c.document_id),
            )
            .join(dp, dp.c.document_id == sd.c.document_id)
            .join(dc, dc.c.document_id == sd.c.document_id)
        )
        .where(and_(srd.c.project_id == project_id, srd.c.source_revision_id == revision_id))
    )
    if cursor is not None:
        created_at, doc_id = decode_cursor(cursor)
        query = query.where(tuple_(sd.c.created_at, sd.c.document_id) < tuple_(created_at, doc_id))
    rows = (
        session.execute(
            query.order_by(sd.c.created_at.desc(), sd.c.document_id.desc()).limit(limit + 1)
        )
        .mappings()
        .all()
    )
    items = [_document_item(r, revision_id) for r in rows[:limit]]
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].document_id)
        if len(rows) > limit and items
        else None
    )
    return DocumentPage(items=items, page=PageInfo(limit=limit, next_cursor=next_cursor))


def _classification(r: RowMapping) -> DocumentClassification:
    return DocumentClassification(
        user_categories=list(r["user_categories"]),
        suggested_categories=list(r["suggested_categories"]),
        tags=list(r["tags"]),
        categories_origin=r["categories_origin"],
        classification_method=r["classification_method"],
        classification_version=r["classification_version"],
        metadata_version=r["metadata_version"],
        updated_at=r["classification_updated_at"],
    )


def _document_item(r: RowMapping, revision_id: UUID) -> SourceDocumentItem:
    return SourceDocumentItem(
        document_id=r["document_id"],
        project_id=r["project_id"],
        sha256=r["sha256"],
        size_bytes=r["size_bytes"],
        original_filename=r["original_filename"],
        detected_media_type=r["detected_media_type"],
        format_family=r["format_family"],
        origin_metadata=r["origin_metadata"],
        created_at=r["created_at"],
        storage_state=r["storage_state"],
        extraction_state=r["extraction_state"],
        processing_detail=r["detail"],
        classification=_classification(r),
        replaces_document_id=r["replaces_document_id"],
        source_revision_id=revision_id,
    )


def list_revisions(
    session: Session, project_id: UUID, limit: int, cursor: str | None
) -> SourceRevisionPage:
    latest = project_latest(session, project_id)
    sr = m.source_revision
    query = select(
        sr.c.source_revision_id,
        sr.c.project_id,
        sr.c.parent_source_revision_id,
        sr.c.manifest_hash,
        sr.c.created_at,
        sr.c.status,
        sr.c.coverage,
    ).where(sr.c.project_id == project_id)
    if cursor is not None:
        created_at, rev_id = decode_cursor(cursor)
        query = query.where(
            tuple_(sr.c.created_at, sr.c.source_revision_id) < tuple_(created_at, rev_id)
        )
    rows = (
        session.execute(
            query.order_by(sr.c.created_at.desc(), sr.c.source_revision_id.desc()).limit(limit + 1)
        )
        .mappings()
        .all()
    )
    page_rows = rows[:limit]
    ids = [r["source_revision_id"] for r in page_rows]
    counts: dict[UUID, tuple[int, int, int, int, int]] = {}
    jobs: dict[UUID, tuple[UUID, str]] = {}
    if ids:
        srd, dp = m.source_revision_document, m.document_processing
        for row in session.execute(
            select(
                srd.c.source_revision_id,
                func.count(),
                func.count().filter(dp.c.storage_state == "stored"),
                func.count().filter(dp.c.storage_state == "quarantined"),
                func.count().filter(dp.c.extraction_state == "pending_extraction"),
                func.count().filter(dp.c.extraction_state == "unsupported"),
            )
            .select_from(srd.join(dp, dp.c.document_id == srd.c.document_id))
            .where(and_(srd.c.project_id == project_id, srd.c.source_revision_id.in_(ids)))
            .group_by(srd.c.source_revision_id)
        ):
            counts[row[0]] = (row[1], row[2], row[3], row[4], row[5])
        for jrow in session.execute(
            select(m.ingest_job.c.source_revision_id, m.ingest_job.c.job_id, m.ingest_job.c.status)
            .where(
                and_(
                    m.ingest_job.c.project_id == project_id,
                    m.ingest_job.c.source_revision_id.in_(ids),
                )
            )
            .order_by(m.ingest_job.c.created_at)
        ):
            jobs[jrow[0]] = (jrow[1], jrow[2])
    items = []
    for r in page_rows:
        member, stored, quarantined, pending, unsupported = counts.get(
            r["source_revision_id"], (0, 0, 0, 0, 0)
        )
        job = jobs.get(r["source_revision_id"])
        items.append(
            SourceRevisionSummary(
                source_revision_id=r["source_revision_id"],
                project_id=r["project_id"],
                parent_source_revision_id=r["parent_source_revision_id"],
                manifest_hash=r["manifest_hash"],
                created_at=r["created_at"],
                status=r["status"],
                coverage=Coverage.model_validate(r["coverage"]) if r["coverage"] else None,
                is_latest=r["source_revision_id"] == latest,
                member_count=member,
                stored_count=stored,
                quarantined_count=quarantined,
                pending_extraction_count=pending,
                unsupported_count=unsupported,
                job_id=job[0] if job else None,
                job_status=job[1] if job else None,
            )
        )
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].source_revision_id)
        if len(rows) > limit and items
        else None
    )
    return SourceRevisionPage(items=items, page=PageInfo(limit=limit, next_cursor=next_cursor))


def update_classification(
    session: Session, project_id: UUID, document_id: UUID, body: ClassificationUpdate
) -> UUID:
    dc = m.document_classification
    row = (
        session.execute(
            select(dc)
            .where(and_(dc.c.project_id == project_id, dc.c.document_id == document_id))
            .with_for_update()
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise not_found("document")
    if row["metadata_version"] != body.expected_metadata_version:
        raise _conflict(
            "document metadata changed; refresh and retry",
            reason="stale_metadata_version",
            current_metadata_version=row["metadata_version"],
        )
    categories = [c.value for c in body.categories]
    if categories == list(row["user_categories"]) and body.tags == list(row["tags"]):
        return document_id
    version = row["metadata_version"] + 1
    session.execute(
        update(dc)
        .where(and_(dc.c.project_id == project_id, dc.c.document_id == document_id))
        .values(
            user_categories=categories,
            tags=body.tags,
            categories_origin="user_override",
            metadata_version=version,
            updated_at=func.clock_timestamp(),
        )
    )
    session.execute(
        insert(m.document_classification_event).values(
            project_id=project_id,
            document_id=document_id,
            metadata_version=version,
            origin="user_override",
            categories=categories,
            tags=body.tags,
        )
    )
    return document_id


def get_document_in_project(
    session: Session, project_id: UUID, document_id: UUID, revision_id: UUID | None
) -> SourceDocumentItem:
    """Single scoped read used after classification edits (document must belong to project)."""
    page = list_documents(session, project_id, revision_id, 200, None)
    for item in page.items:
        if item.document_id == document_id:
            return item
    cur = None
    while page.page.next_cursor:
        cur = page.page.next_cursor
        page = list_documents(session, project_id, revision_id, 200, cur)
        for item in page.items:
            if item.document_id == document_id:
                return item
    raise not_found("document")

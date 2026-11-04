"""Populate EVERY project-scoped table for one project, driven by the PostgreSQL catalog.

The row builder reads column types, defaults and foreign keys from ``pg_catalog`` so a table added
later is populated too (or the helper fails loudly and names the table). Only values the schema's
CHECK constraints need beyond the generic defaults are listed in ``OVERRIDES``.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import Connection, text

from fieldlens.projects.purge import PURGE_ORDER

SHA = "a" * 64

# column values required by CHECK constraints / enums, per table (generic fill covers the rest)
OVERRIDES: dict[str, dict[str, Any]] = {
    "source_revision": {"status": "staging", "manifest_hash": SHA},
    "source_document": {"sha256": SHA, "size_bytes": 3},
    "ingest_job": {"kind": "storage_verification", "status": "queued"},
    "ingest_job_attempt": {"status": "interrupted"},
    "document_classification": {"categories_origin": "none"},
    "document_classification_event": {"origin": "none"},
    "document_processing": {
        "storage_state": "stored",
        "extraction_state": "pending_extraction",
    },
    "extraction_run": {"content_sha256": SHA, "status": "queued"},
    "retrieval_index": {"status": "queued", "kind": "chunks"},
    "evidence_chunk": {"chunk_fingerprint": SHA, "vector_policy": "embed"},
    "chunk_embedding": {
        "embedding_fingerprint": SHA,
        "embedding": "[0.1,0.2,0.3]",
        "dimension": 3,
    },
    "agent_work_unit": {"unit_key": "u", "question": "q", "state": "running"},
    "agent_step": {"kind": "note", "summary": "s"},
    "extraction_candidate": {
        "state": "candidate",
        "method": "model_proposal",
        "validation_state": "valid",
        "attributes": '{"kind": "equipment"}',
    },
    "model_revision": {"status": "draft"},
    "import_batch": {"fingerprint": SHA},
    "identity_merge": {"source_kind": "label", "source_key": "a", "target_key": "b"},
    "merge_proposal": {"status": "pending", "guard_result": "[]"},
    "merge_proposal_member": {"kind": "label", "role": "member"},
    "merge_proposal_run": {"state": "succeeded"},
    "processing_run": {"status": "estimated", "provider": "stub", "route": "model"},
    "processing_run_document": {"state": "estimated"},
    "document_model_result": {
        "extraction_method": "model_classification",
        "provider": "stub",
        "category": "general_report",
    },
    "document_identity_proposal": {
        "extraction_method": "model_classification",
        "provider": "stub",
        "subject_kind": "wellbore",
    },
    "reconstruction_run": {"status": "estimated", "source_revision": SHA},
    "wellbore_asset_spec": {"state": "current", "spec": '{"visual_only": true}'},
    "chat_message": {"role": "user", "text": "hello"},
    "reconstruction_run_stage": {"stage": "gather", "state": "pending", "kind": "deterministic"},
    "series_axis": {
        "position_kind": "line",
        "index_order": "increasing",
        "index_unit_status": "stated",
        "index_encoding": "numeric",
        "index_type": "depth",
        "kind": "log",
        "sample_count": 1,
        "index_data": b"\x00" * 8,
        "positions_data": b"\x00" * 4,
    },
    "series_curve": {
        "data_sha256": SHA,
        "unit_status": "stated",
        "sample_count": 1,
        "values_data": b"\x00" * 8,
        "valid_count": 0,
        "null_count": 1,
    },
    "well": {"name": "w"},
    "wellbore": {"name": "wb"},
}


def _columns(conn: Connection, table: str) -> list[Any]:
    return list(
        conn.execute(
            text(
                "SELECT column_name, data_type, is_nullable, column_default, "
                "character_maximum_length FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=:t ORDER BY ordinal_position"
            ),
            {"t": table},
        ).all()
    )


def _fks(conn: Connection, table: str) -> list[tuple[str, list[str], list[str]]]:
    rows = conn.execute(
        text(
            """
            SELECT c.confrelid::regclass::text AS parent,
                   (SELECT array_agg(a.attname ORDER BY k.ord)
                      FROM unnest(c.conkey) WITH ORDINALITY k(attnum, ord)
                      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum),
                   (SELECT array_agg(a.attname ORDER BY k.ord)
                      FROM unnest(c.confkey) WITH ORDINALITY k(attnum, ord)
                      JOIN pg_attribute a ON a.attrelid = c.confrelid AND a.attnum = k.attnum)
            FROM pg_constraint c
            WHERE c.contype='f' AND c.conrelid = to_regclass(:t)
            """
        ),
        {"t": table},
    ).all()
    return [(r[0], list(r[1]), list(r[2])) for r in rows]


def _generic(col: Any, counter: int) -> Any:
    name, dtype, _nullable, _default, maxlen = col
    if dtype == "uuid":
        return uuid.uuid4()
    if dtype in ("character varying", "text", "character"):
        value = f"v{counter}"
        return value[: maxlen or 64]
    if dtype in ("integer", "bigint", "smallint"):
        return 1
    if dtype == "numeric" or dtype in ("double precision", "real"):
        return 0
    if dtype == "boolean":
        return False
    if dtype.startswith("timestamp"):
        return None  # replaced by now() below
    if dtype in ("jsonb", "json"):
        return json.dumps({})
    if dtype == "ARRAY":
        return []
    if dtype == "bytea":
        return b""
    if dtype == "date":
        return None
    raise AssertionError(f"populate: unsupported column type {dtype} ({name})")


def populate_project(
    conn: Connection,
    project_id: uuid.UUID,
    extra: dict[str, dict[str, Any]] | None = None,
) -> dict[str, int]:
    """Insert one row into every project-scoped table (parents first); returns row counts."""
    created: dict[str, dict[str, Any]] = {
        "project": dict(
            conn.execute(text("SELECT * FROM project WHERE project_id=:p"), {"p": project_id})
            .mappings()
            .one()
        )
    }
    counter = 0
    for table in reversed(PURGE_ORDER):
        counter += 1
        cols = _columns(conn, table)
        fks = _fks(conn, table)
        overrides = {**OVERRIDES.get(table, {}), **(extra or {}).get(table, {})}
        values: dict[str, Any] = {}
        for parent, mine, theirs in fks:
            parent_row = created.get(parent)
            if parent_row is None:
                continue
            if any(m not in {c[0] for c in cols} for m in mine):
                continue
            nullable_cols = {c[0] for c in cols if c[2] == "YES"}
            if any(m in nullable_cols for m in mine if m != "project_id"):
                continue  # optional reference: leave NULL (avoids self-replace style checks)
            for m_col, t_col in zip(mine, theirs, strict=True):
                values[m_col] = parent_row[t_col]
        for col in cols:
            name, dtype, nullable, default, _ = col
            if name in values:
                continue
            if name == "project_id":
                values[name] = project_id
            elif name in overrides:
                values[name] = overrides[name]
            elif default is not None:
                continue
            elif nullable == "YES":
                continue
            elif dtype.startswith("timestamp"):
                values[name] = text("now()")  # type: ignore[assignment]
            else:
                values[name] = _generic(col, counter)
        for key, val in overrides.items():
            values.setdefault(key, val)
        placeholders = []
        params: dict[str, Any] = {}
        for key, val in values.items():
            if hasattr(val, "text"):
                placeholders.append("now()")
            else:
                placeholders.append(f":{key}")
                params[key] = val
        sql = (
            f"INSERT INTO {table} ({', '.join(values)}) "
            f"VALUES ({', '.join(placeholders)}) RETURNING *"
        )
        try:
            with conn.begin_nested():
                inserted = dict(conn.execute(text(sql), params).mappings().one())
        except Exception as exc:  # name the table that could not be populated
            raise AssertionError(f"populate {table} failed: {str(exc)[:400]}") from exc
        created[table] = inserted
    # self-referencing rows: a child wellbore and a child (staging) source revision
    wb = created["wellbore"]
    conn.execute(
        text(
            "INSERT INTO wellbore (project_id, well_id, name, parent_wellbore_id) "
            "VALUES (:p, :w, 'child', :parent)"
        ),
        {"p": project_id, "w": wb["well_id"], "parent": wb["wellbore_id"]},
    )
    conn.execute(
        text(
            "INSERT INTO source_revision (project_id, parent_source_revision_id, manifest_hash, "
            "status) VALUES (:p, :parent, :h, 'ready')"
        ),
        {
            "p": project_id,
            "parent": created["source_revision"]["source_revision_id"],
            "h": "b" * 64,
        },
    )
    pointers = created.get("source_revision")
    models = created.get("model_revision")
    if pointers and models:
        conn.execute(
            text(
                "UPDATE project SET latest_source_revision_id=:s, active_model_revision_id=:m "
                "WHERE project_id=:p"
            ),
            {"s": pointers["source_revision_id"], "m": models["revision_id"], "p": project_id},
        )
    return count_rows(conn, project_id)


def project_tables(conn: Connection) -> list[str]:
    return [
        r[0]
        for r in conn.execute(
            text(
                "SELECT DISTINCT c.table_name FROM information_schema.columns c "
                "JOIN information_schema.tables t USING (table_schema, table_name) "
                "WHERE c.table_schema='public' AND c.column_name='project_id' "
                "AND t.table_type='BASE TABLE' ORDER BY 1"
            )
        )
    ]


def count_rows(conn: Connection, project_id: uuid.UUID) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in project_tables(conn):
        counts[table] = int(
            conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE project_id = :p"),  # noqa: S608
                {"p": project_id},
            ).scalar_one()
        )
    return counts

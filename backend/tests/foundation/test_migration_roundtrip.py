"""FN-2: PostgreSQL migration round trip, persisted contract fixture, scope integrity."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, insert, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from fieldlens.contracts.identity import (
    ModelRevision,
    Project,
    SourceDocument,
    SourceRevision,
    Well,
    Wellbore,
)
from fieldlens.persistence import models as m
from fieldlens.persistence.readiness import alembic_config, expected_head
from tests import support
from tests.conftest import migrate

SNAPSHOT_SQL = {
    "tables": "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
    "AND table_name <> 'alembic_version' ORDER BY 1",
    "columns": "SELECT table_name, column_name, data_type, is_nullable, column_default, "
    "character_maximum_length FROM information_schema.columns WHERE table_schema='public' "
    "AND table_name <> 'alembic_version' ORDER BY 1,2",
    "constraints": "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) "
    "FROM pg_constraint WHERE connamespace='public'::regnamespace "
    "AND conrelid::regclass::text <> 'alembic_version' ORDER BY 1,2",
    "indexes": "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname='public' "
    "AND tablename <> 'alembic_version' ORDER BY 1",
    "triggers": "SELECT tgname, tgrelid::regclass::text, pg_get_triggerdef(oid) FROM pg_trigger "
    "WHERE NOT tgisinternal ORDER BY 1",
    "functions": "SELECT proname FROM pg_proc WHERE pronamespace='public'::regnamespace ORDER BY 1",
    "extensions": "SELECT extname FROM pg_extension WHERE extname='vector'",
}


def snapshot(engine: Engine, keys: tuple[str, ...] | None = None) -> dict[str, Any]:
    with engine.connect() as conn:
        return {
            k: [tuple(r) for r in conn.execute(text(sql))]
            for k, sql in SNAPSHOT_SQL.items()
            if keys is None or k in keys
        }


def _alembic(engine: Engine, fn: str, rev: str) -> None:
    with engine.begin() as conn:
        cfg = alembic_config()
        cfg.attributes["connection"] = conn
        getattr(command, fn)(cfg, rev)


def test_single_head_and_known_revision() -> None:
    assert expected_head() == "0012_merge_proposals"


def test_migration_roundtrip(empty_database: URL) -> None:
    engine = create_engine(empty_database)
    try:
        assert all(v == [] for v in snapshot(engine).values())
        migrate(empty_database)
        first = snapshot(engine)
        assert {t[0] for t in first["tables"]} >= {"project", "source_revision", "wellbore"}
        assert first["extensions"] == [("vector",)]

        # Downgrade to an empty database (only alembic's own bookkeeping may remain).
        _alembic(engine, "downgrade", "base")
        empty = snapshot(engine)
        assert all(v == [] for v in empty.values()), empty

        # Upgrade again: identical schema (no drift).
        _alembic(engine, "upgrade", "head")
        assert snapshot(engine) == first

        # Models and migration agree.
        with engine.connect() as conn:
            diff = compare_metadata(MigrationContext.configure(conn), m.metadata)
        assert diff == []
    finally:
        engine.dispose()


def test_migration_matches_model_metadata_names_and_definitions(
    migrated_url: URL, test_database_base: URL
) -> None:
    other_url = support.sibling_url(test_database_base)
    support.create_database(other_url)
    other = create_engine(other_url)
    try:
        with other.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        m.metadata.create_all(other)
        a = create_engine(migrated_url)
        keys = ("tables", "columns", "constraints", "indexes")
        sa_, sb_ = snapshot(a, keys), snapshot(other, keys)
        for k in keys:
            assert sa_[k] == sb_[k], k
        a.dispose()
    finally:
        other.dispose()
        support.drop_database(other_url)


def test_migration_refuses_demo_database(
    test_database_base: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    demo = test_database_base.set(database="fieldlens_demo")
    monkeypatch.setenv("FIELDLENS_DATABASE_URL", demo.render_as_string(hide_password=False))
    # Must fail either at the guard or because the database does not exist; never migrate it.
    with pytest.raises(Exception, match="protected database|does not exist"):
        command.upgrade(alembic_config(), "head")


# --- persisted contract fixture -----------------------------------------------------------------


def uid() -> uuid.UUID:
    return uuid.uuid4()


def build_fixture() -> dict[str, Any]:
    now = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    pid, src, doc, rev, well, bore, side = (uid() for _ in range(7))
    return {
        "project": Project(
            project_id=pid,
            name="Alpha",
            description="",
            created_at=now,
            updated_at=now,
            latest_source_revision_id=src,
            active_model_revision_id=rev,
        ),
        "source": SourceRevision(
            source_revision_id=src,
            project_id=pid,
            manifest_hash="a" * 64,
            created_at=now,
            status="ready",
        ),
        "document": SourceDocument(
            document_id=doc,
            project_id=pid,
            sha256="b" * 64,
            size_bytes=12,
            original_filename="Report 1.pdf",
            detected_media_type="application/pdf",
            origin_metadata={"rights": "synthetic"},
            created_at=now,
        ),
        "model": ModelRevision(
            revision_id=rev,
            project_id=pid,
            pinned_source_revision_id=src,
            status="published",
            created_at=now,
        ),
        "well": Well(well_id=well, project_id=pid, name="15/9-F-12"),
        "bore": Wellbore(wellbore_id=bore, project_id=pid, well_id=well, name="Main"),
        "side": Wellbore(
            wellbore_id=side, project_id=pid, well_id=well, parent_wellbore_id=bore, name="T2"
        ),
    }


def persist(conn: Any, f: dict[str, Any]) -> None:
    p, s, d, mo = f["project"], f["source"], f["document"], f["model"]
    # Pointers are deferred composite FKs: the project row may precede its revisions in a txn.
    conn.execute(insert(m.project).values(**p.model_dump()))
    conn.execute(
        insert(m.source_revision).values(
            source_revision_id=s.source_revision_id,
            project_id=s.project_id,
            parent_source_revision_id=None,
            manifest_hash=s.manifest_hash,
            status="staging",  # membership may only be added while staging (0003 trigger)
            created_at=s.created_at,
        )
    )
    conn.execute(
        insert(m.model_revision).values(
            revision_id=mo.revision_id,
            project_id=mo.project_id,
            pinned_source_revision_id=mo.pinned_source_revision_id,
            base_revision_id=None,
            status=mo.status.value,
            created_at=mo.created_at,
        )
    )
    conn.execute(insert(m.source_document).values(**d.model_dump(), storage_key="k/ab/cd"))
    conn.execute(
        insert(m.source_revision_document).values(
            project_id=p.project_id,
            source_revision_id=s.source_revision_id,
            document_id=d.document_id,
        )
    )
    conn.execute(
        m.source_revision.update()
        .where(m.source_revision.c.source_revision_id == s.source_revision_id)
        .values(status=s.status.value)
    )
    conn.execute(insert(m.well).values(**f["well"].model_dump()))
    conn.execute(insert(m.wellbore).values(**f["bore"].model_dump()))
    conn.execute(insert(m.wellbore).values(**f["side"].model_dump()))


def test_contract_fixture_roundtrips_through_postgresql(engine: Engine) -> None:
    f = build_fixture()
    with engine.begin() as conn:
        persist(conn, f)
    with engine.connect() as conn:
        row = conn.execute(select(m.project)).mappings().one()
        assert Project.model_validate(dict(row)) == f["project"]
        row = conn.execute(select(m.source_revision)).mappings().one()
        assert SourceRevision.model_validate(dict(row)) == f["source"]
        row = conn.execute(select(m.model_revision)).mappings().one()
        assert ModelRevision.model_validate(dict(row)) == f["model"]
        drow = dict(conn.execute(select(m.source_document)).mappings().one())
        assert drow.pop("storage_key") == "k/ab/cd"  # server-owned, outside the client DTO
        assert SourceDocument.model_validate(drow) == f["document"]
        rows = conn.execute(select(m.wellbore).order_by(m.wellbore.c.name)).mappings().all()
        server_owned = (
            "wellbore_key",
            "suffix",
        )  # identity resolution columns (0008), not in the DTO
        got = [
            Wellbore.model_validate({k: v for k, v in dict(r).items() if k not in server_owned})
            for r in rows
        ]
        assert got == sorted([f["bore"], f["side"]], key=lambda w: w.name)


def two_projects(engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    a, b, src_a = uid(), uid(), uid()
    with engine.begin() as conn:
        conn.execute(
            insert(m.project), [{"project_id": a, "name": "A"}, {"project_id": b, "name": "B"}]
        )
        conn.execute(
            insert(m.source_revision).values(
                source_revision_id=src_a, project_id=a, manifest_hash="c" * 64, status="ready"
            )
        )
    return a, b, src_a


def test_composite_fks_block_cross_project_references(engine: Engine) -> None:
    a, b, src_a = two_projects(engine)
    # A model revision in B cannot pin A's source revision.
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            insert(m.model_revision).values(
                project_id=b, pinned_source_revision_id=src_a, status="draft"
            )
        )
    # B's project pointer cannot reference A's source revision (deferred: fails at commit).
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            text("UPDATE project SET latest_source_revision_id=:s WHERE project_id=:p"),
            {"s": src_a, "p": b},
        )
    # A document owned by A cannot become a member of a B revision.
    doc, src_b = uid(), uid()
    with engine.begin() as conn:
        conn.execute(
            insert(m.source_document).values(
                document_id=doc,
                project_id=a,
                sha256="d" * 64,
                size_bytes=1,
                original_filename="x",
                storage_key="k",
            )
        )
        conn.execute(
            insert(m.source_revision).values(
                source_revision_id=src_b, project_id=b, manifest_hash="e" * 64, status="staging"
            )
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            insert(m.source_revision_document).values(
                project_id=b, source_revision_id=src_b, document_id=doc
            )
        )
    # A wellbore cannot attach to another project's well.
    well = uid()
    with engine.begin() as conn:
        conn.execute(insert(m.well).values(well_id=well, project_id=a, name="W"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(m.wellbore).values(project_id=b, well_id=well, name="bad"))


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO project (name) VALUES ('  padded ')",
        "INSERT INTO project (name) VALUES ('')",
    ],
)
def test_project_name_constraints(engine: Engine, sql: str) -> None:
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(sql))


def test_invalid_hash_status_and_size_rejected(engine: Engine) -> None:
    a, _, _ = two_projects(engine)
    bad_rows = [
        insert(m.source_revision).values(project_id=a, manifest_hash="XYZ", status="ready"),
        insert(m.source_revision).values(project_id=a, manifest_hash="c" * 64, status="bogus"),
        insert(m.source_document).values(
            project_id=a, sha256="d" * 64, size_bytes=-1, original_filename="x", storage_key="k"
        ),
    ]
    for stmt in bad_rows:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(stmt)


def test_wellbore_parent_cycles_rejected(engine: Engine) -> None:
    a, _, _ = two_projects(engine)
    well, x, y, z = uid(), uid(), uid(), uid()
    with engine.begin() as conn:
        conn.execute(insert(m.well).values(well_id=well, project_id=a, name="W"))
        conn.execute(insert(m.wellbore).values(wellbore_id=x, project_id=a, well_id=well, name="x"))
        conn.execute(
            insert(m.wellbore).values(
                wellbore_id=y, project_id=a, well_id=well, parent_wellbore_id=x, name="y"
            )
        )
        conn.execute(
            insert(m.wellbore).values(
                wellbore_id=z, project_id=a, well_id=well, parent_wellbore_id=y, name="z"
            )
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:  # x -> z closes a cycle
        conn.execute(
            text("UPDATE wellbore SET parent_wellbore_id=:z WHERE wellbore_id=:x"),
            {"z": z, "x": x},
        )
    with pytest.raises(IntegrityError), engine.begin() as conn:  # self parent
        conn.execute(
            text("UPDATE wellbore SET parent_wellbore_id=wellbore_id WHERE wellbore_id=:x"),
            {"x": x},
        )


def test_pgvector_usable_without_model_download(engine: Engine) -> None:
    with engine.connect() as conn:
        dist = conn.execute(text("SELECT '[1,2,3]'::vector <-> '[1,2,4]'::vector")).scalar_one()
        assert dist == 1.0
        ver = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname='vector'"))
        assert ver.scalar_one().startswith("0.8")

"""Migration- and extension-aware readiness evaluation."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import SQLAlchemyError

from fieldlens.contracts.system import ReadinessCheck

BACKEND_DIR = Path(__file__).resolve().parents[2]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
REQUIRED_EXTENSIONS = ("vector",)


def alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def expected_head() -> str:
    head = ScriptDirectory.from_config(alembic_config()).get_current_head()
    if head is None:
        raise RuntimeError("no Alembic head revision found")
    return head


def _unavailable(detail: str) -> list[ReadinessCheck]:
    return [
        ReadinessCheck(name="database", ok=False, detail=detail),
        ReadinessCheck(name="migrations", ok=False, detail="database unavailable"),
        ReadinessCheck(name="pgvector", ok=False, detail="database unavailable"),
    ]


def evaluate_readiness(engine: Engine | None) -> list[ReadinessCheck]:
    """One check per requirement; any ``ok=False`` means the API is not ready."""
    if engine is None:
        return _unavailable("FIELDLENS_DATABASE_URL is not configured")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            migrations = _migration_check(conn)
            pgvector = _extension_check(conn)
    except SQLAlchemyError as exc:
        # Exception class only: driver messages can embed connection details.
        return _unavailable(type(exc).__name__)
    return [ReadinessCheck(name="database", ok=True), migrations, pgvector]


def _migration_check(conn: Connection) -> ReadinessCheck:
    head = expected_head()
    try:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    except SQLAlchemyError:
        conn.rollback()
        return ReadinessCheck(name="migrations", ok=False, detail=f"not migrated; expected {head}")
    current = row[0] if row else None
    if current != head:
        return ReadinessCheck(name="migrations", ok=False, detail=f"at {current}; expected {head}")
    return ReadinessCheck(name="migrations", ok=True, detail=head)


def _extension_check(conn: Connection) -> ReadinessCheck:
    rows = conn.execute(text("SELECT extname FROM pg_extension")).scalars().all()
    missing = [e for e in REQUIRED_EXTENSIONS if e not in rows]
    if missing:
        return ReadinessCheck(name="pgvector", ok=False, detail=f"missing extension: {missing[0]}")
    return ReadinessCheck(name="pgvector", ok=True)

"""Single engine/session-factory construction. No database I/O happens at import or creation."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from fieldlens.config import Settings


def create_db_engine(settings: Settings) -> Engine | None:
    """Lazy engine (connects on first use); ``None`` when no database URL is configured."""
    if settings.database_url is None:
        return None
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_s,
            "application_name": application_name(settings),
        },
    )


def application_name(settings: Settings) -> str:
    """``fieldlens:<lane>:<pid>`` so ``pg_stat_activity`` shows which process holds a connection."""
    return f"fieldlens:{settings.lane}:{os.getpid()}"[:63]


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on any error."""
    session = factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()

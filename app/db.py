"""Database engine + session helpers.

`get_session` is a FastAPI dependency (yields a session, closes it after the
request). `session_scope` is a plain context manager for scripts, the seed job,
and the voice tool handlers, which don't run inside a request.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlmodel import Session, SQLModel

from app.config import get_settings

_settings = get_settings()

# pool_pre_ping: transparently recycle connections dropped by the DB / a restart.
engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)


def create_all() -> None:
    """Create tables directly from the models. Used by tests and first-run local
    dev. Production uses Alembic migrations instead."""
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from ..logging.logger import get_logger
from .base import Base, create_engine_and_session

log = get_logger("adapted.database.session")


def _resolve_database_url() -> str:
    """Return the validated DATABASE_URL.

    PostgreSQL + pgvector is the only supported backend. Raises a clear error
    at startup if the URL is missing, points at SQLite, or is unreachable —
    no silent fallback.
    """
    url = settings.database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Point it at a PostgreSQL database, e.g. "
            "postgresql+psycopg://USER:PASSWORD@HOST:5432/dbname"
        )
    if not url.startswith("postgresql"):
        raise RuntimeError(
            f"Unsupported DATABASE_URL scheme in {url!r}: PostgreSQL is the only "
            "supported backend (postgresql+psycopg://...)."
        )

    from sqlalchemy import create_engine as _ce

    probe = _ce(url, connect_args={"connect_timeout": 5}, pool_pre_ping=True, future=True)
    try:
        with probe.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise RuntimeError(f"Cannot reach PostgreSQL at {url.split('@')[-1]}: {exc}") from exc
    finally:
        probe.dispose()

    return url


engine, SessionLocal = create_engine_and_session(_resolve_database_url(), debug=False)


def new_id() -> str:
    return uuid.uuid4().hex


def new_code(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)


def reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def db_add(db: Session, obj: Any) -> Any:
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

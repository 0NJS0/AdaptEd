from __future__ import annotations

from typing import Any, ClassVar

from sqlalchemy import JSON, MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.types import TypeDecorator

from ..config import settings


class VectorColumn(TypeDecorator):
    """pgvector vector type on PostgreSQL."""

    cache_ok = True
    impl = None

    def __init__(self, dim: int | None = None) -> None:
        self.dim = dim or settings.embedding_dim
        super().__init__()

    def load_dialect_impl(self, dialect: Any) -> Any:
        from pgvector.sqlalchemy import Vector

        return dialect.type_descriptor(Vector(self.dim))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        return value


NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[type, Any]] = {dict: JSON}


def create_engine_and_session(database_url: str, debug: bool = False):
    engine = create_engine(database_url, echo=debug, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return engine, SessionLocal

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import text

from ..config import settings
from ..database.session import SessionLocal
from ..models import ContentChunk

log = logging.getLogger("adapted.rag.vector_store")


class VectorStore:
    """PostgreSQL + pgvector vector store.

    Vectors live in the ``content_chunks.vector`` pgvector column; similarity
    search uses the ``<=>`` cosine operator and an HNSW index.
    """

    def __init__(self) -> None:
        self.mode = "postgres"

    # ---------------------------------------------------------------- schema
    def ensure_collection(self, collection: str, dim: int | None = None, db=None) -> None:
        """Ensure pgvector is available and the vector index exists.

        Uses an IVFFlat index: the free OpenRouter embed model (Nemotron 3
        Embed 1B) outputs 2048-dim vectors, which exceed pgvector's 2000-dim
        cap for HNSW. IVFFlat supports up to 40,000 dims.
        """
        session = db or SessionLocal()
        try:
            session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            dim = dim or settings.embedding_dim
            if dim > 2000:
                # pgvector caps every index type at 2000 dims (verified on
                # 0.8.6 for both HNSW and IVFFlat). At >2000 dims search runs
                # a sequential scan over `content_chunks`, which is fine at
                # this dataset size.
                if db is None:
                    session.commit()
                return
            session.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_content_chunks_vector "
                    "ON content_chunks USING ivfflat (vector vector_cosine_ops) "
                    "WITH (lists = 1) WHERE vector IS NOT NULL"
                )
            )
            if db is None:
                session.commit()
        except Exception as exc:  # noqa: BLE001
            log.warning("pgvector_ensure_failed: %s", exc)
        finally:
            if db is None:
                session.close()

    def delete_collection(self, collection: str, db=None) -> None:
        course_id = collection.removeprefix("course_")
        session = db or SessionLocal()
        try:
            session.execute(
                text("DELETE FROM content_chunks WHERE course_id = :cid"),
                {"cid": course_id},
            )
            if db is None:
                session.commit()
        finally:
            if db is None:
                session.close()

    # ---------------------------------------------------------------- writes
    def upsert(
        self,
        collection: str,
        points: list[tuple[str, list[float], dict[str, Any]]],
        db=None,
    ) -> None:
        """points: (chunk_id, vector, payload).

        Sets the vector on the matching ContentChunk row; if no row exists yet
        for ``chunk_id``, inserts one from the payload fields (document_id,
        course_id, chunk_id, chapter_id, topic_id, page_start, page_end,
        heading, content, source).
        """
        if not points:
            return
        session = db or SessionLocal()
        try:
            for chunk_id, vector, payload in points:
                row = session.get(ContentChunk, chunk_id)
                if row is not None:
                    row.vector = vector
                else:
                    session.add(
                        ContentChunk(
                            id=chunk_id,
                            document_id=payload.get("document_id"),
                            course_id=payload.get("course_id"),
                            chapter_id=payload.get("chapter_id"),
                            topic_id=payload.get("topic_id"),
                            page_start=payload.get("page_start"),
                            page_end=payload.get("page_end"),
                            heading=payload.get("heading"),
                            content=payload.get("content", ""),
                            source=payload.get("source"),
                            vector=vector,
                        )
                    )
            if db is None:
                session.commit()
            else:
                session.flush()
        finally:
            if db is None:
                session.close()

    def delete_by_document(self, collection: str, document_id: str, db=None) -> None:
        """Vectors live on ContentChunk rows, so deleting the rows clears them."""
        session = db or SessionLocal()
        try:
            session.execute(
                text("DELETE FROM content_chunks WHERE document_id = :did"),
                {"did": document_id},
            )
            if db is None:
                session.commit()
        finally:
            if db is None:
                session.close()

    # ---------------------------------------------------------------- search
    def search(
        self,
        collection: str,
        vector: list[float],
        *,
        limit: int = 6,
        course_id: str | None = None,
        chapter_id: str | None = None,
        topic_id: str | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        course_id = course_id or collection.removeprefix("course_")
        return self._search_postgres(
            vector,
            limit=limit,
            course_id=course_id,
            chapter_id=chapter_id,
            topic_id=topic_id,
            score_threshold=score_threshold,
        )

    def _filters_sql(
        self,
        course_id: str | None,
        chapter_id: str | None,
        topic_id: str | None,
    ) -> tuple[list[str], dict[str, Any]]:
        conds: list[str] = []
        params: dict[str, Any] = {}
        if course_id:
            conds.append("course_id = :course_id")
            params["course_id"] = course_id
        if chapter_id:
            conds.append("chapter_id = :chapter_id")
            params["chapter_id"] = chapter_id
        if topic_id:
            conds.append("topic_id = :topic_id")
            params["topic_id"] = topic_id
        return conds, params

    def _search_postgres(
        self,
        vector: list[float],
        *,
        limit: int,
        course_id: str | None,
        chapter_id: str | None,
        topic_id: str | None,
        score_threshold: float | None,
    ) -> list[dict[str, Any]]:
        conds, params = self._filters_sql(course_id, chapter_id, topic_id)
        conds.append("vector IS NOT NULL")
        where = " AND ".join(conds)
        # pgvector bound params need a vector literal; psycopg3 adapts Python
        # lists to double precision[] which has no <=> operator, so pass the
        # vector as a text literal and CAST it in SQL.
        query_literal = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"
        params["query"] = query_literal
        params["limit"] = limit
        if score_threshold is not None:
            params["threshold"] = score_threshold
        threshold_sql = (
            " AND 1 - (vector <=> CAST(:query AS vector)) >= :threshold"
            if score_threshold is not None
            else ""
        )
        sql = (
            "SELECT id, document_id, course_id, chapter_id, topic_id, "
            "page_start, page_end, heading, content, source, "
            "1 - (vector <=> CAST(:query AS vector)) AS score "
            f"FROM content_chunks WHERE {where}{threshold_sql} "
            "ORDER BY vector <=> CAST(:query AS vector) LIMIT :limit"
        )
        try:
            with SessionLocal() as db:
                rows = db.execute(text(sql), params).mappings().all()
        except Exception as exc:  # noqa: BLE001
            log.warning("pgvector_search_failed: %s", exc)
            return []
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["score"] = round(float(item["score"] or 0.0), 4)
            out.append(item)
        return out


_store: VectorStore | None = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def reset_vector_store() -> None:
    global _store
    _store = None


def _temp_vector_store() -> VectorStore:
    return VectorStore()

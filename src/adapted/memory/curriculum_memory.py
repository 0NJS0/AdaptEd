from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import ContentChunk, Document
from ..rag.chunker import Chunk, chunk_document
from ..rag.embeddings import embed_texts
from ..rag.parser import ParsedDocument
from ..rag.vector_store import get_vector_store


def collection_for(course_id: str) -> str:
    return f"course_{course_id}"


def ensure_collection(course_id: str, dim: int | None = None) -> None:
    get_vector_store().ensure_collection(
        collection_for(course_id), dim=dim or settings.embedding_dim
    )


def index_document(
    db: Session,
    document: Document,
    parsed: ParsedDocument,
    *,
    dim: int | None = None,
) -> list[ContentChunk]:
    """Chunk, embed and store a document's content into curriculum memory
    (ContentChunk rows with pgvector embeddings)."""
    dim = dim or settings.embedding_dim
    collection = collection_for(document.course_id)
    store = get_vector_store()
    store.ensure_collection(document.course_id, dim=dim, db=db)
    store.delete_by_document(collection, document.id, db=db)

    db.execute(delete(ContentChunk).where(ContentChunk.document_id == document.id))

    chunks: list[Chunk] = chunk_document(parsed)
    contents = [c.content for c in chunks]
    vectors = embed_texts(contents, mode="passage")

    rows: list[ContentChunk] = []
    points: list[tuple[str, list[float], dict[str, Any]]] = []
    for chunk, vector in zip(chunks, vectors, strict=False):
        row = ContentChunk(
            document_id=document.id,
            course_id=document.course_id,
            chunk_index=chunk.index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            heading=chunk.heading,
            content=chunk.content,
            source=document.filename,
        )
        db.add(row)
        db.flush()
        rows.append(row)
        points.append(
            (
                row.id,
                vector,
                {
                    "document_id": document.id,
                    "course_id": document.course_id,
                    "chunk_id": row.id,
                    "chapter_id": None,
                    "topic_id": None,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "heading": chunk.heading or "",
                    "content": chunk.content,
                    "source": document.filename,
                },
            )
        )

    get_vector_store().upsert(collection, points, db=db)
    db.flush()
    return rows


def assign_chunk_topics(
    db: Session, course_id: str, chapter_id: str, topic_id: str, chunk_ids: list[str]
) -> None:
    if not chunk_ids:
        return
    for cid in chunk_ids:
        row = db.get(ContentChunk, cid)
        if row:
            row.chapter_id = chapter_id
            row.topic_id = topic_id
    db.flush()


def chunks_for_topic(db: Session, topic_id: str) -> list[ContentChunk]:
    return list(db.scalars(select(ContentChunk).where(ContentChunk.topic_id == topic_id)).all())


def chunks_by_course(db: Session, course_id: str) -> list[ContentChunk]:
    return list(
        db.scalars(
            select(ContentChunk)
            .where(ContentChunk.course_id == course_id)
            .order_by(ContentChunk.chunk_index)
        ).all()
    )

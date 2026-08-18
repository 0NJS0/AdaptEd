from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..config import settings
from .embeddings import embed_text
from .vector_store import get_vector_store


@dataclass
class RetrievedChunk:
    content: str
    score: float
    source: str | None = None
    page: int | None = None
    heading: str | None = None
    chapter_id: str | None = None
    topic_id: str | None = None
    course_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "score": round(float(self.score), 4),
            "source": self.source,
            "page": self.page,
            "heading": self.heading,
            "chapter_id": self.chapter_id,
            "topic_id": self.topic_id,
            "course_id": self.course_id,
        }


def retrieve(
    collection: str,
    query: str,
    *,
    course_id: str | None = None,
    chapter_id: str | None = None,
    topic_id: str | None = None,
    limit: int | None = None,
) -> list[RetrievedChunk]:
    vector = embed_text(query, mode="query")
    hits = get_vector_store().search(
        collection,
        vector,
        limit=limit or settings.rag_top_k,
        course_id=course_id,
        chapter_id=chapter_id,
        topic_id=topic_id,
    )
    chunks = []
    for h in hits:
        chunks.append(
            RetrievedChunk(
                content=str(h.get("content", "")),
                score=float(h.get("score", 0.0)),
                source=h.get("source"),
                page=h.get("page_start"),
                heading=h.get("heading"),
                chapter_id=h.get("chapter_id"),
                topic_id=h.get("topic_id"),
                course_id=h.get("course_id"),
            )
        )
    return chunks


def format_context(chunks: list[RetrievedChunk], with_citations: bool = True) -> str:
    if not chunks:
        return "No curriculum content was retrieved for this query."
    lines = []
    for i, c in enumerate(chunks, start=1):
        citation = ""
        if with_citations:
            parts = []
            if c.source:
                parts.append(c.source)
            if c.page:
                parts.append(f"p. {c.page}")
            if parts:
                citation = f" [Source: {', '.join(parts)}]"
        lines.append(f"[{i}]{citation}\n{c.content}")
    return "\n\n---\n\n".join(lines)

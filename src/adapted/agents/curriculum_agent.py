from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..logging.logger import get_logger
from ..memory import curriculum_memory
from ..models import (
    Chapter,
    ContentChunk,
    Course,
    Document,
    LearningObjective,
    Topic,
    TopicPrerequisite,
)
from ..rag.parser import parse_document
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.curriculum")


class ObjectiveOut(BaseModel):
    description: str


class TopicOut(BaseModel):
    title: str
    description: str = ""
    difficulty: float = 0.5
    objectives: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)


class ChapterOut(BaseModel):
    title: str
    description: str = ""
    order_index: int = 0
    topics: list[TopicOut] = Field(default_factory=list)


class CurriculumOutput(BaseModel):
    chapters: list[ChapterOut] = Field(default_factory=list)


class CurriculumAnalyzerAgent(BaseAgent):
    name = "curriculum_agent"
    actions: ClassVar[set[str]] = {"curriculum.analyze"}
    output_schema = CurriculumOutput

    def __init__(self, db, provider, bus) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        document_id = payload["document_id"]
        course_id = payload["course_id"]

        document = self.db.get(Document, document_id)
        course = self.db.get(Course, course_id)
        if document is None:
            raise ValueError(f"Document {document_id} not found")

        document.status = "processing"
        self.db.flush()

        from pathlib import Path

        parsed = parse_document(Path(document.storage_path), document.filename)
        document.page_count = parsed.page_count

        indexed = curriculum_memory.index_document(self.db, document, parsed)

        excerpt = parsed.pages[0].text[:2000] if parsed.pages else ""
        schema = CurriculumOutput.model_json_schema()
        result = self.provider.generate(self._build_request(course, document, excerpt, schema))

        chapters_created, topics_created, objectives_created, prereqs_created = (
            self._persist_curriculum(course_id, document.id, result, document.filename)
        )
        self._assign_chunks_to_topics(course_id, indexed)

        document.status = "ready"
        document.processed_at = None
        self.db.flush()

        topic_rows = list(
            self.db.scalars(
                select(Topic).where(Topic.course_id == course_id).order_by(Topic.order_index)
            )
        )
        return {
            "course_id": course_id,
            "chapters": [c.model_dump() for c in CurriculumOutput.model_validate(result).chapters],
            "chapters_created": chapters_created,
            "topics_created": topics_created,
            "objectives_created": objectives_created,
            "prerequisites_created": prereqs_created,
            "chunks_indexed": len(indexed),
            "total_topics": len(topic_rows),
        }

    def output_is_empty(self, output: dict[str, Any]) -> bool:
        return not output.get("chapters")

    def _build_request(self, course: Course, document: Document, excerpt: str, schema: dict) -> Any:
        from ..llm.base import LLMRequest

        prompt = (
            f"You are a curriculum analyst for the course '{course.title}' "
            f"({course.subject or 'unknown subject'}).\n"
            f"Analyze the following textbook excerpt and extract the chapter and topic "
            f"structure, learning objectives, prerequisites and a difficulty score (0..1) "
            f"for each topic.\n"
            f"Return JSON matching the schema.\n\n"
            f"--- DOCUMENT EXCERPT ---\n{excerpt}"
        )
        return LLMRequest(
            task="curriculum_extract",
            prompt=prompt,
            schema=schema,
            meta={
                "subject": course.subject or "",
                "doc_filename": document.filename,
                "text_excerpt": excerpt,
            },
        )

    def _persist_curriculum(
        self, course_id: str, document_id: str, result: dict, doc_filename: str
    ) -> tuple[int, int, int, int]:
        chapters_out = CurriculumOutput.model_validate(result).chapters
        self._doc_filename = f"Source: {doc_filename}"
        existing_chapters = list(
            self.db.scalars(select(Chapter).where(Chapter.course_id == course_id))
        )
        existing_topics = list(self.db.scalars(select(Topic).where(Topic.course_id == course_id)))
        existing_by_title = {t.title.lower(): t for t in existing_topics}

        # if this is a re-analysis, wipe previously extracted structure for the doc
        for ch in existing_chapters:
            if ch.document_id == document_id:
                self.db.delete(ch)
        self.db.flush()
        existing_topics = list(self.db.scalars(select(Topic).where(Topic.course_id == course_id)))
        existing_by_title = {t.title.lower(): t for t in existing_topics}

        chapters_created = topics_created = objectives_created = prereqs_created = 0

        for ch_out in chapters_out:
            chapter = Chapter(
                course_id=course_id,
                document_id=document_id,
                title=ch_out.title,
                order_index=ch_out.order_index,
                source_refs=self._doc_filename,
            )
            self.db.add(chapter)
            self.db.flush()
            chapters_created += 1

            for t_out in ch_out.topics:
                topic = existing_by_title.get(t_out.title.lower())
                if topic is None:
                    topic = Topic(
                        course_id=course_id,
                        chapter_id=chapter.id,
                        title=t_out.title,
                        order_index=len(chapter.topics) if chapter.topics else 0,
                        difficulty=t_out.difficulty,
                        description=t_out.description,
                    )
                    self.db.add(topic)
                    self.db.flush()
                    existing_by_title[t_out.title.lower()] = topic
                    topics_created += 1
                topic.chapter_id = chapter.id
                topic.difficulty = t_out.difficulty
                topic.description = t_out.description or topic.description

                for obj_desc in t_out.objectives:
                    self.db.add(
                        LearningObjective(
                            topic_id=topic.id,
                            description=obj_desc,
                            code=f"LO-{course_id[:4]}-{topic.id[:6]}",
                        )
                    )
                    objectives_created += 1

                for prereq_title in t_out.prerequisites:
                    prereq = existing_by_title.get(prereq_title.lower())
                    if prereq is None:
                        prereq = Topic(
                            course_id=course_id,
                            chapter_id=chapter.id,
                            title=prereq_title,
                            order_index=0,
                            difficulty=0.5,
                        )
                        self.db.add(prereq)
                        self.db.flush()
                        existing_by_title[prereq_title.lower()] = prereq
                    existing = self.db.scalars(
                        select(TopicPrerequisite).where(
                            TopicPrerequisite.topic_id == topic.id,
                            TopicPrerequisite.prereq_topic_id == prereq.id,
                        )
                    ).first()
                    if existing is None:
                        self.db.add(TopicPrerequisite(topic_id=topic.id, prereq_topic_id=prereq.id))
                        prereqs_created += 1

        self.db.flush()
        return chapters_created, topics_created, objectives_created, prereqs_created

    def _assign_chunks_to_topics(self, course_id: str, chunks: list[ContentChunk]) -> None:
        topics = list(self.db.scalars(select(Topic).where(Topic.course_id == course_id)))
        for chunk in chunks:
            heading = (chunk.heading or "").lower()
            for topic in topics:
                if topic.title.lower() in heading:
                    chunk.topic_id = topic.id
                    chunk.chapter_id = topic.chapter_id
                    break
        self.db.flush()

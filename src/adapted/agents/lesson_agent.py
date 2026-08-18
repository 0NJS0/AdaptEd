from __future__ import annotations

import json
from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..config import settings
from ..logging.logger import get_logger
from ..memory.student_memory import build_profile
from ..models import LearningObjective, Lesson, Topic
from ..rag.retriever import retrieve
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.lesson")


class SectionOut(BaseModel):
    name: str
    content: str


class LessonOutput(BaseModel):
    title: str
    level: str = "standard"
    sections: list[SectionOut] = Field(default_factory=list)
    references: list[dict] = Field(default_factory=list)


class LessonAgent(BaseAgent):
    name = "lesson_agent"
    actions: ClassVar[set[str]] = {"lesson.generate"}
    output_schema = LessonOutput

    def __init__(self, db, provider, bus) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        course_id = payload["course_id"]
        topic_id = payload["topic_id"]
        student_id = payload.get("student_id")
        level = payload.get("level") or "standard"

        topic = self.db.get(Topic, topic_id)
        if topic is None:
            raise ValueError(f"Topic {topic_id} not found")

        collection = f"course_{course_id}"
        chunks = retrieve(
            collection,
            topic.title,
            course_id=course_id,
            topic_id=topic_id,
            limit=settings.rag_top_k,
        )
        if not chunks:
            chunks = retrieve(
                collection,
                topic.title,
                course_id=course_id,
                limit=settings.rag_top_k,
            )

        chunk_meta = [c.to_dict() for c in chunks]
        objectives = [
            o.description
            for o in self.db.scalars(
                select(LearningObjective).where(LearningObjective.topic_id == topic_id)
            )
        ]

        profile = None
        student_context: dict[str, Any] = {}
        if student_id:
            profile = build_profile(self.db, student_id, course_id)
            student_context = {
                "mastery": profile.overall_mastery,
                "weak_topics": [w["topic_title"] for w in profile.weak_topics[:3]],
                "strong_topics": [s["topic_title"] for s in profile.strong_topics[:3]],
                "preferences": profile.preferences,
                "misconceptions": [m["label"] for m in profile.misconceptions[:3]],
                "recent_foci": [f["focus_topic"] for f in profile.conversation_foci[:3]],
            }

        schema = LessonOutput.model_json_schema()
        request = self._build_request(
            topic.title, level, chunk_meta, objectives, student_context, schema
        )
        result = self.provider.generate(request)
        lesson = LessonOutput.model_validate(result)

        lesson_row = Lesson(
            course_id=course_id,
            topic_id=topic_id,
            student_id=student_id,
            level=lesson.level,
            title=lesson.title,
            content=lesson.model_dump(),
            chunks_used=chunk_meta,
        )
        self.db.add(lesson_row)
        self.db.flush()

        return {
            "lesson_id": lesson_row.id,
            **lesson.model_dump(),
            "chunks_used": chunk_meta,
        }

    def output_is_empty(self, output: dict[str, Any]) -> bool:
        return not output.get("sections")

    def _build_request(
        self,
        topic_title: str,
        level: str,
        chunks: list[dict],
        objectives: list[str],
        student_context: dict,
        schema: dict,
    ) -> Any:
        from ..llm.base import LLMRequest

        context_block = json.dumps(chunks, ensure_ascii=False)
        prompt = (
            f"Create a lesson about '{topic_title}' at level '{level}' for this student.\n"
            f"Student context: {json.dumps(student_context, ensure_ascii=False)}\n"
            f"Learning objectives: {'; '.join(objectives) if objectives else 'none specified'}\n\n"
            f"Ground every claim in the curriculum chunks below. Include a Worked Example, "
            f"Practice Problems and Common Mistakes section. Do NOT invent curriculum facts "
            f"not present in the chunks; if a topic is not covered, say so.\n\n"
            f"--- CURRICULUM CONTEXT ---\n{context_block}"
        )
        return LLMRequest(
            task="lesson_generate",
            prompt=prompt,
            schema=schema,
            meta={
                "topic_title": topic_title,
                "level": level,
                "objectives": objectives,
                "chunks": chunks,
                "student_context": student_context,
            },
        )

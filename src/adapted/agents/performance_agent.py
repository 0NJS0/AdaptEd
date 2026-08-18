from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..logging.logger import get_logger
from ..memory import student_memory
from ..models import Answer, Misconception, Question, QuizAttempt, StudentMastery, Topic
from ..services import analytics
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.performance")


class TopicMasteryOut(BaseModel):
    topic_id: str
    topic_title: str
    mastery: float
    attempts: int
    status: str


class PerformanceOutput(BaseModel):
    student_id: str
    course_id: str
    weak_topics: list[dict] = Field(default_factory=list)
    strong_topics: list[dict] = Field(default_factory=list)
    topic_mastery: list[TopicMasteryOut] = Field(default_factory=list)
    misconceptions: list[dict] = Field(default_factory=list)


class PerformanceAnalysisAgent(BaseAgent):
    name = "performance_agent"
    actions: ClassVar[set[str]] = {"performance.analyze"}
    output_schema = PerformanceOutput

    def __init__(self, db, provider, bus) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        student_id = payload["student_id"]
        course_id = payload["course_id"]
        attempt_id = payload.get("attempt_id")

        attempt = self.db.get(QuizAttempt, attempt_id) if attempt_id else None

        # 1. Per-topic scores from this attempt
        if attempt:
            self._update_mastery_from_attempt(attempt, course_id)

        # 2. Misconception detection across recent wrong answers
        misconceptions = self._detect_misconceptions(student_id, course_id)

        # 3. Weak/strong topics from mastery memory
        mastery_rows = list(
            self.db.scalars(select(StudentMastery).where(StudentMastery.student_id == student_id))
        )
        records = []
        for row in mastery_rows:
            topic = self.db.get(Topic, row.topic_id)
            if topic and topic.course_id != course_id:
                continue
            records.append(
                {
                    "topic_id": row.topic_id,
                    "topic_title": topic.title if topic else row.topic_id,
                    "mastery": row.mastery,
                    "attempts": row.attempts,
                    "status": row.status,
                }
            )
        from ..services import mastery as mastery_svc

        rec_objs = [
            mastery_svc.build_record(
                r["topic_id"], r["topic_title"], r["mastery"], r["attempts"], []
            )
            for r in records
        ]
        weak, strong = analytics.weak_and_strong(rec_objs)

        return {
            "student_id": student_id,
            "course_id": course_id,
            "weak_topics": weak,
            "strong_topics": strong,
            "topic_mastery": [TopicMasteryOut(**r).model_dump() for r in records],
            "misconceptions": misconceptions,
        }

    def _update_mastery_from_attempt(self, attempt: QuizAttempt, course_id: str) -> None:
        by_topic: dict[str, list[Answer]] = {}
        for answer in attempt.answers:
            question = self.db.get(Question, answer.question_id)
            if question is None:
                continue
            topic_id = question.topic_id
            if topic_id:
                by_topic.setdefault(topic_id, []).append(answer)

        for topic_id, answers in by_topic.items():
            if not answers:
                continue
            score = sum(1 for a in answers if a.is_correct)
            pct = score / len(answers) * 100
            student_memory.update_topic_mastery(self.db, attempt.student_id, topic_id, pct)
            student_memory.record_study(
                self.db,
                attempt.student_id,
                course_id,
                activity_type="quiz",
                topic_id=topic_id,
                ref_id=attempt.id,
                details={"correct": score, "total": len(answers), "percentage": pct},
            )

    def _detect_misconceptions(self, student_id: str, course_id: str) -> list[dict]:
        answers = []
        attempts = self.db.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.student_id == student_id)
            .order_by(QuizAttempt.submitted_at.desc().nulls_last())
            .limit(20)
        )
        for attempt in attempts:
            for answer in attempt.answers:
                question = self.db.get(Question, answer.question_id)
                if question is None:
                    continue
                answers.append(
                    {
                        "is_correct": answer.is_correct,
                        "ai_score": answer.ai_score,
                        "response": answer.response,
                        "question": {
                            "topic_id": question.topic_id,
                            "topic_title": (
                                self.db.get(Topic, question.topic_id).title
                                if question.topic_id and self.db.get(Topic, question.topic_id)
                                else question.topic_id
                            ),
                        },
                    }
                )

        findings = analytics.detect_misconceptions(answers)
        persisted = []
        for f in findings:
            existing = self.db.scalars(
                select(Misconception).where(
                    Misconception.student_id == student_id,
                    Misconception.topic_id == f["topic_id"],
                    Misconception.label == f["label"],
                    Misconception.status == "open",
                )
            ).first()
            if existing is None:
                existing = Misconception(
                    student_id=student_id,
                    topic_id=f["topic_id"],
                    label=f["label"],
                    description=f["description"],
                    evidence=f["evidence"],
                )
                self.db.add(existing)
            persisted.append(f)
        self.db.flush()
        return persisted

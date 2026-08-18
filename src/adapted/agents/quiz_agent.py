from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..logging.logger import get_logger
from ..models import Question, Quiz, QuizQuestion, Topic
from ..services.grading import question_hash
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.quiz")


class GeneratedQuestion(BaseModel):
    question_type: str
    prompt: str
    choices: list[str] | None = None
    correct_answer: dict
    explanation: str = ""
    difficulty: float = 0.5
    source_ref: str | None = None


class QuizOutput(BaseModel):
    questions: list[GeneratedQuestion] = Field(default_factory=list)


class QuizAgent(BaseAgent):
    name = "quiz_agent"
    actions: ClassVar[set[str]] = {"quiz.generate"}
    output_schema = None  # LLM output validated against QuizOutput inside process()

    def __init__(self, db, provider, bus) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        course_id = payload["course_id"]
        topic_id = payload.get("topic_id")
        student_id = payload.get("student_id")
        count = int(payload.get("count", 10))
        difficulty = float(payload.get("difficulty", 0.5))
        question_types = payload.get("types") or ["mcq", "true_false", "numerical"]
        quiz_type = payload.get("quiz_type", "assessment")
        title = payload.get("title") or f"{quiz_type.replace('_', ' ').title()} Quiz"

        topic = self.db.get(Topic, topic_id) if topic_id else None
        variant = payload.get("variant", 0)
        existing_hashes = {
            h
            for h in self.db.scalars(
                select(Question.question_hash).where(Question.course_id == course_id)
            )
            if h
        }

        schema = QuizOutput.model_json_schema()
        request = self._build_request(
            topic, count, difficulty, question_types, existing_hashes, schema, variant
        )
        result = self.provider.generate(request)
        questions = QuizOutput.model_validate(result).questions

        if not questions:
            raise ValueError("Quiz agent produced no questions")

        question_rows: list[Question] = []
        for q in questions:
            h = question_hash(course_id, q.prompt)
            if h in existing_hashes:
                continue
            existing_hashes.add(h)
            row = Question(
                course_id=course_id,
                topic_id=topic_id,
                question_type=q.question_type,
                prompt=q.prompt,
                choices=q.choices,
                correct_answer=q.correct_answer,
                explanation=q.explanation,
                difficulty=q.difficulty,
                source_ref=q.source_ref,
                question_hash=h,
            )
            self.db.add(row)
            self.db.flush()
            question_rows.append(row)

        if not question_rows:
            # fallback: reuse existing course questions for the topic so a
            # reassessment can still be assembled when generation collides
            existing_rows = list(
                self.db.scalars(
                    select(Question)
                    .where(
                        Question.course_id == course_id,
                        Question.topic_id == (topic_id or None)
                        if topic_id
                        else Question.course_id == course_id,
                    )
                    .limit(count)
                )
            )
            if existing_rows:
                question_rows.extend(existing_rows)
            else:
                raise ValueError("No questions available for reassessment")

        quiz = Quiz(
            course_id=course_id,
            student_id=student_id,
            title=title,
            quiz_type=quiz_type,
            config={"topic_id": topic_id, "difficulty": difficulty},
            status="published",
        )
        self.db.add(quiz)
        self.db.flush()
        for i, q in enumerate(question_rows):
            self.db.add(
                QuizQuestion(
                    quiz_id=quiz.id,
                    question_id=q.id,
                    position=i,
                    assigned_difficulty=difficulty,
                )
            )
        self.db.flush()

        return {
            "quiz_id": quiz.id,
            "title": quiz.title,
            "quiz_type": quiz_type,
            "question_count": len(question_rows),
            "questions": [
                {
                    "id": q.id,
                    "question_type": q.question_type,
                    "prompt": q.prompt,
                    "choices": q.choices,
                    "difficulty": q.difficulty,
                    "topic_id": q.topic_id,
                }
                for q in question_rows
            ],
        }

    def output_is_empty(self, output: dict[str, Any]) -> bool:
        return not output.get("questions")

    def _build_request(
        self,
        topic: Topic | None,
        count: int,
        difficulty: float,
        question_types: list[str],
        existing_prompts: set[str],
        schema: dict,
        variant: int = 0,
    ) -> Any:
        from ..llm.base import LLMRequest

        topic_title = topic.title if topic else "this course"
        prompt = (
            f"Generate {count} curriculum-aligned {question_types} questions about "
            f"'{topic_title}' for a quiz.\n"
            f"Target difficulty {difficulty} (0=easy, 1=hard).\n"
            f"Each question must include: prompt, choices (for MCQ), correct_answer "
            f"(dict with 'value'), explanation, difficulty, optional source_ref.\n"
            f"Never duplicate these existing prompts: {sorted(existing_prompts)[:10]}.\n"
            f"Return JSON matching the schema."
        )
        return LLMRequest(
            task="quiz_generate",
            prompt=prompt,
            schema=schema,
            meta={
                "topic_title": topic_title,
                "count": count,
                "difficulty": difficulty,
                "types": question_types,
                "existing_prompts": sorted(existing_prompts),
                "variant": int(variant),
            },
        )

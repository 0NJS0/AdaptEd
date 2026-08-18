from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..logging.logger import get_logger
from ..models import Answer, Grade, Question, QuizAttempt
from ..services.grading import compute_attempt_score, grade_objective
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.grading")


class GradedAnswer(BaseModel):
    answer_id: str
    question_id: str
    is_correct: bool
    ai_score: float
    confidence: float
    explanation: str
    needs_teacher_review: bool


class GradingOutput(BaseModel):
    attempt_id: str
    score: float
    max_score: float
    percentage: float
    answers: list[GradedAnswer] = Field(default_factory=list)


class GradingAgent(BaseAgent):
    name = "grading_agent"
    actions: ClassVar[set[str]] = {"attempt.grade"}
    output_schema = GradingOutput

    def __init__(self, db, provider, bus) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        attempt_id = payload["attempt_id"]

        attempt = self.db.get(QuizAttempt, attempt_id)
        if attempt is None:
            raise ValueError(f"Attempt {attempt_id} not found")

        graded: list[tuple[bool, float]] = []
        results: list[GradedAnswer] = []

        for answer in list(attempt.answers):
            question = self.db.get(Question, answer.question_id)
            if question is None:
                continue
            is_correct, score, confidence, explanation = self._grade_one(question, answer)
            answer.is_correct = is_correct
            answer.ai_score = score
            answer.ai_confidence = confidence
            answer.ai_explanation = explanation
            answer.graded_by = "ai"
            answer.grading_status = "ai_graded"
            graded.append((is_correct, 1.0))
            needs_review = (
                question.question_type in ("short_answer", "problem") and confidence < 0.7
            )
            answer.needs_teacher_review = needs_review
            results.append(
                GradedAnswer(
                    answer_id=answer.id,
                    question_id=question.id,
                    is_correct=is_correct,
                    ai_score=score,
                    confidence=confidence,
                    explanation=explanation,
                    needs_teacher_review=needs_review,
                )
            )

        score, max_score = compute_attempt_score(graded)
        attempt.score = score
        attempt.max_score = max_score
        attempt.status = "graded"

        existing_grade = self.db.scalars(
            select(Grade).where(Grade.attempt_id == attempt_id)
        ).first()
        percentage = round(score / max_score * 100, 2) if max_score else 0.0
        if existing_grade is None:
            self.db.add(
                Grade(
                    attempt_id=attempt_id,
                    student_id=attempt.student_id,
                    score=score,
                    max_score=max_score,
                    percentage=percentage,
                )
            )
        else:
            existing_grade.score = score
            existing_grade.max_score = max_score
            existing_grade.percentage = percentage
        self.db.flush()

        return {
            "attempt_id": attempt_id,
            "score": score,
            "max_score": max_score,
            "percentage": percentage,
            "answers": [r.model_dump() for r in results],
        }

    def _grade_one(self, question: Question, answer: Answer) -> tuple[bool, float, float, str]:
        response = answer.response or {}
        qtype = question.question_type

        if qtype in ("mcq", "true_false", "numerical"):
            correct = grade_objective(
                {
                    "question_type": qtype,
                    "correct_answer": question.correct_answer,
                },
                response,
            )
            explanation = (
                "Correct." if correct else f"Expected: {question.correct_answer.get('value')}."
            )
            return correct, 1.0 if correct else 0.0, 1.0, explanation

        # subjective / problem questions -> LLM rubric grading with confidence
        return self._grade_subjective(question, response)

    def _grade_subjective(
        self, question: Question, response: dict
    ) -> tuple[bool, float, float, str]:
        from ..llm.base import LLMRequest

        student_text = str(response.get("value", ""))
        correct_text = str(question.correct_answer.get("value", ""))
        schema = {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "max_score": {"type": "number"},
                "confidence": {"type": "number"},
                "feedback": {"type": "string"},
                "correct": {"type": "boolean"},
            },
            "required": ["score", "max_score", "confidence", "feedback", "correct"],
        }
        prompt = (
            f"Grade the following short-answer question using a rubric (correctness 60%, "
            f"explanation 40%). Provide a confidence score for your grading.\n\n"
            f"Question: {question.prompt}\n"
            f"Expected answer: {correct_text}\n"
            f"Student response: {student_text}\n\n"
            f"Return JSON matching the schema."
        )
        request = LLMRequest(
            task="grade_subjective",
            prompt=prompt,
            schema=schema,
            meta={
                "question_prompt": question.prompt,
                "correct_answer": correct_text,
                "student_response": student_text,
                "max_score": 1.0,
            },
        )
        try:
            result = self.provider.generate(request)
        except Exception:  # noqa: BLE001
            result = {}
        max_score = float(result.get("max_score", 1.0))
        score = float(result.get("score", 0.0))
        confidence = float(result.get("confidence", 0.0))
        feedback = str(result.get("feedback", ""))
        correct = bool(result.get("correct", score >= max_score / 2))
        score = max(0.0, min(score, max_score))
        return correct, round(score / max_score if max_score else 0.0, 3), confidence, feedback

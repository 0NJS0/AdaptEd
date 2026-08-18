from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base
from ..database.session import new_id
from .user import utcnow

if TYPE_CHECKING:
    from .curriculum import Topic


class StudyPlan(Base):
    __tablename__ = "study_plans"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    daily_minutes: Mapped[int] = mapped_column(Integer, default=90)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active|completed|paused
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    items: Mapped[list[StudyPlanItem]] = relationship(
        back_populates="study_plan",
        cascade="all, delete-orphan",
        order_by="StudyPlanItem.day_index",
    )


class StudyPlanItem(Base):
    __tablename__ = "study_plan_items"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    study_plan_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("study_plans.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    day_index: Mapped[int] = mapped_column(Integer, default=0)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=45)
    goal: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending|in_progress|done|skipped
    reason: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # why this item exists / was added
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    study_plan: Mapped[StudyPlan] = relationship(back_populates="items")
    topic: Mapped[Topic] = relationship()


class Lesson(Base):
    __tablename__ = "lessons"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), nullable=True, index=True
    )
    level: Mapped[str] = mapped_column(String(20), default="standard")  # standard|remedial|advanced
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[dict] = mapped_column(JSON, default=dict)  # sections: explanation/examples/...
    chunks_used: Mapped[dict] = mapped_column(JSON, default=list)  # grounded chunk refs w/ pages
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True
    )
    learning_objective_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("learning_objectives.id", ondelete="SET NULL"), nullable=True
    )
    question_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # mcq|true_false|short_answer|numerical|problem
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    choices: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    correct_answer: Mapped[dict] = mapped_column(JSON, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    difficulty: Mapped[float] = mapped_column(Float, default=0.5)
    source_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="auto_generated"
    )  # auto_generated|teacher_approved|rejected
    question_hash: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    quiz_type: Mapped[str] = mapped_column(
        String(20), default="mixed"
    )  # assessment|mini_quiz|reassessment|practice
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="published")  # draft|published
    created_by: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    questions: Mapped[list[QuizQuestion]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.position"
    )
    attempts: Mapped[list[QuizAttempt]] = relationship(back_populates="quiz")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("quizzes.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer, default=0)
    assigned_difficulty: Mapped[float] = mapped_column(Float, default=0.5)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    question: Mapped[Question] = relationship()


class QuizAttempt(Base):
    __tablename__ = "quiz_attempts"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    quiz_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("quizzes.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(
        String(20), default="in_progress"
    )  # in_progress|submitted|graded
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    quiz: Mapped[Quiz] = relationship(back_populates="attempts")
    answers: Mapped[list[Answer]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True
    )
    question_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("questions.id", ondelete="CASCADE"), index=True
    )
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ai_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    teacher_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    teacher_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    graded_by: Mapped[str] = mapped_column(String(20), default="ai")  # ai|teacher
    grading_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending|ai_graded|teacher_reviewed
    needs_teacher_review: Mapped[bool] = mapped_column(Boolean, default=False)

    attempt: Mapped[QuizAttempt] = relationship(back_populates="answers")
    question: Mapped[Question] = relationship()


class Grade(Base):
    __tablename__ = "grades"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    attempt_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("quiz_attempts.id", ondelete="CASCADE"), index=True
    )
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0)
    max_score: Mapped[float] = mapped_column(Float, default=0)
    percentage: Mapped[float] = mapped_column(Float, default=0)
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base
from ..database.session import new_id
from .user import utcnow

if TYPE_CHECKING:
    from .curriculum import Topic
    from .user import Student


class StudentMastery(Base):
    __tablename__ = "student_mastery"
    __table_args__ = (UniqueConstraint("student_id", "topic_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    mastery: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    trend: Mapped[float] = mapped_column(Float, default=0.0)  # recent slope
    status: Mapped[str] = mapped_column(
        String(20), default="untested"
    )  # untested|weak|developing|proficient|mastered
    history: Mapped[dict] = mapped_column(JSON, default=list)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    topic: Mapped[Topic] = relationship()


class StudyHistory(Base):
    __tablename__ = "study_history"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    activity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # lesson|quiz|practice|review
    ref_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Misconception(Base):
    __tablename__ = "misconceptions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    topic_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|resolved
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    topic: Mapped[Topic | None] = relationship(
        primaryjoin="Misconception.topic_id == Topic.id",
        foreign_keys=[topic_id],
    )


class ConversationMemory(Base):
    __tablename__ = "conversation_memory"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="SET NULL"), nullable=True
    )
    focus_topic: Mapped[str] = mapped_column(String(255), nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, default=1)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    student: Mapped[Student] = relationship()


class LearningPreference(Base):
    __tablename__ = "learning_preferences"
    __table_args__ = (UniqueConstraint("user_id", "pref_key"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    pref_key: Mapped[str] = mapped_column(String(100), nullable=False)
    pref_value: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    student_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("students.user_id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    plan_item_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    action: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # review_topic|practice_more|mini_quiz|reassess|advance|schedule_revision|review_prerequisite
    topic_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    source_agent: Mapped[str] = mapped_column(String(50), default="recommendation_agent")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    needs_teacher_review: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open|applied|dismissed|reviewed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base, VectorColumn
from ..database.session import new_id
from .user import utcnow

if TYPE_CHECKING:
    from .course import Course, Document


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    source_refs: Mapped[str | None] = mapped_column(Text, nullable=True)

    course: Mapped[Course] = relationship(back_populates="chapters")
    topics: Mapped[list[Topic]] = relationship(
        back_populates="chapter", cascade="all, delete-orphan", order_by="Topic.order_index"
    )


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("chapters.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[float] = mapped_column(Float, default=0.5)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chapter: Mapped[Chapter] = relationship(back_populates="topics")
    learning_objectives: Mapped[list[LearningObjective]] = relationship(
        back_populates="topic", cascade="all, delete-orphan"
    )
    prerequisites: Mapped[list[TopicPrerequisite]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        foreign_keys="TopicPrerequisite.topic_id",
    )


class TopicPrerequisite(Base):
    __tablename__ = "topic_prerequisites"
    __table_args__ = (UniqueConstraint("topic_id", "prereq_topic_id"),)

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    topic_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    prereq_topic_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )

    topic: Mapped[Topic] = relationship(back_populates="prerequisites", foreign_keys=[topic_id])
    prereq_topic: Mapped[Topic] = relationship(foreign_keys=[prereq_topic_id])


class LearningObjective(Base):
    __tablename__ = "learning_objectives"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    topic_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    topic: Mapped[Topic] = relationship(back_populates="learning_objectives")


class ContentChunk(Base):
    __tablename__ = "content_chunks"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("courses.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("chapters.id", ondelete="SET NULL"), nullable=True
    )
    topic_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heading: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vector: Mapped[list[float] | None] = mapped_column(VectorColumn(), nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")

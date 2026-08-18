from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database.base import Base
from ..database.session import new_id

if TYPE_CHECKING:
    from .course import Course, Enrollment


def utcnow() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # teacher | student
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    teacher: Mapped[Teacher | None] = relationship(back_populates="user", uselist=False)
    student: Mapped[Student | None] = relationship(back_populates="user", uselist=False)


class Teacher(Base):
    __tablename__ = "teachers"

    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="teacher")
    courses: Mapped[list[Course]] = relationship(back_populates="teacher")


class Student(Base):
    __tablename__ = "students"

    user_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    grade_level: Mapped[str | None] = mapped_column(String(100), nullable=True)
    daily_study_minutes: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    user: Mapped[User] = relationship(back_populates="student")
    enrollments: Mapped[list[Enrollment]] = relationship(back_populates="student")

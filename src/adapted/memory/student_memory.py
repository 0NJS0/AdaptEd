from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    ConversationMemory,
    LearningPreference,
    Misconception,
    QuizAttempt,
    StudentMastery,
    StudyHistory,
    Topic,
)
from ..services import analytics
from ..services import mastery as mastery_svc


@dataclass
class StudentProfile:
    student_id: str
    course_id: str | None
    mastery: list[dict[str, Any]] = field(default_factory=list)
    overall_mastery: float = 0.0
    weak_topics: list[dict[str, Any]] = field(default_factory=list)
    strong_topics: list[dict[str, Any]] = field(default_factory=list)
    misconceptions: list[dict[str, Any]] = field(default_factory=list)
    preferences: dict[str, str] = field(default_factory=dict)
    recent_quiz: dict[str, Any] | None = None
    conversation_foci: list[dict[str, Any]] = field(default_factory=list)
    study_history_recent: list[dict[str, Any]] = field(default_factory=list)


def build_profile(db: Session, student_id: str, course_id: str | None = None) -> StudentProfile:
    q = select(StudentMastery).where(StudentMastery.student_id == student_id)
    if course_id:
        q = q.join(Topic).where(Topic.course_id == course_id)
    mastery_rows = list(db.scalars(q).all())

    records = []
    for row in mastery_rows:
        title = row.topic.title if row.topic else row.topic_id
        records.append(
            mastery_svc.build_record(
                row.topic_id, title, row.mastery, row.attempts, list(row.history or [])
            )
        )

    weak, strong = analytics.weak_and_strong(records)
    tested = [r.mastery for r in records if r.status != "untested"]
    overall = round(sum(tested) / len(tested), 2) if tested else 0.0

    misconceptions = [
        {
            "id": m.id,
            "label": m.label,
            "description": m.description,
            "status": m.status,
            "topic_id": m.topic_id,
            "topic_title": m.topic.title if m.topic else None,
        }
        for m in db.scalars(
            select(Misconception)
            .where(Misconception.student_id == student_id, Misconception.status == "open")
            .order_by(Misconception.created_at.desc())
        )
    ]

    prefs = {
        p.pref_key: p.pref_value
        for p in db.scalars(
            select(LearningPreference).where(LearningPreference.user_id == student_id)
        )
    }

    recent_attempt = db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.student_id == student_id)
        .order_by(QuizAttempt.submitted_at.desc().nulls_last())
        .limit(1)
    ).first()
    recent_quiz = None
    if recent_attempt and recent_attempt.status in ("submitted", "graded"):
        recent_quiz = {
            "quiz_title": recent_attempt.quiz.title if recent_attempt.quiz else "Quiz",
            "score": recent_attempt.score,
            "max_score": recent_attempt.max_score,
            "submitted_at": recent_attempt.submitted_at,
            "attempt_id": recent_attempt.id,
        }

    foci = [
        {
            "focus_topic": f.focus_topic,
            "frequency": f.frequency,
            "last_seen": f.last_seen,
            "summary": f.summary,
        }
        for f in db.scalars(
            select(ConversationMemory)
            .where(ConversationMemory.student_id == student_id)
            .order_by(ConversationMemory.frequency.desc())
            .limit(5)
        )
    ]

    history = [
        {
            "activity_type": h.activity_type,
            "topic_id": h.topic_id,
            "details": h.details,
            "occurred_at": h.occurred_at,
        }
        for h in db.scalars(
            select(StudyHistory)
            .where(StudyHistory.student_id == student_id)
            .order_by(StudyHistory.occurred_at.desc())
            .limit(10)
        )
    ]

    return StudentProfile(
        student_id=student_id,
        course_id=course_id,
        mastery=[r.__dict__ | {"topic_title": r.topic_title} for r in records],
        overall_mastery=overall,
        weak_topics=weak,
        strong_topics=strong,
        misconceptions=misconceptions,
        preferences=prefs,
        recent_quiz=recent_quiz,
        conversation_foci=foci,
        study_history_recent=history,
    )


def update_topic_mastery(
    db: Session, student_id: str, topic_id: str, score_percent: float
) -> StudentMastery:
    row = db.scalars(
        select(StudentMastery).where(
            StudentMastery.student_id == student_id, StudentMastery.topic_id == topic_id
        )
    ).first()
    if row is None:
        row = StudentMastery(
            student_id=student_id,
            topic_id=topic_id,
            mastery=0.0,
            attempts=0,
            history=[],
        )
        db.add(row)
    history = list(row.history or [])
    history.append(round(float(score_percent), 2))
    row.history = history[-20:]
    row.attempts = row.attempts + 1
    row.mastery = mastery_svc.update_mastery(row.mastery, row.attempts, float(score_percent))
    row.trend = mastery_svc.compute_trend(row.history)
    row.status = mastery_svc.status_for(row.mastery)
    row.last_updated = func.now()
    db.flush()
    return row


def record_study(
    db: Session,
    student_id: str,
    course_id: str,
    activity_type: str,
    topic_id: str | None = None,
    ref_id: str | None = None,
    details: dict | None = None,
) -> StudyHistory:
    entry = StudyHistory(
        student_id=student_id,
        course_id=course_id,
        topic_id=topic_id,
        activity_type=activity_type,
        ref_id=ref_id,
        details=details or {},
    )
    db.add(entry)
    db.flush()
    return entry


def record_conversation(
    db: Session, student_id: str, course_id: str | None, focus: str, summary: str = ""
) -> None:
    row = db.scalars(
        select(ConversationMemory).where(
            ConversationMemory.student_id == student_id,
            ConversationMemory.focus_topic == focus,
        )
    ).first()
    if row is None:
        row = ConversationMemory(
            student_id=student_id, course_id=course_id, focus_topic=focus, summary=summary
        )
        db.add(row)
    else:
        row.frequency += 1
        row.summary = summary or row.summary
    row.last_seen = func.now()
    db.flush()


def set_preference(db: Session, user_id: str, key: str, value: str) -> LearningPreference:
    row = db.scalars(
        select(LearningPreference).where(
            LearningPreference.user_id == user_id, LearningPreference.pref_key == key
        )
    ).first()
    if row is None:
        row = LearningPreference(user_id=user_id, pref_key=key, pref_value=value)
        db.add(row)
    else:
        row.pref_value = value
    db.flush()
    return row

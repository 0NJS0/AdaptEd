from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...memory.student_memory import build_profile, set_preference
from ...models import (
    Course,
    Recommendation,
    User,
)
from ...models import (
    Enrollment as _E,
)
from ...schemas.api import MasteryOut, MisconceptionOut, PerformanceOut, RecommendationOut
from ..deps import AnyUserDep

router = APIRouter(prefix="/students", tags=["students"])


def _authorize(db: Session, user: User, student_id: str, course_id: str | None = None) -> None:
    if user.role == "teacher":
        if course_id is not None:
            course = db.get(Course, course_id)
            if course is None or course.teacher_id != user.id:
                raise HTTPException(404, "Course not found or not yours")
        # verify the student is enrolled in any course owned by the teacher
        enrolled = db.scalars(
            select(_E)
            .join(Course, Course.id == _E.course_id)
            .where(_E.student_id == student_id, Course.teacher_id == user.id)
            .limit(1)
        ).first()
        if enrolled is None and course_id is not None:
            raise HTTPException(403, "Student not in this course")
    else:
        if user.id != student_id:
            raise HTTPException(403, "Can only access your own data")


@router.get("/{student_id}/profile", response_model=dict)
def get_student_profile(
    student_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _authorize(db, user, student_id)
    profile = build_profile(db, student_id)
    return {
        "student_id": student_id,
        "overall_mastery": profile.overall_mastery,
        "weak_topics": profile.weak_topics,
        "strong_topics": profile.strong_topics,
        "mastery": profile.mastery,
        "misconceptions": profile.misconceptions,
        "preferences": profile.preferences,
        "recent_quiz": profile.recent_quiz,
        "conversation_foci": profile.conversation_foci,
        "study_history": profile.study_history_recent,
    }


@router.get("/{student_id}/performance", response_model=PerformanceOut)
def get_performance(
    student_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> PerformanceOut:
    course_id = _default_course_id(db, user, student_id)
    _authorize(db, user, student_id, course_id)
    profile = build_profile(db, student_id, course_id)
    return PerformanceOut(
        student_id=student_id,
        course_id=course_id,
        weak_topics=profile.weak_topics,
        strong_topics=profile.strong_topics,
        topic_mastery=[
            MasteryOut(
                topic_id=m["topic_id"],
                topic_title=m["topic_title"],
                mastery=m["mastery"],
                attempts=m["attempts"],
                status=m["status"],
            )
            for m in profile.mastery
        ],
        misconceptions=[MisconceptionOut(**m) for m in profile.misconceptions],
    )


@router.get("/{student_id}/mastery", response_model=dict)
def get_mastery(
    student_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    course_id = _default_course_id(db, user, student_id)
    _authorize(db, user, student_id, course_id)
    profile = build_profile(db, student_id, course_id)
    return {
        "overall_mastery": profile.overall_mastery,
        "topics": profile.mastery,
    }


@router.get("/{student_id}/recommendations", response_model=list[RecommendationOut])
def get_recommendations(
    student_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[RecommendationOut]:
    course_id = _default_course_id(db, user, student_id)
    _authorize(db, user, student_id, course_id)
    rows = list(
        db.scalars(
            select(Recommendation)
            .where(Recommendation.student_id == student_id)
            .order_by(Recommendation.created_at.desc())
            .limit(20)
        )
    )
    return [RecommendationOut.model_validate(r) for r in rows]


@router.patch("/{student_id}/recommendations/{recommendation_id}", response_model=RecommendationOut)
def update_recommendation(
    student_id: str,
    recommendation_id: str,
    body: dict,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> RecommendationOut:
    rec = db.get(Recommendation, recommendation_id)
    if rec is None or rec.student_id != student_id:
        raise HTTPException(404, "Recommendation not found")
    if "status" in body and body["status"] in ("open", "applied", "dismissed", "reviewed"):
        rec.status = body["status"]
        db.commit()
        db.refresh(rec)
    return RecommendationOut.model_validate(rec)


@router.post("/{student_id}/preferences", response_model=dict)
def set_student_preference(
    student_id: str,
    body: dict,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _authorize(db, user, student_id)
    key = body.get("key")
    value = body.get("value")
    if not key or value is None:
        raise HTTPException(400, "key and value required")
    set_preference(db, student_id, str(key), str(value))
    db.commit()
    return {"key": key, "value": value}


def _default_course_id(db: Session, user: User, student_id: str) -> str | None:
    if user.role == "student":
        row = db.scalars(
            select(_E).where(_E.student_id == student_id).order_by(_E.joined_at.desc()).limit(1)
        ).first()
        return row.course_id if row else None
    row = db.scalars(
        select(_E)
        .join(Course, Course.id == _E.course_id)
        .where(_E.student_id == student_id, Course.teacher_id == user.id)
        .order_by(_E.joined_at.desc())
        .limit(1)
    ).first()
    return row.course_id if row else None

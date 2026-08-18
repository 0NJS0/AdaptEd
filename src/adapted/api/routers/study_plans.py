from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...models import Course, StudyPlan, StudyPlanItem, User
from ...schemas.api import PlanItemOut, StudyPlanOut
from ..deps import AnyUserDep, assert_student_enrolled

router = APIRouter(prefix="/study-plans", tags=["study-plans"])
router2 = APIRouter(prefix="/students", tags=["study-plans"])


def _plan_out(db: Session, plan: StudyPlan) -> StudyPlanOut:
    items = list(
        db.scalars(
            select(StudyPlanItem)
            .where(StudyPlanItem.study_plan_id == plan.id)
            .order_by(StudyPlanItem.day_index, StudyPlanItem.sequence)
        )
    )
    return StudyPlanOut(
        id=plan.id,
        student_id=plan.student_id,
        course_id=plan.course_id,
        version=plan.version,
        exam_date=plan.exam_date,
        daily_minutes=plan.daily_minutes,
        status=plan.status,
        created_at=plan.created_at,
        items=[
            PlanItemOut(
                id=i.id,
                topic_id=i.topic_id,
                title=i.topic.title if i.topic else i.topic_id,
                day_index=i.day_index,
                sequence=i.sequence,
                estimated_minutes=i.estimated_minutes,
                goal=i.goal,
                reason=i.reason,
                status=i.status,
            )
            for i in items
        ],
    )


@router.get("/{student_id}/{course_id}", response_model=StudyPlanOut)
def get_study_plan(
    student_id: str,
    course_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> StudyPlanOut:
    _authorize(db, user, course_id, student_id)
    plan = db.scalars(
        select(StudyPlan)
        .where(
            StudyPlan.student_id == student_id,
            StudyPlan.course_id == course_id,
            StudyPlan.status == "active",
        )
        .order_by(StudyPlan.version.desc())
        .limit(1)
    ).first()
    if plan is None:
        raise HTTPException(404, "No study plan yet - create one first")
    return _plan_out(db, plan)


@router2.get("/{student_id}/study-plan", response_model=StudyPlanOut)
def get_student_study_plan(
    student_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> StudyPlanOut:
    """Latest active plan for a student across their courses."""
    plan = db.scalars(
        select(StudyPlan)
        .where(StudyPlan.student_id == student_id, StudyPlan.status == "active")
        .order_by(StudyPlan.version.desc())
        .limit(1)
    ).first()
    if plan is None:
        raise HTTPException(404, "No study plan yet - create one first")
    _authorize(db, user, plan.course_id, student_id)
    return _plan_out(db, plan)


def _authorize(db: Session, user: User, course_id: str, student_id: str) -> None:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if user.role == "teacher":
        if course.teacher_id != user.id:
            raise HTTPException(403, "Not your course")
    else:
        if user.id != student_id:
            raise HTTPException(403, "Can only view your own plan")
        assert_student_enrolled(db, course_id, student_id)

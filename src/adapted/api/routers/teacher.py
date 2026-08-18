from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...memory.student_memory import build_profile
from ...models import (
    Answer,
    Course,
    Enrollment,
    Grade,
    Question,
    Quiz,
    QuizAttempt,
    Student,
    StudentMastery,
    Topic,
    User,
)
from ...services import mastery as mastery_svc
from ...services.analytics import class_topic_summary
from ..deps import TeacherDep, assert_course_owner

router = APIRouter(prefix="/classes", tags=["teacher"])


@router.get("/{course_id}/students", response_model=list[dict])
def class_students(
    course_id: str,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    assert_course_owner(db, course_id, teacher.id)
    rows = db.execute(
        select(Student, User)
        .join(User, User.id == Student.user_id)
        .join(Enrollment, Enrollment.student_id == Student.user_id)
        .where(Enrollment.course_id == course_id)
    ).all()
    return [
        {
            "student_id": s.user_id,
            "name": u.full_name,
            "email": u.email,
            "grade_level": s.grade_level,
            "daily_study_minutes": s.daily_study_minutes,
        }
        for s, u in rows
    ]


@router.get("/{course_id}/analytics", response_model=dict)
def class_analytics(
    course_id: str,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    assert_course_owner(db, course_id, teacher.id)
    course = db.get(Course, course_id)

    enrollments = list(db.scalars(select(Enrollment).where(Enrollment.course_id == course_id)))
    students = [e.student_id for e in enrollments]

    mastery_by_student: dict[str, list] = {}
    for sid in students:
        profile = build_profile(db, sid, course_id)
        recs = []
        for m in profile.mastery:
            recs.append(
                mastery_svc.build_record(
                    m["topic_id"], m["topic_title"], m["mastery"], m["attempts"], []
                )
            )
        mastery_by_student[sid] = recs

    topic_summary = class_topic_summary(mastery_by_student)

    weak_topics = [t for t in topic_summary if t["avg_mastery"] < 60.0]
    curriculum_progress = 0.0
    topics = list(db.scalars(select(Topic).where(Topic.course_id == course_id)))
    if topics:
        tested = [
            m
            for sid in students
            for m in db.scalars(select(StudentMastery).where(StudentMastery.student_id == sid))
        ]
        avg = sum(m.mastery for m in tested) / len(tested) if tested else 0.0
        curriculum_progress = round(avg, 2)

    return {
        "course_id": course_id,
        "title": course.title,
        "student_count": len(students),
        "curriculum_progress": curriculum_progress,
        "topic_mastery": topic_summary,
        "topics_needing_attention": weak_topics,
    }


@router.get("/{course_id}/students/{student_id}/grades", response_model=list[dict])
def student_grades(
    course_id: str,
    student_id: str,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    assert_course_owner(db, course_id, teacher.id)
    attempts = list(
        db.scalars(
            select(QuizAttempt)
            .where(QuizAttempt.student_id == student_id)
            .order_by(QuizAttempt.submitted_at.desc())
        )
    )
    out = []
    for a in attempts:
        quiz = db.get(Quiz, a.quiz_id)
        if quiz and quiz.course_id != course_id:
            continue
        grade = db.scalars(select(Grade).where(Grade.attempt_id == a.id)).first()
        out.append(
            {
                "attempt_id": a.id,
                "quiz_id": a.quiz_id,
                "quiz_title": quiz.title if quiz else "Quiz",
                "status": a.status,
                "score": a.score,
                "max_score": a.max_score,
                "percentage": grade.percentage
                if grade
                else (a.score / a.max_score * 100 if a.max_score else 0),
                "submitted_at": a.submitted_at,
            }
        )
    return out


@router.get("/quizzes/pending-review", response_model=list[dict])
def pending_review(
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[dict]:
    """Answers the teacher should review: their own students' low-confidence AI
    grading (subjective questions flagged by the grading agent)."""
    answers = list(
        db.scalars(
            select(Answer)
            .join(QuizAttempt, QuizAttempt.id == Answer.attempt_id)
            .join(Quiz, Quiz.id == QuizAttempt.quiz_id)
            .join(Course, Course.id == Quiz.course_id)
            .where(
                Course.teacher_id == teacher.id,
                Answer.grading_status == "ai_graded",
                Answer.needs_teacher_review.is_(True),
            )
            .order_by(Answer.ai_confidence.asc().nulls_last())
            .limit(100)
        )
    )
    out = []
    for a in answers:
        question = db.get(Question, a.question_id)
        if question is None:
            continue
        out.append(
            {
                "answer_id": a.id,
                "attempt_id": a.attempt_id,
                "question_id": a.question_id,
                "prompt": question.prompt[:300],
                "response": a.response,
                "ai_score": a.ai_score,
                "ai_confidence": a.ai_confidence,
                "explanation": a.ai_explanation,
                "question_type": question.question_type,
            }
        )
    return out


@router.patch("/answers/{answer_id}", response_model=dict)
def override_grade(
    answer_id: str,
    body: dict,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """Teacher overrides an AI grade. Graded_by becomes 'teacher'."""
    answer = db.get(Answer, answer_id)
    if answer is None:
        raise HTTPException(404, "Answer not found")
    if "score" in body:
        answer.teacher_score = float(body["score"])
    if "feedback" in body:
        answer.teacher_feedback = str(body["feedback"])
    answer.graded_by = "teacher"
    answer.grading_status = "teacher_reviewed"
    if "is_correct" in body:
        answer.is_correct = bool(body["is_correct"])
    db.commit()
    return {"answer_id": answer_id, "status": "overridden", "graded_by": "teacher"}

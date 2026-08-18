from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...logging.logger import get_logger
from ...models import (
    Answer,
    Course,
    Enrollment,
    Question,
    Quiz,
    QuizAttempt,
    QuizQuestion,
    Student,
)
from ...schemas.api import (
    PipelineResult,
    QuestionOut,
    QuizGenerateRequest,
    QuizOut,
    QuizSubmitRequest,
)
from ...tasks.runner import submit_pipeline
from ..deps import AnyUserDep

log = get_logger("adapted.api.quizzes")

router = APIRouter(prefix="/quizzes", tags=["quizzes"])


@router.post("/generate", response_model=PipelineResult, status_code=201)
def generate_quiz(
    body: QuizGenerateRequest,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> PipelineResult:
    """Kick off quiz generation in the background.

    Returns immediately with a task id; poll ``GET /agent/tasks/{task_id}``.
    On success ``result.context.quiz_agent.quiz_id`` names the new quiz (fetch
    it via ``GET /quizzes/{quiz_id}``). Fast checks (course existence,
    ownership) run synchronously.
    """
    course = db.get(Course, body.course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if user.role == "teacher" and course.teacher_id != user.id:
        raise HTTPException(403, "Not your course")
    if user.role == "student":
        enrolled = db.scalars(
            select(Enrollment).where(
                Enrollment.course_id == body.course_id, Enrollment.student_id == user.id
            )
        ).first()
        if enrolled is None:
            raise HTTPException(403, "Not enrolled in this course")
        body.student_id = user.id

    try:
        task_id, correlation_id = submit_pipeline("generate_quiz", body.model_dump(), user.id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        log.error("quiz_submit_error", course_id=body.course_id, error=str(exc))
        raise HTTPException(500, f"Quiz generation submission failed: {exc}") from exc
    return PipelineResult(task_id=task_id, correlation_id=correlation_id, status="started")


@router.get("/{quiz_id}", response_model=QuizOut)
def get_quiz(
    quiz_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> QuizOut:
    return _quiz_out(db, quiz_id)


@router.post("/{quiz_id}/submit", response_model=dict)
def submit_quiz(
    quiz_id: str,
    body: QuizSubmitRequest,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict[str, Any]:
    """Record a quiz submission and kick off the adaptive pipeline in the
    background.

    The fast, synchronous part persists the Attempt + Answer rows (so the
    duplicate-submit guard holds and the worker thread can read them with its
    own session), then the graded chain (grade -> analyze -> recommend ->
    adapt plan -> targeted lesson -> reassessment) runs in a background worker.
    Returns immediately with the task id; poll ``GET /agent/tasks/{task_id}``.
    On success the task's ``result.context`` holds the ``grading_agent``,
    ``performance_agent``, ``recommendation_agent``, ``planner_agent``,
    ``lesson_agent`` and ``quiz_agent`` outputs (the same shape the old
    synchronous response returned).
    """
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "Quiz not found")
    if user.role == "student" and quiz.student_id not in (None, user.id):
        raise HTTPException(403, "Not your quiz")
    if not quiz.questions:
        raise HTTPException(400, "Quiz has no questions")

    student_id = user.id if user.role == "student" else (quiz.student_id or user.id)
    if db.get(Student, student_id) is None:
        # QuizAttempt.student_id FKs to students; a teacher (or a quiz bound
        # to a student id that no longer resolves) would otherwise crash the
        # request with a 500 IntegrityError.
        raise HTTPException(
            400,
            "Quizzes are submitted by enrolled students; no student profile exists for this account.",
        )
    existing = db.scalars(
        select(QuizAttempt).where(
            QuizAttempt.quiz_id == quiz_id,
            QuizAttempt.student_id == student_id,
            QuizAttempt.status.in_(["submitted", "graded"]),
        )
    ).first()
    if existing:
        raise HTTPException(400, "Quiz already submitted by this student")

    attempt = QuizAttempt(
        quiz_id=quiz_id,
        student_id=student_id,
        status="submitted",
    )
    db.add(attempt)
    db.flush()

    for qq in sorted(quiz.questions, key=lambda x: x.position):
        response = body.answers.get(qq.question_id, {})
        db.add(
            Answer(
                attempt_id=attempt.id,
                question_id=qq.question_id,
                response=response,
            )
        )
    # commit now: the background worker uses its OWN session (SQLAlchemy is not
    # thread-safe) and must see the attempt + answers already persisted.
    db.commit()

    try:
        task_id, correlation_id = submit_pipeline(
            "quiz_submit",
            {
                "attempt_id": attempt.id,
                "course_id": quiz.course_id,
                "student_id": student_id,
            },
            user.id,
        )
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        log.error("quiz_submit_error", quiz_id=quiz_id, error=str(exc))
        raise HTTPException(500, f"Quiz submission failed: {exc}") from exc

    return {
        "task_id": task_id,
        "correlation_id": correlation_id,
        "status": "started",
        "attempt_id": attempt.id,
        "quiz_id": quiz_id,
    }


def _quiz_out(db: Session, quiz_id: str) -> QuizOut:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(404, "Quiz not found")
    qq_rows = list(
        db.scalars(
            select(QuizQuestion)
            .where(QuizQuestion.quiz_id == quiz_id)
            .order_by(QuizQuestion.position)
        )
    )
    questions = []
    for qq in qq_rows:
        q = db.get(Question, qq.question_id)
        if q is None:
            continue
        questions.append(
            QuestionOut(
                id=q.id,
                question_type=q.question_type,
                prompt=q.prompt,
                choices=q.choices,
                difficulty=qq.assigned_difficulty or q.difficulty,
                topic_id=q.topic_id,
                explanation=q.explanation,
            )
        )
    return QuizOut(
        id=quiz.id,
        course_id=quiz.course_id,
        student_id=quiz.student_id,
        title=quiz.title,
        quiz_type=quiz.quiz_type,
        status=quiz.status,
        created_at=quiz.created_at,
        questions=questions,
    )

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...logging.logger import get_logger
from ...models import Course, Lesson
from ...schemas.api import LessonOut, PipelineResult
from ...tasks.runner import submit_pipeline
from ..deps import AnyUserDep

log = get_logger("adapted.api.lessons")
router = APIRouter(prefix="/lessons", tags=["lessons"])


class LessonGenerateRequest(BaseModel):
    course_id: str
    topic_id: str
    student_id: str | None = None
    level: str = "standard"


@router.post("/generate", response_model=PipelineResult, status_code=201)
def generate_lesson(
    body: LessonGenerateRequest,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> PipelineResult:
    """Kick off lesson generation in the background.

    Returns immediately with a task id; poll ``GET /agent/tasks/{task_id}``.
    On success the task's ``result.context.lesson_agent.lesson_id`` names the
    generated lesson (fetch it via ``GET /lessons/{lesson_id}``). Fast checks
    (course existence, ownership) run synchronously so invalid requests still
    fail fast instead of queuing a doomed background run.
    """
    course = db.get(Course, body.course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if user.role == "student" and user.id != body.student_id:
        raise HTTPException(403, "Cannot generate a lesson for another student")
    try:
        task_id, correlation_id = submit_pipeline("generate_lesson", body.model_dump(), user.id)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    except Exception as exc:
        log.error("lesson_submit_error", course_id=body.course_id, error=str(exc))
        raise HTTPException(500, f"Lesson generation submission failed: {exc}") from exc
    return PipelineResult(task_id=task_id, correlation_id=correlation_id, status="started")


@router.get("/{lesson_id}", response_model=LessonOut)
def get_lesson(
    lesson_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> LessonOut:
    lesson = db.get(Lesson, lesson_id)
    if lesson is None:
        raise HTTPException(404, "Lesson not found")
    course = db.get(Course, lesson.course_id)
    if user.role == "teacher" and course.teacher_id != user.id:
        raise HTTPException(403, "Not your course")
    if user.role == "student" and lesson.student_id not in (None, user.id):
        raise HTTPException(403, "Not your lesson")
    return lesson

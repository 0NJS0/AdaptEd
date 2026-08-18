from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...models import (
    Chapter,
    Course,
    LearningObjective,
    Topic,
)
from ...schemas.api import ChapterOut, CurriculumOut, TopicOut
from ..deps import AnyUserDep

router = APIRouter(prefix="/courses", tags=["curriculum"])


def _topic_out(db: Session, t: Topic) -> TopicOut:
    objectives = [
        o.description
        for o in db.scalars(select(LearningObjective).where(LearningObjective.topic_id == t.id))
    ]
    prereqs = [
        p.prereq_topic.title if p.prereq_topic else ""
        for p in (t.prerequisites or [])
        if p.prereq_topic
    ]
    return TopicOut(
        id=t.id,
        chapter_id=t.chapter_id,
        title=t.title,
        order_index=t.order_index,
        difficulty=t.difficulty,
        description=t.description,
        objectives=objectives,
        prerequisites=prereqs,
    )


@router.get("/{course_id}/curriculum", response_model=CurriculumOut)
def get_curriculum(
    course_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> CurriculumOut:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if user.role == "teacher" and course.teacher_id != user.id:
        raise HTTPException(403, "Not your course")

    chapters = list(
        db.scalars(
            select(Chapter).where(Chapter.course_id == course_id).order_by(Chapter.order_index)
        )
    )
    topics = list(
        db.scalars(select(Topic).where(Topic.course_id == course_id).order_by(Topic.order_index))
    )
    by_chapter: dict[str, list[Topic]] = {}
    for t in topics:
        by_chapter.setdefault(t.chapter_id, []).append(t)

    chapters_out = []
    for ch in chapters:
        chapters_out.append(
            ChapterOut(
                id=ch.id,
                course_id=ch.course_id,
                title=ch.title,
                order_index=ch.order_index,
                source_refs=ch.source_refs,
                topics=[_topic_out(db, t) for t in by_chapter.get(ch.id, [])],
            )
        )
    return CurriculumOut(course_id=course_id, chapters=chapters_out)


@router.get("/{course_id}/topics/{topic_id}", response_model=TopicOut)
def get_topic(
    course_id: str,
    topic_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> TopicOut:
    topic = db.get(Topic, topic_id)
    if topic is None or topic.course_id != course_id:
        raise HTTPException(404, "Topic not found")
    return _topic_out(db, topic)

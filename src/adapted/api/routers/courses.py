from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ...config import settings
from ...database.session import get_db
from ...logging.logger import get_logger
from ...models import (
    Chapter,
    ContentChunk,
    ConversationMemory,
    Course,
    Document,
    Enrollment,
    Lesson,
    Question,
    Quiz,
    Recommendation,
    Student,
    StudyHistory,
    StudyPlan,
    User,
)
from ...models.observability import AuditLog
from ...rag.parser import SUPPORTED_EXTENSIONS
from ...schemas.api import (
    CourseCreate,
    CourseOut,
    DocumentOut,
    EnrollRequest,
)
from ..deps import (
    AnyUserDep,
    TeacherDep,
    assert_course_owner,
    get_teacher_row,
)

log = get_logger("adapted.api.courses")
router = APIRouter(prefix="/courses", tags=["courses"])


# ---------------------------------------------------------------- courses


@router.post("", response_model=CourseOut, status_code=201)
def create_course(
    body: CourseCreate,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> CourseOut:
    teacher_row = get_teacher_row(db, teacher)
    course = Course(
        teacher_id=teacher_row.user_id,
        title=body.title,
        subject=body.subject,
        description=body.description,
        exam_date=body.exam_date,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    _audit(db, teacher, "course.create", course.id, {"title": course.title})
    return _course_out(db, course)


@router.get("", response_model=list[CourseOut])
def list_courses(
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[CourseOut]:
    if user.role == "teacher":
        courses = list(
            db.scalars(
                select(Course)
                .where(Course.teacher_id == user.id)
                .order_by(Course.created_at.desc())
            )
        )
    else:
        courses = list(
            db.scalars(
                select(Course)
                .join(Enrollment)
                .where(Enrollment.student_id == user.id)
                .order_by(Course.created_at.desc())
            )
        )
    return [_course_out(db, c) for c in courses]


@router.get("/{course_id}", response_model=CourseOut)
def get_course(
    course_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> CourseOut:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if user.role == "teacher":
        if course.teacher_id != user.id:
            raise HTTPException(403, "Not your course")
    else:
        enrolled = db.scalars(
            select(Enrollment).where(
                Enrollment.course_id == course_id, Enrollment.student_id == user.id
            )
        ).first()
        if enrolled is None:
            raise HTTPException(403, "Not enrolled in this course")
    return _course_out(db, course)


@router.post("/{course_id}/enroll", response_model=CourseOut, status_code=201)
def enroll_student(
    course_id: str,
    body: EnrollRequest,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> CourseOut:
    assert_course_owner(db, course_id, teacher.id)
    student = db.get(Student, body.student_id)
    if student is None:
        raise HTTPException(404, "Student not found")
    existing = db.scalars(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.student_id == body.student_id
        )
    ).first()
    if existing is None:
        db.add(Enrollment(course_id=course_id, student_id=body.student_id))
        db.commit()
        _audit(db, teacher, "enrollment.create", course_id, {"student_id": body.student_id})
    return _course_out(db, db.get(Course, course_id))


# ---------------------------------------------------------------- documents


@router.post("/{course_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    course_id: str,
    file: Annotated[UploadFile, File()],
    teacher: TeacherDep = None,
    db: Annotated[Session, Depends(get_db)] = None,
) -> DocumentOut:
    assert_course_owner(db, course_id, teacher.id)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            400,
            f"Unsupported file type '{ext}'. Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}.",
        )
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(413, "File too large")
    if not content.strip():
        raise HTTPException(400, "Empty file")

    storage = settings.storage_path / "documents"
    storage.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid4().hex}{ext}"
    path = storage / stored_name
    path.write_bytes(content)

    doc = Document(
        course_id=course_id,
        filename=file.filename or stored_name,
        storage_path=str(path),
        file_type=ext.lstrip("."),
        size_bytes=len(content),
        status="uploaded",
        uploaded_by=teacher.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    _audit(db, teacher, "document.upload", doc.id, {"filename": doc.filename})
    log.info("document_uploaded", course_id=course_id, document_id=doc.id, filename=doc.filename)
    return _build_document_out(db, doc)


@router.get("/{course_id}/documents", response_model=list[DocumentOut])
def list_documents(
    course_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> list[DocumentOut]:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if user.role == "teacher" and course.teacher_id != user.id:
        raise HTTPException(403, "Not your course")
    docs = list(
        db.scalars(
            select(Document)
            .where(Document.course_id == course_id)
            .order_by(Document.created_at.desc())
        )
    )
    return [_build_document_out(db, d) for d in docs]


@router.get("/{course_id}/documents/{document_id}", response_model=DocumentOut)
def get_document_status(
    course_id: str,
    document_id: str,
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
) -> DocumentOut:
    doc = db.get(Document, document_id)
    if doc is None or doc.course_id != course_id:
        raise HTTPException(404, "Document not found")
    return _build_document_out(db, doc)


# ---------------------------------------------------------------- deletes


@router.delete("/{course_id}/documents/{document_id}")
def delete_document(
    course_id: str,
    document_id: str,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    assert_course_owner(db, course_id, teacher.id)
    doc = db.get(Document, document_id)
    if doc is None or doc.course_id != course_id:
        raise HTTPException(404, "Document not found")
    _unlink_file(doc.storage_path)
    db.execute(delete(Chapter).where(Chapter.document_id == document_id))
    db.delete(doc)
    db.commit()
    _audit(db, teacher, "document.delete", document_id, {"filename": doc.filename})
    log.info("document_deleted", course_id=course_id, document_id=document_id)
    return {"deleted": True, "course_id": course_id, "document_id": document_id}


@router.delete("/{course_id}/contents")
def clear_course_contents(
    course_id: str,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    _get_owned_course(db, course_id, teacher.id)
    removed = _purge_course_data(db, course_id)
    db.commit()
    _audit(db, teacher, "course.clear_contents", course_id, {"documents_removed": removed})
    log.info("course_contents_cleared", course_id=course_id, documents_removed=removed)
    return {"cleared": True, "course_id": course_id, "documents_removed": removed}


@router.delete("/{course_id}")
def delete_course(
    course_id: str,
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    course = _get_owned_course(db, course_id, teacher.id)
    _purge_course_data(db, course_id)
    db.delete(course)
    db.commit()
    _audit(db, teacher, "course.delete", course_id, {"title": course.title})
    log.info("course_deleted", course_id=course_id, title=course.title)
    return {"deleted": True, "course_id": course_id}


# ---------------------------------------------------------------- helpers


def _get_owned_course(db: Session, course_id: str, teacher_id: str) -> Course:
    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(404, "Course not found")
    if course.teacher_id != teacher_id:
        raise HTTPException(403, "Not your course")
    return course


def _unlink_file(storage_path: str | None) -> None:
    if not storage_path:
        return
    try:
        Path(storage_path).unlink(missing_ok=True)
    except OSError as exc:
        log.warning("document_file_unlink_failed", path=storage_path, error=str(exc))


def _purge_course_data(db: Session, course_id: str) -> int:
    """Delete every row tied to a course (documents + on-disk files, curriculum,
    lessons, quizzes, study plans, enrollments, progress). DB-level ON DELETE
    CASCADE clears the child rows (topics, objectives, attempts, answers, grades,
    chunks). The Course row itself is left untouched."""
    docs = list(db.scalars(select(Document).where(Document.course_id == course_id)))
    for doc in docs:
        _unlink_file(doc.storage_path)
    for model in (
        StudyPlan,
        Quiz,
        Question,
        Lesson,
        Chapter,
        Document,
        Enrollment,
        StudyHistory,
        Recommendation,
    ):
        db.execute(delete(model).where(model.course_id == course_id))
    db.execute(
        update(ConversationMemory)
        .where(ConversationMemory.course_id == course_id)
        .values(course_id=None)
    )
    db.execute(delete(ContentChunk).where(ContentChunk.course_id == course_id))
    return len(docs)


def _build_document_out(db: Session, doc: Document) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        course_id=doc.course_id,
        filename=doc.filename,
        file_type=doc.file_type,
        size_bytes=doc.size_bytes,
        page_count=doc.page_count,
        status=doc.status,
        error=doc.error,
        created_at=doc.created_at,
    )


def _course_out(db: Session, course: Course) -> CourseOut:
    n = db.scalar(select(func.count(Enrollment.id)).where(Enrollment.course_id == course.id)) or 0
    return CourseOut(
        id=course.id,
        teacher_id=course.teacher_id,
        title=course.title,
        subject=course.subject,
        description=course.description,
        exam_date=course.exam_date,
        status=course.status,
        created_at=course.created_at,
        student_count=n,
    )


def _audit(db: Session, user: User, action: str, resource_id: str | None, detail: dict) -> None:
    db.add(
        AuditLog(
            user_id=user.id,
            role=user.role,
            action=action,
            resource_type="course",
            resource_id=resource_id,
            detail=detail,
        )
    )
    db.commit()

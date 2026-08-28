from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...models import Student, User
from ...schemas.api import UserOut
from ..deps import TeacherDep

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/search", response_model=list[UserOut])
def search_users(
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
    q: str = Query("", max_length=255),
    role: str | None = Query(None, pattern="^(teacher|student)$"),
    limit: int = Query(20, ge=1, le=100),
) -> list[UserOut]:
    """Teacher-only user lookup by name or email (case-insensitive substring)."""
    query = select(User).order_by(User.full_name)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.where(or_(User.full_name.ilike(like), User.email.ilike(like)))
    if role:
        query = query.where(User.role == role)
    rows = list(db.scalars(query.limit(limit)))

    student_rows = (
        {
            s.user_id: s
            for s in db.scalars(
                select(Student).where(Student.user_id.in_([u.id for u in rows]))
            ).all()
        }
        if rows
        else {}
    )

    out = []
    for u in rows:
        student = student_rows.get(u.id)
        out.append(
            UserOut(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                role=u.role,
                daily_study_minutes=student.daily_study_minutes if student else None,
            )
        )
    return out

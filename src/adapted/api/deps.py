from __future__ import annotations

from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database.session import get_db
from ..models import Student, Teacher, User
from ..security.jwt import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        payload = decode_access_token(credentials.credentials)
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


def require_role(*roles: str):
    def _dep(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires role: {' or '.join(roles)}")
        return user

    return _dep


TeacherDep = Annotated[User, Depends(require_role("teacher"))]
StudentDep = Annotated[User, Depends(require_role("student"))]
AnyUserDep = Annotated[User, Depends(get_current_user)]


def get_teacher_row(db: Session, user: User) -> Teacher:
    teacher = db.get(Teacher, user.id)
    if teacher is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Teacher profile not found")
    return teacher


def get_student_row(db: Session, user: User) -> Student:
    student = db.get(Student, user.id)
    if student is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Student profile not found")
    return student


def assert_course_owner(db: Session, course_id: str, teacher_id: str) -> None:
    from ..models import Course

    course = db.get(Course, course_id)
    if course is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Course not found")
    if course.teacher_id != teacher_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your course")


def assert_student_enrolled(db: Session, course_id: str, student_id: str) -> None:
    from ..models import Enrollment

    enrolled = db.scalars(
        select(Enrollment).where(
            Enrollment.course_id == course_id, Enrollment.student_id == student_id
        )
    ).first()
    if enrolled is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not enrolled in this course")

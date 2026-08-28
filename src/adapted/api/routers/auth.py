from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...models import Student, Teacher, User
from ...schemas.api import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from ...security.jwt import create_access_token
from ...security.passwords import hash_password, verify_password
from ..deps import AnyUserDep

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    if body.role not in ("teacher", "student"):
        raise HTTPException(400, "role must be 'teacher' or 'student'")
    existing = db.scalars(select(User).where(User.email == body.email)).first()
    if existing:
        raise HTTPException(409, "Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    db.add(user)
    db.flush()
    if body.role == "teacher":
        db.add(Teacher(user_id=user.id))
    else:
        db.add(
            Student(
                user_id=user.id,
                daily_study_minutes=body.daily_study_minutes or 90,
            )
        )
    db.commit()
    token = create_access_token(user.id, user.role)

    student = db.scalars(select(Student).where(Student.user_id == user.id)).first()
    daily_minutes = student.daily_study_minutes if student else None
    return TokenResponse(
        access_token=token,
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            daily_study_minutes=daily_minutes,
        ),
    )


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    token = create_access_token(user.id, user.role)
    student = db.scalars(select(Student).where(Student.user_id == user.id)).first()
    daily_minutes = student.daily_study_minutes if student else None
    return TokenResponse(
        access_token=token,
        user=UserOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            daily_study_minutes=daily_minutes,
        ),
    )


@router.get("/me", response_model=UserOut)
def me(user: AnyUserDep) -> UserOut:
    return user

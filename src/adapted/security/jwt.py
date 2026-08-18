from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt

from ..config import settings


def create_access_token(user_id: str, role: str, minutes: int | None = None) -> str:
    expires = datetime.now(UTC) + timedelta(minutes=minutes or settings.access_token_expire_minutes)
    payload = {"sub": user_id, "role": role, "exp": expires}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])

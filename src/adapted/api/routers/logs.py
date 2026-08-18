from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...models import AuditLog
from ..deps import TeacherDep

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("/audit", response_model=list[dict])
def audit_logs(
    teacher: TeacherDep,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(200, le=1000),
) -> list[dict]:
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)))
    return [
        {
            "timestamp": r.timestamp,
            "user_id": r.user_id,
            "role": r.role,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "detail": r.detail,
            "task_id": r.task_id,
            "correlation_id": r.correlation_id,
        }
        for r in rows
    ]

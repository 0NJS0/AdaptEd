from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...logging.logger import get_logger
from ...models import AgentMessage, AgentTask
from ...schemas.api import AgentMessageOut, AgentTaskOut
from ..deps import AnyUserDep

log = get_logger("adapted.api.agent_ops")

router = APIRouter(prefix="/agent", tags=["observability"])


def reap_stale_tasks(db: Session) -> None:
    """Mark tasks stuck in ``started`` far beyond a realistic run as failed.

    Background runs are tied to the server process; if it dies mid-run (restart,
    crash), the task would otherwise show ``started`` forever. The free chat
    model can legitimately take 30+ minutes on large documents, so the budget is
    generous (60 min): real orphans from a dead server are reaped, but
    slow-but-valid runs are never touched. Genuine hangs are already bounded by
    the LLM per-request timeout + bounded retries inside the runtime.
    """
    budget = timedelta(minutes=60)
    cutoff = datetime.now(UTC) - budget
    stale = db.scalars(
        select(AgentTask).where(AgentTask.status == "started", AgentTask.started_at < cutoff)
    ).all()
    for task in stale:
        task.status = "failed"
        task.error = "request interrupted / exceeded time budget (server restarted?)"
        task.finished_at = datetime.now(UTC)
        log.warning("task_reaped_stale", task_id=task.task_id, intent=task.intent)
    if stale:
        db.commit()


@router.get("/tasks", response_model=list[AgentTaskOut])
def list_tasks(
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(50, le=200),
    workflow: str | None = None,
) -> list[AgentTaskOut]:
    reap_stale_tasks(db)
    q = select(AgentTask).order_by(AgentTask.started_at.desc()).limit(limit)
    if workflow:
        q = q.where(AgentTask.workflow == workflow)
    return [AgentTaskOut.model_validate(t) for t in db.scalars(q).all()]


@router.get("/tasks/{task_id}", response_model=AgentTaskOut)
def get_task(
    task_id: str, user: AnyUserDep, db: Annotated[Session, Depends(get_db)]
) -> AgentTaskOut:
    reap_stale_tasks(db)
    task = db.scalars(select(AgentTask).where(AgentTask.task_id == task_id)).first()
    if task is None:
        from fastapi import HTTPException

        raise HTTPException(404, "Task not found")
    return AgentTaskOut.model_validate(task)


@router.get("/messages", response_model=list[AgentMessageOut])
def list_messages(
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
    task_id: str | None = None,
    correlation_id: str | None = None,
    limit: int = Query(200, le=500),
) -> list[AgentMessageOut]:
    q = select(AgentMessage).order_by(AgentMessage.created_at.desc()).limit(limit)
    if task_id:
        q = q.where(AgentMessage.task_id == task_id)
    if correlation_id:
        q = q.where(AgentMessage.correlation_id == correlation_id)
    return [AgentMessageOut.model_validate(m) for m in db.scalars(q).all()]


@router.get("/runs", response_model=list[AgentTaskOut])
def agent_runs(
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(50),
) -> list[AgentTaskOut]:
    q = select(AgentTask).order_by(AgentTask.started_at.desc()).limit(limit)
    return [AgentTaskOut.model_validate(t) for t in db.scalars(q).all()]

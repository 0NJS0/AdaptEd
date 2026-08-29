from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database.session import get_db
from ...graph import topology
from ...logging.logger import get_logger
from ...models import AgentMessage, AgentTask
from ...schemas.api import (
    AgentMessageOut,
    AgentTaskOut,
    ExecutionGraphOut,
    TaskActionResult,
    UsageSummaryOut,
)
from ...tasks import runner
from ..deps import AnyUserDep, TeacherDep

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


# ------------------------------------------------------------ execution graph
@router.get("/graph", response_model=ExecutionGraphOut)
def execution_graph(
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
    task_id: str | None = None,
) -> ExecutionGraphOut:
    """The pipeline's execution graph. With ``task_id``, highlight the path taken."""
    visited: list[str] = []
    if task_id:
        msgs = db.scalars(
            select(AgentMessage)
            .where(AgentMessage.task_id == task_id)
            .order_by(AgentMessage.created_at)
        ).all()
        visited = topology.visited_from_messages(list(msgs))
    nodes, edges = topology.as_dicts()
    return ExecutionGraphOut(
        nodes=nodes, edges=edges, dot=topology.to_dot(visited), visited=visited
    )


# ------------------------------------------------------- token usage & cost
@router.get("/usage", response_model=UsageSummaryOut)
def usage_summary(
    user: AnyUserDep,
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(200, le=1000),
) -> UsageSummaryOut:
    tasks = db.scalars(
        select(AgentTask).order_by(AgentTask.started_at.desc()).limit(limit)
    ).all()
    from ...config import settings

    prompt = sum(t.prompt_tokens or 0 for t in tasks)
    completion = sum(t.completion_tokens or 0 for t in tasks)
    calls = sum(t.llm_calls or 0 for t in tasks)
    cost = round(sum(t.cost_usd or 0.0 for t in tasks), 6)
    by_intent: dict[str, dict] = {}
    for t in tasks:
        row = by_intent.setdefault(
            t.intent, {"intent": t.intent, "tasks": 0, "total_tokens": 0, "cost_usd": 0.0}
        )
        row["tasks"] += 1
        row["total_tokens"] += (t.prompt_tokens or 0) + (t.completion_tokens or 0)
        row["cost_usd"] = round(row["cost_usd"] + (t.cost_usd or 0.0), 6)
    return UsageSummaryOut(
        tasks=len(tasks),
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=prompt + completion,
        llm_calls=calls,
        cost_usd=cost,
        by_intent=sorted(by_intent.values(), key=lambda r: -r["total_tokens"]),
    )


# ----------------------------------------------- human-in-the-loop controls
def _get_task(db: Session, task_id: str) -> AgentTask:
    task = db.scalars(select(AgentTask).where(AgentTask.task_id == task_id)).first()
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


@router.post("/tasks/{task_id}/cancel", response_model=TaskActionResult)
def cancel_task(
    task_id: str, user: TeacherDep, db: Annotated[Session, Depends(get_db)]
) -> TaskActionResult:
    task = _get_task(db, task_id)
    task.control = "cancel"
    db.commit()
    return TaskActionResult(
        task_id=task_id, status=task.status, message="Cancellation requested (stops at next step)."
    )


@router.post("/tasks/{task_id}/pause", response_model=TaskActionResult)
def pause_task(
    task_id: str, user: TeacherDep, db: Annotated[Session, Depends(get_db)]
) -> TaskActionResult:
    task = _get_task(db, task_id)
    task.control = "pause"
    db.commit()
    return TaskActionResult(
        task_id=task_id, status=task.status, message="Pause requested (parks at next step)."
    )


@router.post("/tasks/{task_id}/approve", response_model=TaskActionResult)
def approve_task(
    task_id: str, user: TeacherDep, db: Annotated[Session, Depends(get_db)]
) -> TaskActionResult:
    ok = runner.approve_task(task_id)
    if not ok:
        raise HTTPException(409, "Task is not awaiting approval.")
    return TaskActionResult(task_id=task_id, status="started", message="Approved — now running.")


@router.post("/tasks/{task_id}/reject", response_model=TaskActionResult)
def reject_task(
    task_id: str, user: TeacherDep, db: Annotated[Session, Depends(get_db)]
) -> TaskActionResult:
    task = _get_task(db, task_id)
    if task.status != "awaiting_approval":
        raise HTTPException(409, "Task is not awaiting approval.")
    task.status = "cancelled"
    task.control = "cancel"
    db.commit()
    return TaskActionResult(task_id=task_id, status="cancelled", message="Rejected.")


@router.post("/tasks/{task_id}/retry", response_model=TaskActionResult)
def retry_task(
    task_id: str, user: TeacherDep, db: Annotated[Session, Depends(get_db)]
) -> TaskActionResult:
    ids = runner.retry_task(task_id)
    if ids is None:
        raise HTTPException(404, "Task not found")
    new_id, _ = ids
    return TaskActionResult(
        task_id=task_id, status="started", message="Re-running as a new task.", new_task_id=new_id
    )


@router.post("/tasks/{task_id}/resume", response_model=TaskActionResult)
def resume_task(
    task_id: str, user: TeacherDep, db: Annotated[Session, Depends(get_db)]
) -> TaskActionResult:
    """Resume a paused/failed task by re-running its workflow as a fresh task."""
    ids = runner.retry_task(task_id)
    if ids is None:
        raise HTTPException(404, "Task not found")
    new_id, _ = ids
    return TaskActionResult(
        task_id=task_id, status="started", message="Resumed (re-running).", new_task_id=new_id
    )

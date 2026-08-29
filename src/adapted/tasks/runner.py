from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from sqlalchemy import select

from ..agents.message import MessageBus
from ..agents.supervisor import Supervisor
from ..database.session import SessionLocal
from ..llm.registry import get_provider
from ..logging.logger import get_logger
from ..models import AgentTask

log = get_logger("adapted.tasks")

# Bounded worker pool for background agent runs. Each run gets its OWN DB
# session (SQLAlchemy sessions are not thread-safe) and is independent from
# the request's session, which closes when the HTTP response returns.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="adapted-agent")


def submit_pipeline(
    intent: str,
    payload: dict[str, Any],
    user_id: str | None,
    require_approval: bool = False,
) -> tuple[str, str]:
    """Persist an agent task and (unless it needs approval) run it in the background.

    Returns (task_id, correlation_id) immediately. With ``require_approval`` the
    task is parked in status ``awaiting_approval`` and only runs once a human
    calls :func:`approve_task` — the human-in-the-loop gate.
    """
    db = SessionLocal()
    try:
        task = Supervisor(db).start_task(intent, payload, user_id)
        if require_approval:
            task.status = "awaiting_approval"
        db.commit()
        task_id, correlation_id = task.task_id, task.correlation_id
    except Exception as exc:
        db.rollback()
        log.error("task_submit_failed", intent=intent, error=str(exc))
        raise
    finally:
        db.close()
    if not require_approval:
        _executor.submit(_run_in_thread, intent, payload, user_id, task_id, correlation_id)
    return task_id, correlation_id


def approve_task(task_id: str) -> bool:
    """Release an ``awaiting_approval`` task into execution. Returns False if not gated."""
    db = SessionLocal()
    try:
        task = db.scalars(select(AgentTask).where(AgentTask.task_id == task_id)).first()
        if task is None or task.status != "awaiting_approval":
            return False
        task.status = "started"
        task.control = "run"
        intent, payload, user_id = task.intent, dict(task.payload or {}), task.user_id
        cid = task.correlation_id
        db.commit()
    finally:
        db.close()
    _executor.submit(_run_in_thread, intent, payload, user_id, task_id, cid)
    return True


def retry_task(task_id: str) -> tuple[str, str] | None:
    """Re-run a task's intent/payload as a fresh task. Used for retry and resume.

    Resume re-runs the whole workflow (the pipeline is not mid-graph checkpointed),
    which is safe because agent writes are idempotent per savepoint.
    """
    db = SessionLocal()
    try:
        task = db.scalars(select(AgentTask).where(AgentTask.task_id == task_id)).first()
        if task is None:
            return None
        intent, payload, user_id = task.intent, dict(task.payload or {}), task.user_id
    finally:
        db.close()
    return submit_pipeline(intent, payload, user_id)


def _run_in_thread(
    intent: str,
    payload: dict[str, Any],
    user_id: str | None,
    task_id: str,
    correlation_id: str,
) -> None:
    db = SessionLocal()
    try:
        from ..graph.runtime import AgentRuntime

        runtime = AgentRuntime(db, get_provider(), MessageBus(db))
        # reuse the pre-created task (submit_pipeline) so the API-returned id is
        # the one that gets finished; runtime.run only starts a task when none
        # is given (synchronous callers keep the old behaviour)
        runtime.run(intent, payload, user_id, task_id, correlation_id)
    except Exception as exc:  # noqa: BLE001
        # runtime.run finishes the task itself on graph failure; this guards the
        # rarer crash-before-invoke case so the task never stays 'started' forever.
        log.error("background_run_failed", task_id=task_id, error=str(exc))
        try:
            _mark_failed(task_id, str(exc))
        except Exception as mark_err:  # noqa: BLE001
            log.error("background_task_mark_failed", task_id=task_id, error=str(mark_err))
    finally:
        db.close()


def _mark_failed(task_id: str, error: str) -> None:
    db = SessionLocal()
    try:
        task = db.scalars(select(AgentTask).where(AgentTask.task_id == task_id)).first()
        if task is not None and task.status == "started":
            Supervisor(db).finish_task(task_id, "failed", error=error)
            db.commit()
    finally:
        db.close()

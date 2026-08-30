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
from ..obe import runner as obe_runner

log = get_logger("adapted.tasks")

# Bounded worker pool for background agent runs. Each run gets its OWN DB
# session (SQLAlchemy sessions are not thread-safe) and is independent from
# the request's session, which closes when the HTTP response returns.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="adapted-agent")


def submit_pipeline(intent: str, payload: dict[str, Any], user_id: str | None) -> tuple[str, str]:
    """Persist a 'started' agent task and run it in the background.

    Returns (task_id, correlation_id) immediately; callers poll
    ``GET /agent/tasks/{task_id}`` for the outcome.
    """
    db = SessionLocal()
    try:
        task = Supervisor(db).start_task(intent, payload, user_id)
        db.commit()
        task_id, correlation_id = task.task_id, task.correlation_id
    except Exception as exc:
        db.rollback()
        log.error("task_submit_failed", intent=intent, error=str(exc))
        raise
    finally:
        db.close()
    _executor.submit(_run_in_thread, intent, payload, user_id, task_id, correlation_id)
    return task_id, correlation_id


def submit_obe(
    *, text: str, polish: bool, filename: str, user_id: str | None
) -> tuple[str, str]:
    """Persist a 'started' OBE analysis task and run it in the background.

    The OBE extract → validate → suggest → summarize chain is a single linear
    pipeline, not a graph, so it doesn't go through ``AgentRuntime`` / the
    supervisor graph. The task row is still persisted (intent
    ``"analyze_outline"`` -> workflow ``"obe_summary"``) so it shows up in
    ``GET /agent/tasks`` and the Operations page like every other agent run.
    """
    db = SessionLocal()
    try:
        task = Supervisor(db).start_task(
            "analyze_outline",
            {"filename": filename, "polish": bool(polish)},
            user_id,
        )
        db.commit()
        task_id, correlation_id = task.task_id, task.correlation_id
    except Exception as exc:
        db.rollback()
        log.error("obe_task_submit_failed", filename=filename, error=str(exc))
        raise
    finally:
        db.close()
    _executor.submit(
        _run_obe_in_thread, text, polish, filename, task_id, correlation_id
    )
    return task_id, correlation_id


def _run_obe_in_thread(
    text: str,
    polish: bool,
    filename: str,
    task_id: str,
    correlation_id: str,
) -> None:
    db = SessionLocal()
    try:
        result = obe_runner.analyze_text(text, polish=polish)
        Supervisor(db).finish_task(task_id, "success", result=result)
        db.commit()
        log.info(
            "obe_task_succeeded",
            task_id=task_id,
            filename=filename,
            errors=result.get("report", {}).get("error_count"),
        )
    except Exception as exc:  # noqa: BLE001
        log.error("obe_task_failed", task_id=task_id, error=str(exc))
        try:
            _mark_failed(task_id, f"OBE analysis failed: {exc}")
        except Exception as mark_err:  # noqa: BLE001
            log.error("obe_task_mark_failed", task_id=task_id, error=str(mark_err))
    finally:
        db.close()


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

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..logging.logger import get_logger
from ..models import AgentMessage as AgentMessageRow
from ..models import AgentTask
from .message import AgentMessage

log = get_logger("adapted.agents.supervisor")

# intent -> workflow + initial action
WORKFLOWS: dict[str, dict[str, str]] = {
    "analyze_curriculum": {"workflow": "curriculum", "first_action": "curriculum.analyze"},
    "create_plan": {"workflow": "plan_create", "first_action": "plan.create"},
    "adapt_plan": {"workflow": "plan_adapt", "first_action": "plan.modify"},
    "generate_lesson": {"workflow": "lesson", "first_action": "lesson.generate"},
    "generate_quiz": {"workflow": "quiz_generate", "first_action": "quiz.generate"},
    "quiz_submit": {"workflow": "quiz_submit", "first_action": "attempt.grade"},
    "generate_recommendation": {"workflow": "recommend", "first_action": "recommend.generate"},
    "generate_reassessment": {"workflow": "lesson", "first_action": "lesson.generate"},
}


class Supervisor:
    """Central orchestrator: classifies intents, routes to specialized agents,
    coordinates multi-agent workflows, validates outputs and records every hop."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def classify(self, payload: dict[str, Any]) -> str | None:
        intent = payload.get("intent")
        if intent in WORKFLOWS:
            return intent
        raise ValueError(f"Unknown intent '{intent}'. Valid intents: {', '.join(WORKFLOWS)}")

    def start_task(self, intent: str, payload: dict[str, Any], user_id: str | None) -> AgentTask:
        workflow = WORKFLOWS[intent]["workflow"]
        task = AgentTask(
            task_id=f"TASK-{uuid.uuid4().hex[:10].upper()}",
            correlation_id=f"CORR-{uuid.uuid4().hex[:10].upper()}",
            workflow=workflow,
            intent=intent,
            status="started",
            user_id=user_id,
            payload=payload,
        )
        self.db.add(task)
        self.db.flush()
        log.info(
            "supervisor_task_started",
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            intent=intent,
            workflow=workflow,
        )
        return task

    def initial_message(self, task: AgentTask) -> AgentMessage:
        first_action = WORKFLOWS[task.intent]["first_action"]
        receiver = self._receiver_for_action(first_action)
        return AgentMessage(
            task_id=task.task_id,
            correlation_id=task.correlation_id,
            sender="supervisor",
            receiver=receiver,
            action=first_action,
            payload={**task.payload},
        )

    @staticmethod
    def _receiver_for_action(action: str) -> str:
        mapping = {
            "curriculum.analyze": "curriculum_agent",
            "plan.create": "planner_agent",
            "plan.modify": "planner_agent",
            "lesson.generate": "lesson_agent",
            "quiz.generate": "quiz_agent",
            "attempt.grade": "grading_agent",
            "performance.analyze": "performance_agent",
            "recommend.generate": "recommendation_agent",
        }
        return mapping.get(action, "unknown")

    def finish_task(
        self,
        task_id: str,
        status: str,
        error: str | None = None,
        result: dict | None = None,
        duration_ms: int = 0,
    ) -> None:
        task = self.db.scalars(select(AgentTask).where(AgentTask.task_id == task_id)).first()
        if task is None:
            return
        task.status = status
        task.error = error
        task.result = result
        task.duration_ms = duration_ms
        from datetime import datetime

        task.finished_at = datetime.now(UTC)
        self.db.flush()

    def log_message(self, message: AgentMessage, status: str, error: str | None = None) -> None:
        row = self.db.scalars(
            select(AgentMessageRow).where(AgentMessageRow.message_id == message.message_id)
        ).first()
        if row:
            row.status = status
            row.error = error
            self.db.flush()

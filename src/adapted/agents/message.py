from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from ..logging.logger import get_logger
from ..models import AgentMessage as AgentMessageRow

log = get_logger("adapted.agents.message")

MESSAGE_ACTIONS = {
    "curriculum.analyze",
    "curriculum.retrieve",
    "plan.create",
    "plan.modify",
    "lesson.generate",
    "quiz.generate",
    "attempt.grade",
    "performance.analyze",
    "recommend.generate",
    "memory.update",
    "supervisor.route",
}


@dataclass
class AgentMessage:
    task_id: str
    correlation_id: str
    sender: str
    receiver: str
    action: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "sent"
    error: str | None = None
    duration_ms: int = 0
    message_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def as_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "task_id": self.task_id,
            "correlation_id": self.correlation_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "action": self.action,
            "payload": self.payload,
            "status": self.status,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "timestamp": datetime.now(UTC).isoformat(),
        }


class MessageBus:
    """Persisted agent-to-agent message bus. Every hop is recorded so agent
    communication stays observable and auditable."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def send(self, message: AgentMessage) -> AgentMessage:
        start = time.perf_counter()
        try:
            row = AgentMessageRow(
                message_id=message.message_id,
                task_id=message.task_id,
                correlation_id=message.correlation_id,
                sender=message.sender,
                receiver=message.receiver,
                action=message.action,
                payload=message.payload,
                status=message.status,
                error=message.error,
                duration_ms=message.duration_ms,
            )
            self.db.add(row)
            self.db.flush()
            log.info(
                "agent_message",
                message_id=message.message_id,
                task_id=message.task_id,
                correlation_id=message.correlation_id,
                sender=message.sender,
                receiver=message.receiver,
                action=message.action,
                status=message.status,
            )
            return message
        finally:
            message.duration_ms = int((time.perf_counter() - start) * 1000)

    def mark(
        self,
        message: AgentMessage,
        status: str,
        error: str | None = None,
    ) -> None:
        message.status = status
        message.error = error
        row = (
            self.db.query(AgentMessageRow)
            .filter(AgentMessageRow.message_id == message.message_id)
            .first()
        )
        if row:
            row.status = status
            row.error = error
            row.duration_ms = message.duration_ms
            self.db.flush()

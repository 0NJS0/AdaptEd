from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, ValidationError

from ..logging.logger import get_logger
from .message import AgentMessage, MessageBus

log = get_logger("adapted.agents.base")


class AgentResult(BaseModel):
    output: dict[str, Any] = {}
    error: str | None = None


class BaseAgent(ABC):
    """A specialized agent. Subclasses declare the message `actions` they
    handle and implement `process`, which returns a dict that validates
    against `output_schema`."""

    name: str = "base_agent"
    actions: ClassVar[set[str]] = set()
    output_schema: type[BaseModel] | None = None

    def __init__(self, bus: MessageBus | None = None) -> None:
        self.bus = bus

    @abstractmethod
    def process(self, message: AgentMessage) -> dict[str, Any]:
        """Execute the agent's work for `message` and return its output."""

    def validate_output(self, output: dict[str, Any]) -> dict[str, Any]:
        if self.output_schema is None:
            return output
        try:
            validated = self.output_schema.model_validate(output)
            result = validated.model_dump()
            # preserve extra context keys agents may attach (lesson_id, chunks_used, ...)
            for key, value in output.items():
                if key not in result:
                    result[key] = value
            return result
        except ValidationError as exc:
            log.error("agent_output_invalid", agent=self.name, errors=exc.errors())
            raise

    def output_is_empty(self, output: dict[str, Any]) -> bool:
        """True when the agent produced schema-valid but vacuum output (e.g. an
        LLM returning `{"chapters": []}`). Content-producing agents override
        this so the runtime can retry rather than silently "succeed" empty."""
        return False

    def handle(self, message: AgentMessage) -> AgentResult:
        start = time.perf_counter()
        try:
            output = self.process(message)
            output = self.validate_output(output)
            if self.bus:
                self.bus.mark(message, "success")
            log.info(
                "agent_completed",
                agent=self.name,
                task_id=message.task_id,
                correlation_id=message.correlation_id,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )
            return AgentResult(output=output)
        except Exception as exc:  # noqa: BLE001
            log.error("agent_failed", agent=self.name, task_id=message.task_id, error=str(exc))
            if self.bus:
                self.bus.mark(message, "failed", error=str(exc))
            return AgentResult(error=str(exc))

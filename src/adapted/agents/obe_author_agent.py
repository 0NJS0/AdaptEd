"""OBE Authoring Agent — generates and improves Course Outcomes.

The second agent in the OBE domain. Where ``obe_agent`` *analyzes and validates*
an existing outline, this agent *authors*: it drafts new OBE-compliant Course
Outcomes for a course/topic set, and rewrites a single CO the validator flagged
so its verb, Bloom level and PO/K-P-A are consistent with the OBE Manual.

Non-destructive and offline-capable (deterministic templates); no database needed.

Actions
-------
- ``obe.author``   -> generate a set of compliant Course Outcomes
- ``obe.improve``  -> rewrite one Course Outcome to fix its Bloom/PO alignment
"""

from __future__ import annotations

from typing import Any, ClassVar

from ..logging.logger import get_logger
from ..obe import authoring
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.obe_author")


class OBEAuthorAgent(BaseAgent):
    name = "obe_author_agent"
    actions: ClassVar[set[str]] = {"obe.author", "obe.improve"}
    output_schema = None  # output shape varies per action; validated internally

    def __init__(self, db=None, provider=None, bus=None) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        action = message.action
        payload = message.payload
        if action == "obe.author":
            return self._author(payload)
        if action == "obe.improve":
            return self._improve(payload)
        raise ValueError(f"OBEAuthorAgent cannot handle action '{action}'")

    def _author(self, payload: dict[str, Any]) -> dict[str, Any]:
        cos = authoring.author_cos(
            course_title=str(payload.get("course_title", "")),
            subject=str(payload.get("subject", "")),
            topics=payload.get("topics") or [],
            count=int(payload.get("count", 4) or 4),
            po_hint=payload.get("po_hint"),
        )
        return {"cos": [c.model_dump() for c in cos]}

    def _improve(self, payload: dict[str, Any]) -> dict[str, Any]:
        description = str(payload.get("description", "")).strip()
        if not description:
            raise ValueError("obe.improve needs a CO 'description' to rewrite.")
        improved = authoring.improve_co(
            description,
            target_level=payload.get("target_level"),
            target_po=payload.get("target_po"),
            co_id=str(payload.get("co_id") or "CO1"),
        )
        return {"improved": improved.model_dump()}

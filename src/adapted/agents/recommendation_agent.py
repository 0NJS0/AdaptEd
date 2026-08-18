from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from ..logging.logger import get_logger
from ..models import Recommendation
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.recommendation")


class RecommendationOut(BaseModel):
    action: str
    title: str
    reasons: list[str] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    confidence: float = 0.5
    needs_teacher_review: bool = False


class RecommendationOutput(BaseModel):
    student_id: str
    course_id: str
    recommendation: RecommendationOut
    message: str = ""


class RecommendationAgent(BaseAgent):
    name = "recommendation_agent"
    actions: ClassVar[set[str]] = {"recommend.generate"}
    output_schema = RecommendationOutput

    def __init__(self, db, provider, bus) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        student_id = payload["student_id"]
        course_id = payload["course_id"]
        weak = payload.get("weak_topics", []) or []
        strong = payload.get("strong_topics", []) or []
        misconceptions = payload.get("misconceptions", []) or []

        rec = self._decide(weak, strong, misconceptions)

        if self.provider.is_mock:
            narrative = self._mock_narrative(weak, strong, rec.action)
        else:
            narrative = self._llm_narrative(weak, strong, rec)

        recommendation_row = Recommendation(
            student_id=student_id,
            course_id=course_id,
            action=rec.action,
            topic_id=rec.payload.get("topic_id"),
            title=rec.title,
            reasons=rec.reasons,
            payload=rec.payload,
            confidence=rec.confidence,
            needs_teacher_review=rec.needs_teacher_review,
        )
        self.db.add(recommendation_row)
        self.db.flush()

        return {
            "student_id": student_id,
            "course_id": course_id,
            "recommendation": rec.model_dump(),
            "message": narrative,
        }

    def _decide(
        self, weak: list[dict], strong: list[dict], misconceptions: list[dict]
    ) -> RecommendationOut:
        weak_titles = [w.get("topic_title", "") for w in weak]
        primary_topic_id = weak[0].get("topic_id") if weak else None

        if not weak:
            return RecommendationOut(
                action="advance",
                title="Continue to the next topic",
                reasons=["No weak topics detected", "Current mastery is sufficient"],
                payload={},
                confidence=0.8,
            )

        if misconceptions and primary_topic_id:
            return RecommendationOut(
                action="review_topic",
                title=f"Review {weak_titles[0]}",
                reasons=[
                    f"Mastery of {weak_titles[0]} is below target",
                    "Recurring mistakes suggest a persistent misunderstanding",
                    "Five targeted exercises recommended before continuing",
                ],
                payload={
                    "topic_id": primary_topic_id,
                    "exercises": 5,
                    "practice_type": "targeted",
                },
                confidence=0.85,
            )

        return RecommendationOut(
            action="review_topic",
            title=f"Review {weak_titles[0]}",
            reasons=[
                f"Mastery of {weak_titles[0]} is below target",
                "Prerequisite review is recommended",
            ],
            payload={"topic_id": primary_topic_id, "exercises": 5},
            confidence=0.7,
        )

    def _mock_narrative(self, weak: list, strong: list, action: str) -> str:
        from ..llm.mock import _mock_recommendation

        return _mock_recommendation(
            {
                "weak_topics": [w.get("topic_title", "") for w in weak],
                "strong_topics": [s.get("topic_title", "") for s in strong],
                "action": action,
            }
        )["message"]

    def _llm_narrative(self, weak: list, strong: list, rec: RecommendationOut) -> str:
        from ..llm.base import LLMRequest

        schema = {
            "type": "object",
            "properties": {"message": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["message", "summary"],
        }
        prompt = (
            "Write a short, encouraging recommendation for a student. "
            f"Weak topics: {[w.get('topic_title') for w in weak]}. "
            f"Strong topics: {[s.get('topic_title') for s in strong]}. "
            f"Decided action: {rec.title}. Return JSON with 'message' and 'summary'."
        )
        request = LLMRequest(
            task="recommend_narrative",
            prompt=prompt,
            schema=schema,
            meta={
                "weak_topics": [w.get("topic_title", "") for w in weak],
                "strong_topics": [s.get("topic_title", "") for s in strong],
                "action": rec.action,
            },
        )
        try:
            result = self.provider.generate(request)
            return str(result.get("message", rec.title))
        except Exception:  # noqa: BLE001
            return rec.title

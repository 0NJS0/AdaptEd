from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, Field
from sqlalchemy import select

from ..logging.logger import get_logger
from ..models import StudentMastery, StudyPlan, StudyPlanItem, Topic
from ..services import mastery as mastery_svc
from ..services.scheduler import (
    PlanItem,
    PlanTopic,
    adapt_plan,
    build_plan,
    validate_plan,
)
from .base import BaseAgent
from .message import AgentMessage

log = get_logger("adapted.agents.planner")


class PlanItemOut(BaseModel):
    topic_id: str
    title: str
    day_index: int
    sequence: int
    estimated_minutes: int
    goal: str
    reason: str = "scheduled"
    status: str = "pending"


class PlannerOutput(BaseModel):
    plan_id: str
    version: int
    valid: bool
    validation_errors: list[str] = Field(default_factory=list)
    items: list[PlanItemOut] = Field(default_factory=list)


class StudyPlannerAgent(BaseAgent):
    name = "planner_agent"
    actions: ClassVar[set[str]] = {"plan.create", "plan.modify"}
    output_schema = PlannerOutput

    def __init__(self, db, provider, bus) -> None:
        super().__init__(bus)
        self.db = db
        self.provider = provider

    def process(self, message: AgentMessage) -> dict[str, Any]:
        payload = message.payload
        student_id = payload["student_id"]
        course_id = payload["course_id"]
        exam_date = payload.get("exam_date")
        if exam_date and not isinstance(exam_date, date):
            exam_date = date.fromisoformat(str(exam_date))
        daily_minutes = int(payload.get("daily_minutes") or 90)
        mode = payload.get("mode", "create")

        topics = self._load_topics(course_id, student_id)
        id_by_title = {t.title: t.topic_id for t in topics}
        prereq_titles_by_id = {
            t.id: [
                (prereq.prereq_topic.title if prereq.prereq_topic else "")
                for prereq in t.prerequisites
                if prereq.prereq_topic is not None
            ]
            for t in self.db.scalars(select(Topic).where(Topic.course_id == course_id))
        }

        if mode == "modify":
            existing = self._latest_plan(student_id, course_id)
            if existing is None:
                # fall back to building a fresh plan if none exists yet
                new_items = build_plan(topics, exam_date=exam_date, daily_minutes=daily_minutes)
            else:
                items = [
                    PlanItem(
                        topic_id=i.topic_id,
                        title=(i.topic.title if i.topic else i.topic_id),
                        day_index=i.day_index,
                        sequence=i.sequence,
                        estimated_minutes=i.estimated_minutes,
                        goal=i.goal,
                        reason=i.reason,
                        status=i.status,
                    )
                    for i in existing.items
                ]
                weak_ids = payload.get("weak_topic_ids", [])
                new_items = adapt_plan(items, weak_topic_ids=weak_ids, daily_minutes=daily_minutes)
        else:
            new_items = build_plan(
                topics,
                exam_date=exam_date,
                daily_minutes=daily_minutes,
            )

        resolved_prereq_map = {
            topic_id: [id_by_title[p] for p in prereq_titles if p in id_by_title]
            for topic_id, prereq_titles in prereq_titles_by_id.items()
        }
        validation = validate_plan(
            new_items,
            exam_date=exam_date,
            daily_minutes=daily_minutes,
            prerequisite_map=resolved_prereq_map,
        )

        # If the naive plan is infeasible, relax: drop revision filler and pack topics.
        if not validation.valid and mode == "create":
            log.info("planner_relaxation", errors=validation.errors)
            packed = self._pack_fast(new_items, daily_minutes, exam_date)
            validation = validate_plan(packed, exam_date=exam_date, daily_minutes=daily_minutes)
            new_items = packed if validation.valid else new_items

        if not validation.valid:
            raise ValueError("Study plan is infeasible: " + "; ".join(validation.errors))

        plan, _ = self._persist(student_id, course_id, exam_date, daily_minutes, new_items, mode)

        return {
            "plan_id": plan.id,
            "version": plan.version,
            "valid": validation.valid,
            "validation_errors": validation.errors,
            "items": [i.to_dict() for i in new_items],
        }

    def _load_topics(self, course_id: str, student_id: str) -> list[PlanTopic]:
        topics = list(
            self.db.scalars(
                select(Topic).where(Topic.course_id == course_id).order_by(Topic.order_index)
            )
        )
        mastery_rows = {
            m.topic_id: m
            for m in self.db.scalars(
                select(StudentMastery).where(StudentMastery.student_id == student_id)
            )
        }
        out = []
        for t in topics:
            m = mastery_rows.get(t.id)
            mastered = m is not None and m.mastery >= mastery_svc.MASTERED_THRESHOLD
            out.append(
                PlanTopic(
                    topic_id=t.id,
                    title=t.title,
                    difficulty=t.difficulty,
                    prerequisite_ids=[p.prereq_topic_id for p in t.prerequisites],
                    mastered=mastered,
                )
            )
        return out

    def _latest_plan(self, student_id: str, course_id: str) -> StudyPlan | None:
        return self.db.scalars(
            select(StudyPlan)
            .where(
                StudyPlan.student_id == student_id,
                StudyPlan.course_id == course_id,
                StudyPlan.status == "active",
            )
            .order_by(StudyPlan.version.desc())
            .limit(1)
        ).first()

    def _pack_fast(
        self, items: list[PlanItem], daily_minutes: int, exam_date: date | None
    ) -> list[PlanItem]:
        """Re-pack items to fit within remaining days, up to 3 topics per day."""
        remaining_days = (
            max((exam_date - datetime.now(UTC).date()).days - 1, 1) if exam_date else len(items)
        )
        ordered = sorted(items, key=lambda i: (i.day_index, i.sequence))
        packed: list[PlanItem] = []
        day = 0
        used = 0
        seq = 0
        for item in ordered:
            if item.reason == "revision":
                continue
            if used + item.estimated_minutes > daily_minutes and day < remaining_days - 1:
                day += 1
                used = 0
            packed.append(
                PlanItem(
                    topic_id=item.topic_id,
                    title=item.title,
                    day_index=day,
                    sequence=seq,
                    estimated_minutes=min(item.estimated_minutes, daily_minutes),
                    goal=item.goal,
                    reason=item.reason,
                )
            )
            seq += 1
            used += item.estimated_minutes
        return packed

    def _persist(
        self,
        student_id: str,
        course_id: str,
        exam_date: date | None,
        daily_minutes: int,
        items: list[PlanItem],
        mode: str,
    ) -> tuple[StudyPlan, bool]:
        plan = self._latest_plan(student_id, course_id)
        if plan is None:
            plan = StudyPlan(
                student_id=student_id,
                course_id=course_id,
                exam_date=exam_date,
                daily_minutes=daily_minutes,
                version=1,
            )
            self.db.add(plan)
            self.db.flush()
            created = True
        else:
            plan.version += 1
            plan.exam_date = exam_date
            plan.daily_minutes = daily_minutes
            for old in list(plan.items):
                self.db.delete(old)
            self.db.flush()
            created = False

        for item in items:
            self.db.add(
                StudyPlanItem(
                    study_plan_id=plan.id,
                    topic_id=item.topic_id,
                    day_index=item.day_index,
                    sequence=item.sequence,
                    estimated_minutes=item.estimated_minutes,
                    goal=item.goal,
                    reason=item.reason,
                    status=item.status,
                )
            )
        self.db.flush()
        return plan, created

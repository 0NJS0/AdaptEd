from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime


@dataclass
class PlanTopic:
    topic_id: str
    title: str
    difficulty: float = 0.5
    prerequisite_ids: list[str] = field(default_factory=list)
    mastered: bool = False


@dataclass
class PlanItem:
    topic_id: str
    title: str
    day_index: int
    sequence: int
    estimated_minutes: int
    goal: str
    reason: str = "scheduled"
    status: str = "pending"

    def to_dict(self) -> dict:
        return {
            "topic_id": self.topic_id,
            "title": self.title,
            "day_index": self.day_index,
            "sequence": self.sequence,
            "estimated_minutes": self.estimated_minutes,
            "goal": self.goal,
            "reason": self.reason,
            "status": self.status,
        }


BASE_MINUTES = 40
DAYS_BUFFER = 1  # reserve buffer day(s) before the exam


def _topological_order(topics: list[PlanTopic]) -> list[PlanTopic]:
    """Order topics so prerequisites come first; tie-break by difficulty then title."""
    ids = {t.topic_id for t in topics}
    ordered: list[PlanTopic] = []
    placed: set[str] = set()
    remaining = list(topics)

    def can_place(t: PlanTopic) -> bool:
        return all(p in placed or p not in ids for p in t.prerequisite_ids)

    while remaining:
        ready = [t for t in remaining if can_place(t)]
        if not ready:
            # cycle or dangling prereq -> place by stability (difficulty) to avoid deadlock
            ready = [min(remaining, key=lambda x: (x.difficulty, x.title))]
        ready.sort(key=lambda t: (t.difficulty, t.title))
        for t in ready:
            ordered.append(t)
            placed.add(t.topic_id)
            remaining.remove(t)
    return ordered


def build_plan(
    topics: list[PlanTopic],
    *,
    exam_date: date | None,
    daily_minutes: int = 90,
    today: date | None = None,
) -> list[PlanItem]:
    """Create an initial study plan.

    Topics are scheduled topologically (prerequisites first). When there are
    more study-days than topics, only one topic per day is scheduled and later
    days get revision/review. When there are fewer days, multiple topics are
    packed into each day up to the daily minute budget.
    """
    today = today or datetime.now(UTC).date()
    active = [t for t in topics if not t.mastered]
    if not active:
        active = topics

    ordered = _topological_order(active)

    days_available = max((exam_date - today).days - DAYS_BUFFER, 1) if exam_date else len(ordered)

    items: list[PlanItem] = []
    seq = 0
    day = 0
    used_today = 0

    def place(t: PlanTopic, reason: str = "scheduled") -> None:
        nonlocal seq, day, used_today
        minutes = min(BASE_MINUTES + int(t.difficulty * 30), daily_minutes)
        items.append(
            PlanItem(
                topic_id=t.topic_id,
                title=t.title,
                day_index=day,
                sequence=seq,
                estimated_minutes=minutes,
                goal=f"Master {t.title}",
                reason=reason,
            )
        )
        seq += 1
        used_today += minutes

    for t in ordered:
        if (
            used_today > 0
            and (used_today + BASE_MINUTES > daily_minutes or day >= days_available - 1)
            and day < days_available - 1
        ):
            day += 1
            used_today = 0
        place(t)

    # Fill remaining days before the exam with revision
    while day < days_available - 1:
        day += 1
        used_today = 0
        if items:
            last = items[-1]
            items.append(
                PlanItem(
                    topic_id=last.topic_id,
                    title=f"{last.title} - revision",
                    day_index=day,
                    sequence=seq,
                    estimated_minutes=min(daily_minutes, 30),
                    goal=f"Revise {last.title}",
                    reason="revision",
                )
            )
            seq += 1
    return items


@dataclass
class PlanValidation:
    valid: bool
    errors: list[str]
    total_minutes: int
    days_used: int


def validate_plan(
    items: list[PlanItem],
    *,
    exam_date: date | None,
    daily_minutes: int,
    today: date | None = None,
    prerequisite_map: dict[str, list[str]] | None = None,
) -> PlanValidation:
    """Validate schedule feasibility: deadline compliance, daily capacity,
    and prerequisite ordering."""
    today = today or datetime.now(UTC).date()
    errors: list[str] = []
    prereq_map = prerequisite_map or {}

    if exam_date:
        days_available = max((exam_date - today).days - DAYS_BUFFER, 0)
        if not items:
            errors.append("Plan is empty - no topics were scheduled.")
        else:
            max_day = max(i.day_index for i in items)
            if max_day >= days_available:
                errors.append(
                    f"Plan exceeds available study days ({max_day + 1} days needed, "
                    f"{days_available} available before exam {exam_date})."
                )

    by_topic: dict[str, list[PlanItem]] = {}
    for item in items:
        by_topic.setdefault(item.topic_id, []).append(item)
        if item.estimated_minutes <= 0:
            errors.append(f"Item for {item.title} has non-positive duration.")
        if item.estimated_minutes > daily_minutes:
            errors.append(
                f"Item for {item.title} needs {item.estimated_minutes} min but daily "
                f"budget is {daily_minutes} min."
            )

    placed_days: dict[str, int] = {}
    for item in sorted(items, key=lambda i: (i.day_index, i.sequence)):
        for prereq in prereq_map.get(item.topic_id, []):
            if prereq in placed_days and placed_days[prereq] > item.day_index:
                errors.append(
                    f"Prerequisite violation: {item.title} is scheduled before its "
                    f"prerequisite (day {item.day_index} vs {placed_days[prereq]})."
                )
        placed_days[item.topic_id] = item.day_index

    total = sum(i.estimated_minutes for i in items)
    days_used = max((i.day_index for i in items), default=-1) + 1
    return PlanValidation(valid=not errors, errors=errors, total_minutes=total, days_used=days_used)


def adapt_plan(
    items: list[PlanItem],
    *,
    weak_topic_ids: list[str],
    daily_minutes: int,
    day_offset: int = 0,
) -> list[PlanItem]:
    """Revise the plan after a weak performance. Inserts review/practice/
    reassessment items for weak topics immediately, then shifts the rest."""
    if not weak_topic_ids:
        return items

    weak_set = set(weak_topic_ids)

    new_items: list[PlanItem] = []
    seq = 0
    for item in items:
        if item.topic_id in weak_set and item.reason not in ("review", "practice", "reassess"):
            # keep original item but schedule remedial loop right after it
            new_items.append(item)
            seq += 1
            insert_day = item.day_index
            for label, goal, minutes in [
                ("review", "Review the weak topic with a fresh explanation and examples.", 30),
                ("practice", "Complete five targeted practice exercises.", 35),
                ("reassess", "Retake a short reassessment quiz.", 20),
            ]:
                new_items.append(
                    PlanItem(
                        topic_id=item.topic_id,
                        title=f"{item.title} - {label}",
                        day_index=insert_day + 1,
                        sequence=seq,
                        estimated_minutes=minutes,
                        goal=goal,
                        reason=label,
                    )
                )
                seq += 1
        else:
            new_items.append(item)
            seq += 1

    # re-normalise day indexes so no item violates daily budget ordering
    _renormalise(new_items)
    return new_items


def _renormalise(items: list[PlanItem]) -> None:
    items.sort(key=lambda i: (i.day_index, i.sequence))
    current_day = 0
    used = 0
    for item in items:
        if used + item.estimated_minutes > 120:  # soft ceiling to keep order clean
            current_day += 1
            used = 0
        item.day_index = current_day
        used += item.estimated_minutes

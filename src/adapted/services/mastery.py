from __future__ import annotations

from dataclasses import dataclass, field

# Exponential moving average for mastery updates. Recent performance weighs more.
ALPHA = 0.4

WEAK_THRESHOLD = 50.0
DEVELOPING_THRESHOLD = 65.0
PROFICIENT_THRESHOLD = 80.0
MASTERED_THRESHOLD = 90.0


@dataclass
class MasteryRecord:
    topic_id: str
    topic_title: str
    mastery: float = 0.0
    attempts: int = 0
    trend: float = 0.0
    status: str = "untested"
    history: list[float] = field(default_factory=list)


def status_for(mastery: float) -> str:
    if mastery >= MASTERED_THRESHOLD:
        return "mastered"
    if mastery >= PROFICIENT_THRESHOLD:
        return "proficient"
    if mastery >= DEVELOPING_THRESHOLD:
        return "developing"
    if mastery >= WEAK_THRESHOLD:
        return "weak"
    return "weak"


def update_mastery(current: float, attempts: int, latest_score_percent: float) -> float:
    if attempts <= 1:
        return float(latest_score_percent)
    return round(ALPHA * latest_score_percent + (1 - ALPHA) * current, 2)


def compute_trend(history: list[float], window: int = 3) -> float:
    if len(history) < 2:
        return 0.0
    recent = history[-window:]
    delta = recent[-1] - recent[0]
    return round(delta / max(len(recent) - 1, 1), 2)


def classify(mastery: float) -> str:
    return status_for(mastery)


def build_record(
    topic_id: str,
    topic_title: str,
    mastery: float,
    attempts: int,
    history: list[float],
) -> MasteryRecord:
    return MasteryRecord(
        topic_id=topic_id,
        topic_title=topic_title,
        mastery=round(float(mastery), 2),
        attempts=attempts,
        trend=compute_trend(history),
        status=status_for(mastery),
        history=history,
    )

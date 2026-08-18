from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from .mastery import MasteryRecord


def weak_and_strong(records: list[MasteryRecord]) -> tuple[list[dict], list[dict]]:
    tested = [r for r in records if r.status != "untested"]
    weak = sorted(
        (r for r in tested if r.mastery < 60.0),
        key=lambda r: r.mastery,
    )
    strong = sorted(
        (r for r in tested if r.mastery >= 75.0),
        key=lambda r: r.mastery,
        reverse=True,
    )
    return (
        [
            {"topic_id": r.topic_id, "topic_title": r.topic_title, "mastery": r.mastery}
            for r in weak
        ],
        [
            {"topic_id": r.topic_id, "topic_title": r.topic_title, "mastery": r.mastery}
            for r in strong
        ],
    )


def detect_misconceptions(
    answers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Detect repeated-mistake patterns: the same wrong choice selected more
    than once, or the same topic answered incorrectly across attempts."""
    wrong_choice_counts: Counter[tuple[str, str]] = Counter()
    wrong_topic_counts: Counter[str] = Counter()
    topic_titles: dict[str, str] = {}

    for a in answers:
        q = a.get("question", {}) or {}
        topic_id = q.get("topic_id")
        title = q.get("topic_title") or topic_id
        if topic_id:
            topic_titles[topic_id] = title
        is_correct = a.get("is_correct")
        if is_correct is False or (is_correct is None and (a.get("ai_score") or 0) < 0.5):
            wrong_topic_counts[topic_id or "unknown"] += 1
            response = a.get("response", {})
            if isinstance(response, dict) and response.get("value"):
                wrong_choice_counts[(topic_id or "unknown", str(response["value"]))] += 1

    findings: list[dict[str, Any]] = []
    for (topic_id, choice), count in wrong_choice_counts.items():
        if count >= 2:
            findings.append(
                {
                    "topic_id": topic_id,
                    "topic_title": topic_titles.get(topic_id, topic_id),
                    "label": f"Consistent wrong choice: {choice}",
                    "description": (
                        f"The student chose '{choice}' {count} times. This suggests a "
                        "persistent misunderstanding rather than a one-off error."
                    ),
                    "evidence": {"count": count, "choice": choice},
                }
            )
    for topic_id, count in wrong_topic_counts.items():
        if count >= 3:
            findings.append(
                {
                    "topic_id": topic_id,
                    "topic_title": topic_titles.get(topic_id, topic_id),
                    "label": "Recurring errors in topic",
                    "description": (
                        f"{count} incorrect answers in this topic across attempts. "
                        "Prerequisite review is recommended."
                    ),
                    "evidence": {"count": count},
                }
            )
    return findings


def class_topic_summary(
    mastery_by_student: dict[str, list[MasteryRecord]],
) -> list[dict[str, Any]]:
    """Aggregate topic mastery across students for the teacher dashboard."""
    topic_records: dict[str, dict[str, Any]] = defaultdict(lambda: {"mastery": [], "title": ""})
    for records in mastery_by_student.values():
        for r in records:
            rec = topic_records[r.topic_id]
            rec["title"] = r.topic_title
            rec["mastery"].append(r.mastery)
    summary = []
    for topic_id, rec in topic_records.items():
        if not rec["mastery"]:
            continue
        avg = sum(rec["mastery"]) / len(rec["mastery"])
        summary.append(
            {
                "topic_id": topic_id,
                "topic_title": rec["title"],
                "avg_mastery": round(avg, 2),
                "n_students": len(rec["mastery"]),
            }
        )
    return sorted(summary, key=lambda s: s["avg_mastery"])

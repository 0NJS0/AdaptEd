from __future__ import annotations

import hashlib
import re
from typing import Any


def question_hash(course_id: str, prompt: str) -> str:
    norm = re.sub(r"\s+", " ", prompt.strip()).lower()
    return hashlib.sha256(f"{course_id}:{norm}".encode()).hexdigest()


def is_duplicate(existing_hashes: set[str], course_id: str, prompt: str) -> bool:
    return question_hash(course_id, prompt) in existing_hashes


def grade_objective(question: dict[str, Any], response: dict[str, Any]) -> bool:
    """Grade MCQ / true-false / numerical answers deterministically."""
    qtype = question.get("question_type", "")
    correct = question.get("correct_answer", {})
    expected = str(correct.get("value", "")).strip().lower()
    given = str(response.get("value", "")).strip().lower()

    if qtype in ("mcq", "true_false"):
        return given == expected

    if qtype == "numerical":
        return _numeric_equal(given, expected)

    return False


def _numeric_equal(a: str, b: str) -> bool:
    try:
        return abs(float(a) - float(b)) < 1e-6
    except (ValueError, TypeError):
        return a == b


def compute_attempt_score(graded: list[tuple[bool, float]]) -> tuple[float, float]:
    score = sum(points for correct, points in graded if correct)
    max_score = sum(points for _, points in graded)
    return round(score, 2), round(max_score, 2)


def rubric_default(max_score: float) -> dict[str, Any]:
    return {
        "criteria": [
            {"label": "Correctness", "weight": 0.6, "max": max_score * 0.6},
            {"label": "Explanation", "weight": 0.4, "max": max_score * 0.4},
        ]
    }

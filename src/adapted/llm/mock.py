from __future__ import annotations

import hashlib
import random
import re
from collections.abc import Callable
from typing import Any, ClassVar, Literal

import numpy as np

from ..config import settings
from .base import LLMProvider, LLMRequest

MATH_CURRICULUM = {
    "algebra": [
        {
            "title": "Algebra",
            "description": "Working with symbols, variables and expressions.",
            "objectives": [
                "Simplify algebraic expressions",
                "Solve linear equations",
                "Factorise quadratic and higher-degree expressions",
            ],
            "topics": [
                {"title": "Linear Equations", "difficulty": 0.3},
                {"title": "Polynomials", "difficulty": 0.5},
                {"title": "Factorization", "difficulty": 0.6},
            ],
        },
        {
            "title": "Functions",
            "description": "Relations, graphs and function notation.",
            "objectives": [
                "Understand function notation f(x)",
                "Interpret graphs of functions",
                "Determine domain and range",
            ],
            "topics": [
                {"title": "Linear Functions", "difficulty": 0.4},
                {"title": "Quadratic Functions", "difficulty": 0.6},
                {"title": "Graph Interpretation", "difficulty": 0.5},
            ],
        },
        {
            "title": "Quadratic Equations",
            "description": "Solving and applying quadratic equations.",
            "objectives": [
                "Solve quadratics by factorization",
                "Use the quadratic formula",
                "Analyse the discriminant",
            ],
            "topics": [
                {"title": "Solving Quadratics", "difficulty": 0.6},
                {"title": "The Discriminant", "difficulty": 0.7},
                {"title": "Applications of Quadratics", "difficulty": 0.7},
            ],
        },
    ],
    "geometry": [
        {
            "title": "Geometry",
            "description": "Shapes, angles and spatial reasoning.",
            "objectives": ["Identify angle relationships", "Compute area and perimeter"],
            "topics": [
                {"title": "Angles and Lines", "difficulty": 0.3},
                {"title": "Triangles", "difficulty": 0.5},
                {"title": "Circles", "difficulty": 0.6},
            ],
        }
    ],
    "probability": [
        {
            "title": "Probability",
            "description": "Chance, outcomes and data interpretation.",
            "objectives": ["Compute basic probabilities", "Read and interpret data"],
            "topics": [
                {"title": "Basic Probability", "difficulty": 0.4},
                {"title": "Statistical Interpretation", "difficulty": 0.6},
            ],
        }
    ],
}

PREREQ_MAP = {
    "Factorization": ["Linear Equations", "Polynomials"],
    "Quadratic Functions": ["Linear Functions"],
    "Solving Quadratics": ["Factorization", "Linear Equations"],
    "The Discriminant": ["Solving Quadratics"],
    "Applications of Quadratics": ["Solving Quadratics", "The Discriminant"],
    "Graph Interpretation": ["Linear Functions"],
    "Statistical Interpretation": ["Basic Probability"],
}


def _stable_seed(*parts: Any) -> int:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:16], 16)


def _detect_subject(text: str) -> str:
    low = text.lower()
    for key in MATH_CURRICULUM:
        if key in low:
            return key
    return "generic"


def _mock_curriculum(meta: dict) -> dict:
    subject = str(meta.get("subject", "")).lower()
    doc_name = str(meta.get("doc_filename", "")).lower()
    text_excerpt = str(meta.get("text_excerpt", ""))[:2000].lower()
    key = _detect_subject(f"{subject} {doc_name} {text_excerpt}")

    chapters = []
    if key in MATH_CURRICULUM:
        for ci, ch in enumerate(MATH_CURRICULUM[key]):
            topics = [
                {
                    "title": t["title"],
                    "description": f"Study of {t['title'].lower()}.",
                    "difficulty": t["difficulty"],
                    "objectives": [
                        f"Understand core ideas in {t['title'].lower()}",
                        f"Solve problems involving {t['title'].lower()}",
                    ],
                    "prerequisites": PREREQ_MAP.get(t["title"], []),
                }
                for t in ch["topics"]
            ]
            chapters.append(
                {
                    "title": ch["title"],
                    "description": ch["description"],
                    "order_index": ci,
                    "topics": topics,
                }
            )
    else:
        chapters = [
            {
                "title": f"Chapter {ci + 1}",
                "description": f"Core material of chapter {ci + 1}.",
                "order_index": ci,
                "topics": [
                    {
                        "title": f"Topic {ci + 1}{chr(97 + ti)}",
                        "description": f"A key topic in chapter {ci + 1}.",
                        "difficulty": 0.5,
                        "objectives": [f"Master the essentials of topic {ci + 1}{chr(97 + ti)}"],
                        "prerequisites": [],
                    }
                    for ti in range(3)
                ],
            }
            for ci in range(4)
        ]
    return {"chapters": chapters}


def _mock_lesson(meta: dict) -> dict:
    topic = str(meta.get("topic_title", "Topic"))
    level = str(meta.get("level", "standard"))
    chunks = meta.get("chunks", []) or []
    chunk_texts = [str(c.get("content", "")) for c in chunks if c.get("content")]
    objectives = meta.get("objectives", []) or []

    explanation_parts = []
    if chunk_texts:
        explanation_parts.append(chunk_texts[0][:1200])
    if len(chunk_texts) > 1:
        explanation_parts.append(chunk_texts[1][:1200])
    if not explanation_parts:
        explanation_parts.append(
            f"This lesson covers {topic}. It is the foundational material your teacher "
            f"provided. Work through the examples and then practise independently."
        )
    explanation = "\n\n".join(explanation_parts)

    sections = [
        {
            "name": "Key Concepts",
            "content": f"The central ideas of **{topic}** are covered below. "
            f"{'You are at a ' + level + ' level, so explanations are adjusted accordingly.' if level != 'standard' else 'Explanations are at a standard level.'}"
            + (
                "\n\n**Learning objectives:**\n" + "\n".join(f"- {o}" for o in objectives)
                if objectives
                else ""
            ),
        },
        {"name": "Explanation", "content": explanation},
        {
            "name": "Worked Example",
            "content": f"**Example:** Consider a typical problem on {topic}.\n\n"
            f"*Step 1:* Read the problem and identify what is given.\n"
            f"*Step 2:* Recall the relevant rule or method for {topic}.\n"
            f"*Step 3:* Apply the method step by step and check your answer.",
        },
        {
            "name": "Practice Problems",
            "content": f"1. Try a basic problem on {topic}.\n"
            f"2. Attempt a medium-difficulty problem on {topic}.\n"
            f"3. Challenge yourself with a harder problem on {topic}.",
        },
        {
            "name": "Common Mistakes",
            "content": f"Students often confuse the order of operations when working with {topic}. "
            f"Always show intermediate steps and verify your final result.",
        },
        {
            "name": "Summary",
            "content": f"You have reviewed **{topic}**. Make sure you can state the key rule, "
            f"solve a worked example unaided, and explain the idea to a friend.",
        },
    ]
    return {
        "title": f"Lesson: {topic}",
        "level": level,
        "sections": sections,
        "references": [
            {
                "source": str(c.get("source", "")),
                "page": c.get("page_start"),
                "heading": str(c.get("heading", "")),
            }
            for c in chunks
            if c.get("page_start") or c.get("source")
        ],
    }


_QUESTION_BANK: dict[str, list[dict]] = {
    "Linear Equations": [
        {
            "q": "Solve for x: 3x + 5 = 20",
            "ans": "x = 5",
            "distractors": ["x = 4", "x = 6", "x = 15"],
            "type": "mcq",
            "expl": "Subtract 5 from both sides: 3x = 15, then divide by 3: x = 5.",
        },
        {
            "q": "Solve for x: 2x - 7 = 9",
            "ans": "x = 8",
            "distractors": ["x = 1", "x = 13", "x = 16"],
            "type": "mcq",
            "expl": "2x = 16, so x = 8.",
        },
        {
            "q": "Solve for x: x/4 + 3 = 10",
            "ans": "x = 28",
            "distractors": ["x = 52", "x = 7", "x = 17"],
            "type": "mcq",
            "expl": "x/4 = 7, so x = 28.",
        },
    ],
    "Factorization": [
        {
            "q": "Factorise: x^2 + 5x + 6",
            "ans": "(x + 2)(x + 3)",
            "distractors": ["(x + 1)(x + 6)", "(x + 2)(x - 3)", "(x - 2)(x - 3)"],
            "type": "mcq",
            "expl": "Find two numbers that multiply to 6 and add to 5: 2 and 3.",
        },
        {
            "q": "Factorise: x^2 - 9",
            "ans": "(x + 3)(x - 3)",
            "distractors": ["(x + 9)(x - 1)", "(x - 9)(x + 1)", "(x + 3)^2"],
            "type": "mcq",
            "expl": "Difference of two squares: a^2 - b^2 = (a+b)(a-b).",
        },
    ],
    "Polynomials": [
        {
            "q": "Simplify: (2x^2 + 3x - 4) + (x^2 - x + 7)",
            "ans": "3x^2 + 2x + 3",
            "distractors": ["3x^2 + 4x - 11", "2x^2 + 2x + 3", "3x^2 - 2x + 3"],
            "type": "mcq",
            "expl": "Add like terms: (2+1)x^2 + (3-1)x + (-4+7).",
        },
    ],
    "The Discriminant": [
        {
            "q": "For x^2 + 4x + 4 = 0, the discriminant b^2 - 4ac is:",
            "ans": "0",
            "distractors": ["16", "-12", "4"],
            "type": "mcq",
            "expl": "a=1, b=4, c=4, so b^2 - 4ac = 16 - 16 = 0 (one repeated root).",
        },
        {
            "q": "A quadratic with a negative discriminant has:",
            "ans": "No real roots",
            "distractors": ["Two distinct real roots", "One real root", "Exactly three roots"],
            "type": "mcq",
            "expl": "A negative discriminant means no real roots.",
        },
    ],
    "Solving Quadratics": [
        {
            "q": "Solve: x^2 - 5x + 6 = 0",
            "ans": "x = 2 or x = 3",
            "distractors": ["x = 1 or x = 6", "x = -2 or x = -3", "x = 2 or x = -3"],
            "type": "mcq",
            "expl": "Factors: (x-2)(x-3) = 0.",
        },
    ],
    "Linear Functions": [
        {
            "q": "The slope of the line y = 3x - 2 is:",
            "ans": "3",
            "distractors": ["-2", "2", "-3"],
            "type": "mcq",
            "expl": "y = mx + c, so m = 3.",
        },
    ],
    "Quadratic Functions": [
        {
            "q": "The graph of y = x^2 - 4x + 3 opens:",
            "ans": "Upwards",
            "distractors": ["Downwards", "Sideways", "It does not open"],
            "type": "mcq",
            "expl": "The coefficient of x^2 is positive, so it opens upwards.",
        },
    ],
    "Graph Interpretation": [
        {
            "q": "The x-intercept of y = 2x - 6 is:",
            "ans": "x = 3",
            "distractors": ["x = -3", "x = 6", "x = 2"],
            "type": "mcq",
            "expl": "Set y = 0: 2x - 6 = 0, x = 3.",
        },
    ],
}


def _mock_quiz(meta: dict) -> dict:
    topic = str(meta.get("topic_title", ""))
    count = int(meta.get("count", 5))
    difficulty = float(meta.get("difficulty", 0.5))
    types = meta.get("types", ["mcq", "true_false"]) or ["mcq"]
    existing = meta.get("existing_prompts", []) or []
    variant = meta.get("variant", 0)
    existing_set = {str(p) for p in existing}

    rng = random.Random(_stable_seed("quiz", topic, count, difficulty, variant))
    questions: list[dict] = []
    bank = _QUESTION_BANK.get(topic, [])

    for item in bank:
        if len(questions) >= count:
            break
        if str(item["q"]) in existing_set:
            continue
        choices = list(item["distractors"]) + [item["ans"]]
        rng.shuffle(choices)
        questions.append(
            {
                "question_type": "mcq",
                "prompt": item["q"],
                "choices": choices,
                "correct_answer": {"value": item["ans"]},
                "explanation": item["expl"],
                "difficulty": difficulty,
                "source_ref": None,
            }
        )

    while len(questions) < count:
        qid = _stable_seed("genq", topic, len(questions))
        prompt = f"Which statement about {topic} is correct? (generated item {len(questions) + 1})"
        if prompt in existing_set:
            rng = random.Random(qid)
            prompt = f"Consider this {topic} question: what is the correct approach? (variant {len(questions)})"
        qtype = types[len(questions) % len(types)]
        if qtype == "true_false":
            questions.append(
                {
                    "question_type": "true_false",
                    "prompt": f"True or False: {topic} is an important topic in this course.",
                    "choices": ["True", "False"],
                    "correct_answer": {"value": "True"},
                    "explanation": f"This statement about {topic} is true.",
                    "difficulty": difficulty,
                    "source_ref": None,
                }
            )
        elif qtype == "numerical":
            questions.append(
                {
                    "question_type": "numerical",
                    "prompt": f"For a question on {topic}, the expected numeric result is 42.",
                    "choices": None,
                    "correct_answer": {"value": "42"},
                    "explanation": f"The canonical result for this {topic} problem is 42.",
                    "difficulty": difficulty,
                    "source_ref": None,
                }
            )
        else:
            questions.append(
                {
                    "question_type": "mcq",
                    "prompt": prompt,
                    "choices": ["Option A", "Option B", "Option C", "Option D"],
                    "correct_answer": {"value": "Option A"},
                    "explanation": f"The correct choice for this {topic} question is Option A.",
                    "difficulty": difficulty,
                    "source_ref": None,
                }
            )
    return {"questions": questions}


def _mock_grade(meta: dict) -> dict:
    student = str(meta.get("student_response", "")).strip().lower()
    correct = str(meta.get("correct_answer", "")).strip().lower()
    max_score = float(meta.get("max_score", 1.0))

    if not student:
        return {
            "score": 0.0,
            "max_score": max_score,
            "confidence": 0.99,
            "feedback": "No answer was provided.",
            "correct": False,
        }

    def normalize(s: str) -> str:
        s = re.sub(r"[^a-z0-9=<>+\-*/. ]", " ", s)
        return " ".join(s.split())

    overlap = _token_overlap(normalize(student), normalize(correct))
    if overlap >= 0.7:
        ratio, correct_flag, conf = 1.0, True, 0.9
    elif overlap >= 0.35:
        ratio, correct_flag, conf = 0.5, False, 0.6
    else:
        ratio, correct_flag, conf = 0.0, False, 0.7
    score = round(max_score * ratio, 2)
    return {
        "score": score,
        "max_score": max_score,
        "confidence": conf,
        "feedback": (
            "Great work, the answer is essentially correct."
            if correct_flag and ratio == 1.0
            else "Partially correct - compare your answer with the expected solution."
            if ratio > 0
            else "The answer does not match the expected response. Review the topic and try again."
        ),
        "correct": correct_flag,
    }


def _token_overlap(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(len(ta), len(tb))


def _mock_recommendation(meta: dict) -> dict:
    weak = meta.get("weak_topics", []) or []
    strong = meta.get("strong_topics", []) or []
    actions: list[str] = []
    if weak:
        actions.append(
            f"Review {', '.join(weak[:3])} with five targeted exercises before moving on."
        )
    if strong:
        actions.append(f"Keep {', '.join(strong[:2])} fresh with weekly revision.")
    if not actions:
        actions.append("Proceed to the next scheduled topic.")
    summary = (
        f"Focus on weak areas ({', '.join(weak) if weak else 'none flagged'}). "
        f"Strengths: {', '.join(strong) if strong else 'still building'}."
    )
    return {"summary": summary, "message": " ".join(actions), "actions": actions}


class MockProvider(LLMProvider):
    """Deterministic offline provider. Generates structured, testable output
    without any API key or network access."""

    name = "mock"

    HANDLERS: ClassVar[dict[str, Callable[[dict], dict]]] = {
        "curriculum_extract": _mock_curriculum,
        "lesson_generate": _mock_lesson,
        "quiz_generate": _mock_quiz,
        "grade_subjective": _mock_grade,
        "recommend_narrative": _mock_recommendation,
    }

    EMBED_DIM = settings.embedding_dim

    def generate(self, request: LLMRequest) -> dict[str, Any]:
        handler = self.HANDLERS.get(request.task)
        if handler is None:
            return {}
        return handler(request.meta)

    def embed(
        self,
        texts: list[str],
        mode: Literal["passage", "query"] | None = None,
    ) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def _embed(self, text: str) -> list[float]:
        vec = np.zeros(self.EMBED_DIM, dtype=np.float64)
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        for tok in tokens:
            for n in (2, 3):
                for i in range(len(tok) - n + 1):
                    gram = tok[i : i + n]
                    idx = _stable_seed("embed", gram) % self.EMBED_DIM
                    vec[idx] += 1.0
            vec[_stable_seed("embed", "tok", tok) % self.EMBED_DIM] += 2.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    @property
    def is_mock(self) -> bool:
        return True

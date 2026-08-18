from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import settings
from ..rag.retriever import RetrievedChunk, retrieve


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., Any]
    parameters: dict[str, str] = field(default_factory=dict)


def _rag_retrieve(
    collection: str,
    query: str,
    *,
    course_id: str | None = None,
    topic_id: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    chunks = retrieve(
        collection,
        query,
        course_id=course_id,
        topic_id=topic_id,
        limit=limit or settings.rag_top_k,
    )
    return [c.to_dict() for c in chunks]


def _web_search(query: str, max_results: int = 5) -> list[dict[str, Any]]:
    """SearXNG JSON API tool. Returns [] when not configured."""
    if not settings.searxng_url:
        logging.getLogger("adapted.tools").info("web_search_unavailable", reason="no_searxng_url")
        return []
    params = {
        "q": query,
        "format": "json",
        "engines": "google,bing",
        "number_of_results": max_results,
    }
    try:
        resp = httpx.get(
            f"{settings.searxng_url.rstrip('/')}/search",
            params=params,
            timeout=10.0,
            verify=not settings.searxng_insecure,
        )
        resp.raise_for_status()
        results = []
        for item in (resp.json().get("results") or [])[:max_results]:
            results.append(
                {
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content", "")[:500],
                }
            )
        return results
    except Exception as exc:  # noqa: BLE001
        logging.getLogger("adapted.tools").warning("web_search_failed", error=str(exc))
        return []


def _format_chunks(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [c.to_dict() for c in chunks]


def get_tools() -> dict[str, Tool]:
    return {
        "rag_retrieve": Tool(
            name="rag_retrieve",
            description="Retrieve relevant curriculum content from the course knowledge base.",
            fn=_rag_retrieve,
            parameters={"collection": "str", "query": "str", "course_id": "str|None"},
        ),
        "web_search": Tool(
            name="web_search",
            description="Search the web via SearXNG for supplementary material.",
            fn=_web_search,
            parameters={"query": "str", "max_results": "int"},
        ),
        "scheduler_validate": Tool(
            name="scheduler_validate",
            description="Validate study plan feasibility (deadlines, daily capacity, prerequisites).",
            fn=_validate_plan,
            parameters={"items": "list", "exam_date": "date|None", "daily_minutes": "int"},
        ),
        "mastery_calc": Tool(
            name="mastery_calc",
            description="Update topic mastery from the latest quiz score percentage.",
            fn=_calc_mastery,
            parameters={"current": "float", "attempts": "int", "score_percent": "float"},
        ),
        "dedupe_check": Tool(
            name="dedupe_check",
            description="Check whether a question prompt is a duplicate in a course.",
            fn=_check_duplicate,
            parameters={"course_id": "str", "prompt": "str"},
        ),
    }


def _validate_plan(
    items: list[dict[str, Any]], exam_date: Any, daily_minutes: int
) -> dict[str, Any]:
    from ..services.scheduler import PlanItem, validate_plan

    parsed = [
        PlanItem(
            **{
                k: i.get(k)
                for k in (
                    "topic_id",
                    "title",
                    "day_index",
                    "sequence",
                    "estimated_minutes",
                    "goal",
                    "reason",
                    "status",
                )
            }
        )
        for i in items
    ]
    res = validate_plan(parsed, exam_date=exam_date, daily_minutes=daily_minutes)
    return {"valid": res.valid, "errors": res.errors, "total_minutes": res.total_minutes}


def _calc_mastery(current: float, attempts: int, score_percent: float) -> float:
    from ..services.mastery import update_mastery

    return update_mastery(current, attempts, score_percent)


def _check_duplicate(course_id: str, prompt: str) -> bool:
    from ..database.session import SessionLocal
    from ..models import Question
    from ..services.grading import question_hash

    db = SessionLocal()
    try:
        from sqlalchemy import select

        existing = db.scalars(
            select(Question.question_hash).where(Question.course_id == course_id)
        ).all()
        return question_hash(course_id, prompt) in set(existing)
    finally:
        db.close()

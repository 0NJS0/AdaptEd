"""Thin, DB-free entry points for running the OBE agent over raw inputs.

These wrap ``OBEAgent`` so both the HTTP router and the tests can invoke the
agent without a database session or an authenticated request. The OBE agent
needs no DB for text/structured input, so analysis runs fully in-process and
offline (with the mock provider).
"""

from __future__ import annotations

import uuid
from typing import Any

from ..agents.message import AgentMessage
from ..agents.obe_agent import OBEAgent
from ..agents.obe_author_agent import OBEAuthorAgent


def _provider(provider: Any | None) -> Any:
    if provider is not None:
        return provider
    # Imported lazily so this module stays importable without the LLM extras.
    from ..llm.registry import get_provider

    return get_provider()


def _message(action: str, payload: dict[str, Any]) -> AgentMessage:
    tid = f"OBE-{uuid.uuid4().hex[:10].upper()}"
    return AgentMessage(
        task_id=tid,
        correlation_id=tid,
        sender="api",
        receiver="obe_agent",
        action=action,
        payload=payload,
    )


def analyze_text(text: str, *, polish: bool = False, provider: Any | None = None) -> dict[str, Any]:
    """Extract, validate, suggest and summarize an outline given its raw text."""
    agent = OBEAgent(db=None, provider=_provider(provider), bus=None)
    result = agent.handle(_message("obe.summarize", {"outline_text": text, "polish": polish}))
    if result.error:
        raise RuntimeError(result.error)
    return result.output


def validate_text(text: str, *, provider: Any | None = None) -> dict[str, Any]:
    agent = OBEAgent(db=None, provider=_provider(provider), bus=None)
    result = agent.handle(_message("obe.validate", {"outline_text": text}))
    if result.error:
        raise RuntimeError(result.error)
    return result.output


def suggest(
    *,
    description: str | None = None,
    co_id: str | None = None,
    cos: list[dict[str, Any]] | None = None,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Suggest Bloom/PO/K-P-A for a single CO description or a list of COs."""
    payload: dict[str, Any] = {}
    if cos:
        payload["cos"] = cos
    elif description:
        payload["description"] = description
        if co_id:
            payload["co_id"] = co_id
    else:
        raise ValueError("Provide 'description' or a 'cos' list.")
    agent = OBEAgent(db=None, provider=_provider(provider), bus=None)
    result = agent.handle(_message("obe.suggest_mapping", payload))
    if result.error:
        raise RuntimeError(result.error)
    return result.output


def author(
    *,
    course_title: str = "",
    subject: str = "",
    topics: list[str] | None = None,
    count: int = 4,
    po_hint: str | None = None,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Generate a set of OBE-compliant Course Outcomes."""
    payload = {
        "course_title": course_title,
        "subject": subject,
        "topics": topics or [],
        "count": count,
        "po_hint": po_hint,
    }
    agent = OBEAuthorAgent(db=None, provider=_provider(provider), bus=None)
    result = agent.handle(_message("obe.author", payload))
    if result.error:
        raise RuntimeError(result.error)
    return result.output


def improve(
    *,
    description: str,
    target_level: int | None = None,
    target_po: str | None = None,
    co_id: str | None = None,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Rewrite a single Course Outcome for Bloom/PO consistency."""
    payload: dict[str, Any] = {"description": description}
    if target_level is not None:
        payload["target_level"] = target_level
    if target_po:
        payload["target_po"] = target_po
    if co_id:
        payload["co_id"] = co_id
    agent = OBEAuthorAgent(db=None, provider=_provider(provider), bus=None)
    result = agent.handle(_message("obe.improve", payload))
    if result.error:
        raise RuntimeError(result.error)
    return result.output

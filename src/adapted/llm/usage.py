"""Per-run LLM token-usage accounting and cost estimation.

An agent pipeline runs on its own worker thread, and every LLM call happens deep
inside an agent. Rather than thread usage numbers up through every return value,
we accumulate them in a ``contextvars`` counter that lives for the duration of
one run: the runtime calls :func:`start` before invoking the graph, each provider
call records into the active counter, and the runtime reads the total afterwards.

Costs are an *estimate*: real providers report token counts; the mock provider
estimates them from text length so the dashboard still shows figures offline.
"""

from __future__ import annotations

import contextvars
from dataclasses import dataclass

_USAGE: contextvars.ContextVar["Usage | None"] = contextvars.ContextVar("llm_usage", default=None)


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def start() -> Usage:
    """Begin (or reset) usage accounting for the current run/thread."""
    u = Usage()
    _USAGE.set(u)
    return u


def record(prompt: int = 0, completion: int = 0) -> None:
    """Add one LLM call's token counts to the active counter (no-op if none)."""
    u = _USAGE.get()
    if u is None:
        return
    u.prompt_tokens += max(0, int(prompt or 0))
    u.completion_tokens += max(0, int(completion or 0))
    u.calls += 1


def current() -> Usage | None:
    return _USAGE.get()


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 characters per token) for offline/mock runs."""
    if not text:
        return 0
    return max(1, len(text) // 4)


def estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    """Estimated USD cost from the configured per-1K-token prices (0 for free models)."""
    from ..config import settings

    cost = (
        prompt_tokens / 1000.0 * settings.llm_price_input_per_1k
        + completion_tokens / 1000.0 * settings.llm_price_output_per_1k
    )
    return round(cost, 6)

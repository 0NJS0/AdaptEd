from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class LLMRequest:
    """A single LLM call.

    `task` identifies the kind of generation (used by deterministic/mock
    providers and for prompt bookkeeping). `prompt` is the full instruction
    for real providers. `schema` is a JSON Schema for structured output.
    `meta` carries structured inputs so non-LLM providers can build
    deterministic, testable outputs.
    """

    task: str
    prompt: str
    schema: dict[str, Any]
    meta: dict[str, Any] = field(default_factory=dict)
    temperature: float = 0.7


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, request: LLMRequest) -> dict[str, Any]:
        """Return a dict conforming to request.schema."""

    @abstractmethod
    def embed(
        self,
        texts: list[str],
        mode: Literal["passage", "query"] | None = None,
    ) -> list[list[float]]:
        """Return dense embeddings for texts.

        ``mode`` selects query-aware embedding behaviour for models that
        distinguish document ("passage") from search ("query") inputs.
        """

    @property
    def is_mock(self) -> bool:
        return False

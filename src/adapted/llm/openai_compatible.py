from __future__ import annotations

import json
import logging
from typing import Any, Literal

from openai import OpenAI

from ..config import settings
from .base import LLMProvider, LLMRequest

log = logging.getLogger("adapted.llm.openai_compatible")


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI-compatible provider pointed at OpenRouter or any OpenAI-compatible
    endpoint."""

    name = "openrouter"

    def __init__(self, base_url: str, api_key: str, model: str, embed_model: str) -> None:
        self.model = model
        self.embed_model = embed_model
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or "synthetic",
            timeout=settings.llm_timeout_seconds,
            default_headers={
                "HTTP-Referer": "https://adapted.app",
                "X-Title": "AdaptED",
            },
        )
        self._query_aware = "nemotron" in embed_model.lower()

    def generate(self, request: LLMRequest) -> dict[str, Any]:
        schema_block = json.dumps(request.schema)
        system = (
            "You are a precise educational AI. Always respond with valid JSON matching the "
            f"given JSON Schema exactly.\nJSON Schema:\n{schema_block}"
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=request.temperature,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": request.prompt},
                ],
            )
            content = resp.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception as exc:
            log.error("llm_generate_failed task=%s error=%s", request.task, exc)
            raise

    def embed(
        self,
        texts: list[str],
        mode: Literal["passage", "query"] | None = None,
    ) -> list[list[float]]:
        kwargs: dict[str, Any] = {
            "model": self.embed_model,
            "input": texts,
            "encoding_format": "float",
        }
        if mode and self._query_aware:
            kwargs["extra_body"] = {"input_type": mode}
        resp = self.client.embeddings.create(**kwargs)
        embeds = [item.embedding for item in resp.data]
        expected = settings.embedding_dim
        for embedding in embeds:
            if len(embedding) != expected:
                raise ValueError(
                    f"Embedding dimension mismatch: model '{self.embed_model}' "
                    f"returned {len(embedding)} dims but EMBEDDING_DIM={expected}. "
                    "Align .env EMBEDDING_DIM with the model's output dimension."
                )
        return embeds

    @property
    def is_mock(self) -> bool:
        return False

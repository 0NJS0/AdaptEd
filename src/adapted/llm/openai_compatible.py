from __future__ import annotations

import json
import logging
from typing import Any, Literal

from openai import OpenAI

from ..config import settings
from .base import LLMProvider, LLMRequest
from .jsonparse import extract_json

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
            "You are a precise educational AI. Always respond with a single valid JSON "
            "object matching the given JSON Schema exactly. Output ONLY the JSON — no "
            f"prose, no markdown code fences.\nJSON Schema:\n{schema_block}"
        )
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": request.prompt},
        ]
        try:
            resp = self._create(messages, request.temperature)
            self._record_usage(resp)
            content = resp.choices[0].message.content if resp.choices else None
            data = extract_json(content)
            if data is None:
                snippet = (content or "").strip()[:200]
                log.error(
                    "llm_generate_no_json task=%s model=%s content=%r",
                    request.task,
                    self.model,
                    snippet,
                )
                raise ValueError(
                    f"Model '{self.model}' returned no valid JSON for task "
                    f"'{request.task}' (got: {snippet!r}). Try a different free model "
                    "that supports JSON output."
                )
            return data
        except Exception as exc:
            log.error("llm_generate_failed task=%s error=%s", request.task, exc)
            raise

    def _create(self, messages: list[dict], temperature: float):
        """Call chat.completions, retrying without response_format for models that
        reject it (many free models don't support forced JSON mode)."""
        try:
            return self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                response_format={"type": "json_object"},
                messages=messages,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "llm response_format unsupported for model=%s (%s); retrying without it",
                self.model,
                exc,
            )
            return self.client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                messages=messages,
            )

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
        self._record_usage(resp)
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

    @staticmethod
    def _record_usage(resp: Any) -> None:
        """Record token usage from an OpenAI-style response into the run counter."""
        from .usage import record

        u = getattr(resp, "usage", None)
        if u is None:
            return
        record(
            prompt=getattr(u, "prompt_tokens", 0) or 0,
            completion=getattr(u, "completion_tokens", 0) or 0,
        )

    @property
    def is_mock(self) -> bool:
        return False

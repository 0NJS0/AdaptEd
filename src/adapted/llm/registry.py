from __future__ import annotations

import logging
from functools import lru_cache

from ..config import settings
from .base import LLMProvider
from .mock import MockProvider
from .openai_compatible import OpenAICompatibleProvider

log = logging.getLogger("adapted.llm.registry")


def get_provider() -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockProvider()
    if settings.llm_provider in ("openrouter", "openai"):
        return OpenAICompatibleProvider(
            base_url=settings.openrouter_base_url.rstrip("/"),
            api_key=settings.openrouter_api_key,
            model=settings.llm_model,
            embed_model=settings.embed_model,
        )
    log.warning("unknown llm_provider %s, falling back to mock", settings.llm_provider)
    return MockProvider()


def get_embed_provider() -> LLMProvider:
    """Provider used for embeddings (may differ from the chat provider).

    Embeddings route through the OpenRouter embed provider (free models only)
    so pgvector stores real vectors; falls back to deterministic mock offline."""
    if settings.embed_provider in ("openrouter", "openai"):
        return OpenAICompatibleProvider(
            base_url=settings.openrouter_base_url.rstrip("/"),
            api_key=settings.openrouter_api_key,
            model=settings.llm_model,
            embed_model=settings.embed_model,
        )
    return MockProvider()


@lru_cache
def get_provider_cached() -> LLMProvider:
    return get_provider()


@lru_cache
def get_embed_provider_cached() -> LLMProvider:
    return get_embed_provider()

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from ..llm.registry import get_embed_provider_cached


@lru_cache(maxsize=4096)
def _embed_single(text: str, mode: Literal["passage", "query"] | None = None) -> tuple[float, ...]:
    return tuple(get_embed_provider_cached().embed([text], mode=mode)[0])


def embed_texts(
    texts: list[str], mode: Literal["passage", "query"] | None = None
) -> list[list[float]]:
    if len(texts) == 1:
        return [list(_embed_single(texts[0], mode))]
    return get_embed_provider_cached().embed(texts, mode=mode)


def embed_text(text: str, mode: Literal["passage", "query"] | None = None) -> list[float]:
    return list(_embed_single(text, mode))

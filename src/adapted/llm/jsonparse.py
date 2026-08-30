"""Best-effort JSON recovery from LLM completions.

Free/community models often wrap JSON in a ```json ... ``` fence, prepend prose,
or return an empty completion — a bare ``json.loads`` then fails with
"Expecting value: line 1 column 1 (char 0)". This module strips fences and, that
failing, slices out the first balanced-looking object/array before parsing.

Kept dependency-free (no ``openai`` import) so it is easy to unit-test offline.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str | None) -> dict[str, Any] | list[Any] | None:
    """Return parsed JSON from ``text``, or ``None`` if nothing parseable is found."""
    if not text or not text.strip():
        return None
    t = text.strip()
    m = _FENCE.search(t)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start, end = t.find(open_ch), t.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(t[start : end + 1])
            except Exception:  # noqa: BLE001
                continue
    return None

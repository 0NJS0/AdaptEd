"""Author and improve OBE-compliant Course Outcomes.

Where the OBE Mapping agent *analyzes and validates* an existing outline, this
module *generates* — it drafts new Course Outcomes for a course/topic set with a
sensible Bloom spread, and rewrites a single flagged CO so its action verb, Bloom
level and PO/K-P-A line up with the AIUB CS OBE Manual.

Deterministic and offline (no LLM required); every result carries a rationale and
the list of changes made, and nothing here mutates a source document.
"""

from __future__ import annotations

import re

from . import mapping
from . import reference as ref
from .schema import KPA, AuthoredCO, ImprovedCO

# One canonical action verb per Bloom Cognitive level (used when (re)writing COs).
CANONICAL_VERB: dict[int, str] = {
    1: "Define",
    2: "Explain",
    3: "Apply",
    4: "Analyze",
    5: "Evaluate",
    6: "Design",
}

# A natural-reading CO template per Bloom level; the leading verb matches the
# level so the generated CO passes the verb<->Bloom validation rule.
_TEMPLATE: dict[int, str] = {
    1: "Define the key terms and components of {topic}.",
    2: "Explain the fundamental concepts of {topic}.",
    3: "Apply {topic} to solve a given problem.",
    4: "Analyze {topic} to compare possible approaches.",
    5: "Evaluate {topic} to justify an appropriate solution.",
    6: "Design a solution for a complex engineering problem using {topic}.",
}

_STOPWORDS = {"a", "an", "the", "to", "of"}


def _bloom_ladder(count: int) -> list[int]:
    """A spread of Bloom levels for ``count`` outcomes (avoids all-same-level)."""
    base = [3, 4, 5, 6]
    if count <= len(base):
        return base[:count] if count > 0 else []
    ladder = list(base)
    while len(ladder) < count:
        ladder.append(3 + (len(ladder) % 4))  # cycle 3..6
    return ladder


def _rewrite_leading_verb(description: str, canonical: str) -> str:
    """Replace the first meaningful word of a CO with ``canonical`` (keep the rest)."""
    tokens = description.strip().split()
    for i, tok in enumerate(tokens):
        word = re.sub(r"[^A-Za-z]", "", tok)
        if word and word.lower() not in _STOPWORDS:
            tokens[i] = canonical
            return " ".join(tokens)
    return f"{canonical} {description.strip()}"


def author_cos(
    *,
    course_title: str = "",
    subject: str = "",
    topics: list[str] | None = None,
    count: int = 4,
    po_hint: str | None = None,
) -> list[AuthoredCO]:
    """Draft ``count`` OBE-compliant Course Outcomes across a spread of Bloom levels."""
    topics = [t.strip() for t in (topics or []) if t and t.strip()]
    count = max(1, min(int(count or 4), 12))
    levels = _bloom_ladder(count)
    fallback_topic = subject or course_title or "the core concepts of the course"

    out: list[AuthoredCO] = []
    for i, level in enumerate(levels, start=1):
        topic = topics[i - 1] if i - 1 < len(topics) else fallback_topic
        description = _TEMPLATE[level].format(topic=topic)
        suggestion = mapping.suggest_for_description(f"CO{i}", description)
        pos = [po_hint] if po_hint else suggestion.suggested_pos
        rationale = [
            f"Verb “{CANONICAL_VERB[level].lower()}” fixes this outcome at Bloom "
            f"Cognitive level {level} ({ref.level_name('cognitive', level)}).",
        ]
        rationale += suggestion.rationale[1:]  # PO / K-P-A reasoning
        out.append(
            AuthoredCO(
                id=f"CO{i}",
                description=description,
                verb=CANONICAL_VERB[level].lower(),
                bloom_level=level,
                bloom_name=ref.level_name("cognitive", level) or "",
                suggested_pos=pos,
                suggested_kpa=suggestion.suggested_kpa,
                rationale=rationale,
            )
        )
    return out


def improve_co(
    description: str,
    *,
    target_level: int | None = None,
    target_po: str | None = None,
    co_id: str = "CO1",
) -> ImprovedCO:
    """Rewrite one CO so its verb, Bloom level and PO/K-P-A are consistent.

    If ``target_level`` is given, the CO is rewritten to that level; otherwise the
    level implied by the current verb is kept (and any tagged-level mismatch the
    validator would flag is resolved by aligning the verb).
    """
    original = description.strip()
    current_verb = mapping.leading_verb(original)
    inferred = ref.cognitive_level_for_verb(current_verb)
    level = target_level or inferred or 3
    level = max(1, min(int(level), 6))

    canonical = CANONICAL_VERB[level]
    improved = _rewrite_leading_verb(original, canonical)
    suggestion = mapping.suggest_for_description(co_id, improved)
    pos = [target_po] if target_po else suggestion.suggested_pos

    changes: list[str] = []
    if current_verb and canonical.lower() != current_verb.lower():
        inferred_txt = (
            f" (was Bloom level {inferred})" if inferred and inferred != level else ""
        )
        changes.append(
            f"Rewrote the leading verb “{current_verb}”{inferred_txt} to "
            f"“{canonical.lower()}” so it matches Bloom level {level} "
            f"({ref.level_name('cognitive', level)})."
        )
    if target_po:
        changes.append(f"Set the mapped PO to {target_po} as requested.")
    elif pos:
        changes.append(f"Suggested PO {', '.join(pos)} from the outcome's content.")
    if not changes:
        changes.append("The outcome already reads as compliant; no change was needed.")

    return ImprovedCO(
        co_id=co_id,
        original_description=original,
        improved_description=improved,
        verb=canonical.lower(),
        bloom_level=level,
        bloom_name=ref.level_name("cognitive", level) or "",
        suggested_pos=pos,
        suggested_kpa=suggestion.suggested_kpa or KPA(),
        changes=changes,
        rationale=suggestion.rationale,
    )

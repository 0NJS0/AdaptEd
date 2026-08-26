"""Assistive CO -> PO / Bloom / K-P-A mapping suggestions.

Given a Course Outcome description (or a whole outline with gaps), propose a
Bloom level+domain, the best-fit Program Outcome family, and a K/P/A set — each
with a short rationale that cites the OBE Manual criterion it derives from.

These are *suggestions*: the faculty member accepts or overrides them. Nothing
here overwrites an author's mapping.
"""

from __future__ import annotations

import re

from . import reference as ref
from .schema import KPA, CourseOutcome, MappingSuggestion

# PO family <- keyword signals in a CO description. Order matters: the first
# family whose signals hit wins as the primary suggestion; others are secondary.
_PO_SIGNALS: list[tuple[str, tuple[str, ...]]] = [
    ("a", ("mathematics", "natural science", "engineering fundamental", "first principle",
           "number system", "boolean", "logic gate", "hardware", "architecture")),
    ("b", ("identify", "formulate", "analyse", "analyze", "research literature",
           "investigate the problem")),
    ("c", ("design solution", "design a solution", "design the solution")),
    ("d", ("investigation", "experiment", "research-based", "conduct investigation")),
    ("e", ("tool", "technique", "modern engineering", "modelling", "model ", "uml",
           "software metric", "resource", "diagram", "framework")),
    ("f", ("societal", "society", "health", "safety", "legal", "cultural", "contextual")),
    ("g", ("sustainability", "environment", "impact of professional")),
    ("h", ("ethic", "professional responsibility")),
    ("i", ("team", "individual", "leader", "collaborat")),
    ("j", ("communicate", "report", "presentation", "documentation")),
    ("k", ("management", "economic", "project management", "cost", "estimation", "scheduling")),
    ("l", ("life-long", "lifelong", "independent learning", "self-study")),
]

_STOPWORDS = {"a", "an", "the", "to", "of"}


def leading_verb(description: str) -> str:
    """First meaningful word of a CO description, lower-cased."""
    for tok in re.findall(r"[A-Za-z][A-Za-z\-]*", description):
        low = tok.lower()
        if low not in _STOPWORDS:
            return low
    return ""


def _suggest_pos(description: str) -> list[str]:
    low = description.lower()
    hits: list[str] = []
    for family, signals in _PO_SIGNALS:
        if any(sig in low for sig in signals):
            hits.append(f"PO-{family}-1")
    return hits


def _suggest_kpa(description: str, pos: list[str]) -> KPA:
    low = description.lower()
    families = {ref.po_family(p) for p in pos}
    k: list[str] = []
    p: list[str] = []
    a: list[str] = []

    if "a" in families:
        k.append("K1")
    if "mathematic" in low or "boolean" in low:
        k.append("K2")
    if {"b", "c"} & families:
        k.append("K3")
    if "design" in low or "c" in families:
        k.append("K5")
    if {"e"} & families or "tool" in low or "model" in low:
        k.append("K6")
    if {"f", "g", "h"} & families or "societal" in low or "ethic" in low:
        k.append("K7")

    if any(sig in low for sig in ref.COMPLEX_PROBLEM_SIGNALS):
        p.append("P1")
    if "conflict" in low:
        p.append("P2")
    if "stakeholder" in low:
        p.append("P6")

    # de-duplicate, keep order
    return KPA(k=list(dict.fromkeys(k)), p=list(dict.fromkeys(p)), a=list(dict.fromkeys(a)))


def suggest_for_description(co_id: str, description: str) -> MappingSuggestion:
    """Produce a full mapping suggestion for one CO description."""
    verb = leading_verb(description)
    level = ref.cognitive_level_for_verb(verb)
    name = ref.level_name("cognitive", level) if level else ""
    pos = _suggest_pos(description)
    kpa = _suggest_kpa(description, pos)

    rationale: list[str] = []
    if level:
        rationale.append(
            f"Verb “{verb}” is a Bloom Cognitive level-{level} ({name}) action per the "
            f"OBE Manual verb list."
        )
    else:
        rationale.append(
            f"Verb “{verb}” was not found in the OBE Manual Bloom verb lists; set the "
            f"level manually."
        )
    if pos:
        fam = ref.po_family(pos[0])
        rationale.append(
            f"Content signals map to PO-{fam}: “{ref.PROGRAM_OUTCOMES.get(fam, '')[:70]}…”."
        )
    else:
        rationale.append("No strong PO keyword signals detected; choose the PO family by hand.")
    if kpa.k or kpa.p or kpa.a:
        rationale.append(
            f"K/P/A suggested from content: K={kpa.k or '—'}, P={kpa.p or '—'}, A={kpa.a or '—'}."
        )

    return MappingSuggestion(
        co_id=co_id,
        description=description,
        verb=verb,
        suggested_domain="cognitive",
        suggested_bloom_level=level,
        suggested_bloom_name=name or "",
        suggested_pos=pos,
        suggested_kpa=kpa,
        rationale=rationale,
    )


def suggest_for_co(co: CourseOutcome) -> MappingSuggestion:
    return suggest_for_description(co.id, co.description)

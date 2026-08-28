"""AIUB CS OBE Manual reference vocabulary.

Everything the validator and mapper reason against — Program Outcomes, Bloom's
Taxonomy verbs/levels across the three domains, and the K/P/A indicator sets —
is encoded here verbatim from the OBE Manual so mappings can be checked and
justified against a single authoritative source.

Ref: https://www.aiub.edu/cs-obe-manual
"""

from __future__ import annotations

# --------------------------------------------------------------------------
# Program Outcomes (PO a..l). Short titles taken from the OBE Manual.
# Course outlines reference *indicators* of these, e.g. "PO-a-1", "PO-f-2".
# --------------------------------------------------------------------------
PROGRAM_OUTCOMES: dict[str, str] = {
    "a": "Apply knowledge of mathematics, natural science and engineering "
    "fundamentals to complex engineering problems.",
    "b": "Identify, formulate, research literature and analyse complex "
    "engineering problems.",
    "c": "Design solutions for complex engineering problems.",
    "d": "Conduct investigations of complex problems using research-based knowledge.",
    "e": "Create, select and apply appropriate techniques, resources and modern "
    "engineering tools.",
    "f": "Apply reasoning informed by contextual knowledge to assess societal, "
    "health, safety, legal and cultural issues.",
    "g": "Understand and evaluate the sustainability and impact of professional "
    "engineering work.",
    "h": "Apply ethical principles and commit to professional ethics.",
    "i": "Function effectively as an individual and as a member or leader in "
    "diverse teams.",
    "j": "Communicate effectively on complex engineering activities.",
    "k": "Demonstrate knowledge and understanding of engineering management "
    "principles.",
    "l": "Recognise the need for, and have the ability to engage in, independent "
    "and life-long learning.",
}

VALID_PO_FAMILIES: frozenset[str] = frozenset(PROGRAM_OUTCOMES)

# --------------------------------------------------------------------------
# Bloom's Taxonomy. For each domain: level number -> (level name, action verbs).
# Verbs are lower-cased; used to infer/validate the declared level of a CO.
# --------------------------------------------------------------------------
COGNITIVE: dict[int, tuple[str, tuple[str, ...]]] = {
    1: ("Remembering", ("list", "recite", "outline", "define", "name", "match",
                         "quote", "recall", "identify", "label", "recognize",
                         "state", "memorize")),
    2: ("Understanding", ("describe", "explain", "comprehend", "defend",
                          "distinguish", "generalize", "predict", "summarize",
                          "interpret", "discuss", "paraphrase", "illustrate",
                          "classify")),
    3: ("Applying", ("calculate", "apply", "change", "compute", "solve",
                     "manipulate", "use", "demonstrate", "implement", "operate",
                     "practice", "show", "determine")),
    4: ("Analyzing", ("classify", "analyze", "break down", "compare",
                      "categorize", "differentiate", "diagram", "distinguish",
                      "examine", "contrast", "investigate", "separate")),
    5: ("Evaluating", ("choose", "support", "relate", "determine", "defend",
                       "judge", "grade", "evaluate", "assess", "justify",
                       "critique", "rank", "measure", "recommend")),
    6: ("Creating", ("design", "formulate", "build", "invent", "create",
                     "compose", "generate", "derive", "construct", "develop",
                     "plan", "produce", "devise")),
}

PSYCHOMOTOR: dict[int, tuple[str, tuple[str, ...]]] = {
    1: ("Imitation", ("adhere", "follow", "repeat", "reproduce", "trace")),
    2: ("Manipulation", ("build", "complete", "execute", "implement", "play",
                         "perform", "operate")),
    3: ("Precision", ("adapt", "alter", "construct", "calibrate", "combine",
                      "control", "create", "master")),
    4: ("Articulation", ("adapt", "combine", "construct", "coordinate", "create",
                         "develop", "integrate", "formulate")),
    5: ("Naturalization", ("create", "design", "develop", "invent", "specify",
                           "manage")),
}

AFFECTIVE: dict[int, tuple[str, tuple[str, ...]]] = {
    1: ("Receiving", ("acknowledge", "ask", "choose", "describe", "follow",
                      "identify", "listen")),
    2: ("Responding", ("answer", "assist", "aid", "comply", "conform", "discuss",
                       "enjoy", "follow", "practice")),
    3: ("Valuing", ("appreciate", "demonstrate", "differentiate", "explain",
                    "follow", "form", "value", "justify")),
    4: ("Organization", ("adhere", "alter", "arrange", "choose", "combine",
                         "compare", "organize", "prioritize")),
    5: ("Characterization", ("act", "display", "modify", "perform", "revise",
                             "serve", "solve", "verify", "influence")),
}

DOMAINS: dict[str, dict[int, tuple[str, tuple[str, ...]]]] = {
    "cognitive": COGNITIVE,
    "psychomotor": PSYCHOMOTOR,
    "affective": AFFECTIVE,
}

# --------------------------------------------------------------------------
# Knowledge profile (K1..K8), complex-problem attributes (P1..P7) and complex
# activity attributes (A1..A5).
# --------------------------------------------------------------------------
KNOWLEDGE_PROFILE: dict[str, str] = {
    "K1": "A systematic, theory-based understanding of the natural sciences "
    "applicable to the discipline.",
    "K2": "Conceptually-based mathematics, numerical analysis, statistics and "
    "formal aspects of computer and information science.",
    "K3": "A systematic, theory-based formulation of engineering fundamentals "
    "required in the engineering discipline.",
    "K4": "Engineering specialist knowledge that provides theoretical frameworks "
    "and bodies of knowledge for the accepted practice areas.",
    "K5": "Knowledge that supports engineering design in a practice area.",
    "K6": "Knowledge of engineering practice (technology) in the practice areas "
    "in the engineering discipline.",
    "K7": "Comprehension of the role of engineering in society and identified "
    "issues in engineering practice: ethics and impacts (economic, social, "
    "cultural, environmental, sustainability).",
    "K8": "Engagement with selected knowledge in the research literature of the "
    "discipline.",
}

PROBLEM_ATTRS: dict[str, str] = {
    "P1": "Depth of knowledge required — cannot be resolved without in-depth "
    "engineering knowledge at the level of K3-K8.",
    "P2": "Range of conflicting requirements — wide-ranging or conflicting "
    "technical, engineering and other issues.",
    "P3": "Depth of analysis required — no obvious solution; requires abstract "
    "thinking and originality in analysis.",
    "P4": "Familiarity of issues — involve infrequently encountered issues.",
    "P5": "Extent of applicable codes — outside problems encompassed by "
    "standards and codes of practice.",
    "P6": "Extent of stakeholder involvement — diverse groups of stakeholders "
    "with widely varying needs.",
    "P7": "Interdependence — high-level problems including many component parts "
    "or sub-problems.",
}

ACTIVITY_ATTRS: dict[str, str] = {
    "A1": "Range of resources — involve the use of diverse resources.",
    "A2": "Level of interaction — resolution of significant problems arising "
    "from interactions between wide-ranging or conflicting requirements.",
    "A3": "Innovation — creative use of engineering principles and research-based "
    "knowledge.",
    "A4": "Consequences to society and the environment — significant consequences "
    "in a range of contexts.",
    "A5": "Familiarity — can extend beyond previous experiences by applying "
    "principles-based approaches.",
}

VALID_K = frozenset(KNOWLEDGE_PROFILE)
VALID_P = frozenset(PROBLEM_ATTRS)
VALID_A = frozenset(ACTIVITY_ATTRS)

# Phrases in a CO/PO that signal a "complex engineering problem" and therefore
# imply the presence of P-attributes (used by the K/P/A consistency rule).
COMPLEX_PROBLEM_SIGNALS: tuple[str, ...] = (
    "complex engineering problem",
    "complex problem",
    "complex engineering",
)


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------
def level_name(domain: str, level: int) -> str | None:
    """Bloom level name for a (domain, level), e.g. ('cognitive', 3) -> 'Applying'."""
    table = DOMAINS.get(domain.lower())
    if not table or level not in table:
        return None
    return table[level][0]


def classify_verb(verb: str) -> list[tuple[str, int]]:
    """Return every (domain, level) whose verb set contains ``verb``.

    A verb can legitimately appear in more than one domain/level (e.g. "explain"
    is Cognitive-2 and Affective-3); callers use the full set to judge whether a
    *declared* level is defensible rather than forcing a single answer.
    """
    v = verb.strip().lower()
    hits: list[tuple[str, int]] = []
    for domain, table in DOMAINS.items():
        for lvl, (_name, verbs) in table.items():
            if v in verbs:
                hits.append((domain, lvl))
    return hits


def cognitive_level_for_verb(verb: str) -> int | None:
    """Best-guess Cognitive level for a verb, or None if unknown."""
    for domain, lvl in classify_verb(verb):
        if domain == "cognitive":
            return lvl
    return None


def is_valid_po_indicator(po_id: str) -> bool:
    """True for a well-formed, known PO indicator id like 'PO-a-1' or 'PO-f-2'."""
    parts = po_id.strip().upper().split("-")
    if len(parts) != 3 or parts[0] != "PO":
        return False
    family = parts[1].lower()
    return family in VALID_PO_FAMILIES and parts[2].isdigit()


def po_family(po_id: str) -> str | None:
    """Extract the PO family letter from an indicator id ('PO-f-2' -> 'f')."""
    parts = po_id.strip().upper().split("-")
    if len(parts) >= 2 and parts[0] == "PO":
        return parts[1].lower()
    return None

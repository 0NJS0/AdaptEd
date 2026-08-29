"""Static description of the LangGraph agent pipeline for visualization.

Mirrors the graph built in ``graph/runtime.py`` (``AgentRuntime.compile``). It is
kept as plain data so the UI can draw the execution graph — and highlight the
path a specific run actually took — without instantiating agents or a database.
"""

from __future__ import annotations

# node id -> (display label, the agent that runs it | None for control nodes)
NODES: dict[str, tuple[str, str | None]] = {
    "supervisor": ("Supervisor", "supervisor"),
    "curriculum_agent": ("Curriculum", "curriculum_agent"),
    "plan_create": ("Plan · create", "planner_agent"),
    "plan_modify": ("Plan · adapt", "planner_agent"),
    "lesson_agent": ("Lesson", "lesson_agent"),
    "quiz_agent": ("Quiz", "quiz_agent"),
    "grading_agent": ("Grading", "grading_agent"),
    "performance_agent": ("Performance", "performance_agent"),
    "recommendation_agent": ("Recommendation", "recommendation_agent"),
    "obe_extract": ("OBE · extract", "obe_agent"),
    "obe_validate": ("OBE · validate", "obe_agent"),
    "obe_suggest": ("OBE · suggest", "obe_agent"),
    "obe_summarize": ("OBE · summarize", "obe_agent"),
    "finalize": ("Finalize", None),
}

# (source, target, optional condition label)
EDGES: list[tuple[str, str, str | None]] = [
    ("supervisor", "curriculum_agent", "analyze_curriculum"),
    ("supervisor", "plan_create", "create_plan"),
    ("supervisor", "plan_modify", "adapt_plan"),
    ("supervisor", "lesson_agent", "generate_lesson"),
    ("supervisor", "quiz_agent", "generate_quiz"),
    ("supervisor", "grading_agent", "quiz_submit"),
    ("supervisor", "recommendation_agent", "generate_recommendation"),
    ("supervisor", "obe_extract", "extract_outline"),
    ("supervisor", "obe_validate", "validate_outline"),
    ("supervisor", "obe_suggest", "suggest_co_mapping"),
    ("supervisor", "obe_summarize", "analyze_outline"),
    ("grading_agent", "performance_agent", None),
    ("performance_agent", "recommendation_agent", None),
    ("recommendation_agent", "plan_modify", "needs remediation"),
    ("recommendation_agent", "finalize", "advance"),
    ("plan_modify", "lesson_agent", "quiz_submit"),
    ("lesson_agent", "quiz_agent", "reassess"),
    ("quiz_agent", "finalize", None),
    ("curriculum_agent", "finalize", None),
    ("plan_create", "finalize", None),
    ("obe_extract", "finalize", None),
    ("obe_validate", "finalize", None),
    ("obe_suggest", "finalize", None),
    ("obe_summarize", "finalize", None),
]

# message action -> node id (to reconstruct the path a run took from its messages)
ACTION_TO_NODE: dict[str, str] = {
    "curriculum.analyze": "curriculum_agent",
    "plan.create": "plan_create",
    "plan.modify": "plan_modify",
    "lesson.generate": "lesson_agent",
    "quiz.generate": "quiz_agent",
    "attempt.grade": "grading_agent",
    "performance.analyze": "performance_agent",
    "recommend.generate": "recommendation_agent",
    "obe.extract": "obe_extract",
    "obe.validate": "obe_validate",
    "obe.suggest_mapping": "obe_suggest",
    "obe.summarize": "obe_summarize",
}


def visited_from_messages(messages: list) -> list[str]:
    """Node ids touched by a run, inferred from its agent messages.

    Each message may be a dict or an ORM row; we read ``action``. The supervisor
    always runs, and any completed pipeline reaches ``finalize``.
    """
    visited: set[str] = {"supervisor"}
    for m in messages:
        action = m.get("action") if isinstance(m, dict) else getattr(m, "action", None)
        node = ACTION_TO_NODE.get(action or "")
        if node:
            visited.add(node)
    if len(visited) > 1:
        visited.add("finalize")
    return sorted(visited)


def to_dot(visited: list[str] | None = None) -> str:
    """Graphviz DOT for the pipeline; ``visited`` nodes are highlighted."""
    hot = set(visited or [])
    lines = [
        "digraph adapted {",
        '  rankdir=LR;',
        '  bgcolor="transparent";',
        '  node [shape=box style="rounded,filled" fontname="Helvetica" '
        'fontsize=11 color="#c6ced9" fillcolor="#eef1f6" fontcolor="#26313f"];',
        '  edge [color="#9aa6b5" fontname="Helvetica" fontsize=9 fontcolor="#77839a"];',
    ]
    for nid, (label, _agent) in NODES.items():
        if nid in hot:
            style = ' fillcolor="#2a4e7c" fontcolor="#ffffff" color="#2a4e7c"'
        elif nid in ("supervisor", "finalize"):
            style = ' fillcolor="#e4ecf6" color="#8fb0dc"'
        else:
            style = ""
        lines.append(f'  "{nid}" [label="{label}"{style}];')
    for src, dst, cond in EDGES:
        both = src in hot and dst in hot
        attrs = []
        if cond:
            attrs.append(f'label="{cond}"')
        if both:
            attrs.append('color="#2a4e7c" penwidth=2')
        a = f' [{", ".join(attrs)}]' if attrs else ""
        lines.append(f'  "{src}" -> "{dst}"{a};')
    lines.append("}")
    return "\n".join(lines)


def as_dicts() -> tuple[list[dict], list[dict]]:
    nodes = [
        {"id": nid, "label": label, "agent": agent, "kind": "agent" if agent else "control"}
        for nid, (label, agent) in NODES.items()
    ]
    edges = [{"source": s, "target": t, "label": c} for s, t, c in EDGES]
    return nodes, edges

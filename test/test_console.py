"""Offline tests for the Agent Console building blocks: token usage/cost and the
execution-graph topology. These are pure (no database), so they always run."""

from __future__ import annotations

from adapted.config import settings
from adapted.graph import topology
from adapted.llm import usage


def test_usage_accumulates():
    usage.start()
    usage.record(100, 40)
    usage.record(prompt=50, completion=10)
    u = usage.current()
    assert u.prompt_tokens == 150
    assert u.completion_tokens == 50
    assert u.total_tokens == 200
    assert u.calls == 2


def test_usage_record_without_start_is_safe():
    # a fresh context has no active counter; record must not raise
    usage._USAGE.set(None)
    usage.record(10, 10)  # no-op
    assert usage.current() is None


def test_estimate_tokens():
    assert usage.estimate_tokens("") == 0
    assert usage.estimate_tokens("a" * 40) == 10


def test_estimate_cost_uses_prices():
    old_in, old_out = settings.llm_price_input_per_1k, settings.llm_price_output_per_1k
    try:
        settings.llm_price_input_per_1k = 0.5
        settings.llm_price_output_per_1k = 1.5
        # 2000 prompt -> 1.0 ; 1000 completion -> 1.5 ; total 2.5
        assert usage.estimate_cost(2000, 1000) == 2.5
        assert usage.estimate_cost(0, 0) == 0.0
    finally:
        settings.llm_price_input_per_1k = old_in
        settings.llm_price_output_per_1k = old_out


def test_topology_shape():
    nodes, edges = topology.as_dicts()
    ids = {n["id"] for n in nodes}
    assert {"supervisor", "grading_agent", "obe_summarize", "finalize"} <= ids
    # every edge connects known nodes
    for e in edges:
        assert e["source"] in ids and e["target"] in ids


def test_topology_dot_renders():
    dot = topology.to_dot(["supervisor", "grading_agent", "performance_agent"])
    assert dot.startswith("digraph")
    assert "grading_agent" in dot
    assert "->" in dot


def test_visited_from_messages():
    msgs = [
        {"action": "attempt.grade"},
        {"action": "performance.analyze"},
        {"action": "recommend.generate"},
    ]
    visited = topology.visited_from_messages(msgs)
    assert "grading_agent" in visited
    assert "performance_agent" in visited
    assert "recommendation_agent" in visited
    assert "supervisor" in visited  # always runs
    assert "finalize" in visited  # a completed run reaches finalize


def test_visited_handles_orm_like_objects():
    class M:
        def __init__(self, action):
            self.action = action

    visited = topology.visited_from_messages([M("obe.summarize")])
    assert "obe_summarize" in visited

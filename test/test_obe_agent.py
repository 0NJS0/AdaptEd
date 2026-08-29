"""Tests for the OBE agent dispatch and the DB-free runner helpers.

These import ``adapted.agents`` / ``adapted.models``, which (per the project's
fail-fast design) require ``DATABASE_URL`` to be importable. The whole module
therefore skips automatically when no database is configured, and runs in full
on any environment that has one — no Postgres data is read or written, since the
OBE agent needs no DB for text input.
"""

from __future__ import annotations

import pytest

try:
    from adapted.agents.message import AgentMessage
    from adapted.agents.obe_agent import OBEAgent
    from adapted.agents.obe_author_agent import OBEAuthorAgent
    from adapted.llm.mock import MockProvider
    from adapted.obe import runner

    _IMPORTABLE = True
    _REASON = ""
except Exception as exc:  # noqa: BLE001 - RuntimeError when DATABASE_URL is unset
    _IMPORTABLE = False
    _REASON = f"agent stack not importable ({type(exc).__name__}: {exc})"

pytestmark = pytest.mark.skipif(not _IMPORTABLE, reason=_REASON)

SAMPLE = (
    "CSC 8888 DEMO SEMESTER: Fall, 2025-2026 3 Credit "
    "By the end of this course, students should be able to: "
    "CO1 Explain the basics. 4 PO-a-1 "
    "CO2 Apply methods. 3 PO-a-1 "
    "CO3 Analyze results. 4 PO-b-1 "
    "CO4 Design a component. 6 PO-b-1 "
    "Topics to be covered in the class Week 1 CO1 Week 2 CO2 Week 3 CO3 Week 4 CO4 "
    "Mapping of PO "
    "PO-a-1 Apply fundamentals. Cognitive Level 3 (Applying) K1 "
    "PO-b-1 Analyse problems. Cognitive Level 4 (Analyzing) K3 "
    "K, P, A Definitions "
)


def _msg(action, payload):
    return AgentMessage(
        task_id="T1", correlation_id="T1", sender="test",
        receiver="obe_agent", action=action, payload=payload,
    )


def _agent():
    return OBEAgent(db=None, provider=MockProvider(), bus=None)


def test_agent_extract():
    out = _agent().handle(_msg("obe.extract", {"outline_text": SAMPLE}))
    assert out.error is None
    assert len(out.output["extraction"]["cos"]) == 4


def test_agent_validate():
    out = _agent().handle(_msg("obe.validate", {"outline_text": SAMPLE}))
    assert out.error is None
    assert "report" in out.output and "findings" in out.output["report"]


def test_agent_summarize():
    out = _agent().handle(_msg("obe.summarize", {"outline_text": SAMPLE}))
    assert out.error is None
    for key in ("extraction", "report", "suggestions", "summary_markdown"):
        assert key in out.output
    assert "CO-PO Mapping Summary" in out.output["summary_markdown"]


def test_agent_suggest():
    out = _agent().handle(
        _msg("obe.suggest_mapping", {"description": "Design a solution for a complex problem."})
    )
    assert out.error is None
    s = out.output["suggestions"][0]
    assert s["suggested_bloom_level"] == 6
    assert "PO-c-1" in s["suggested_pos"]


def test_agent_missing_input_errors():
    out = _agent().handle(_msg("obe.extract", {}))
    assert out.error is not None  # no outline/text/document_id


def test_runner_analyze_text():
    res = runner.analyze_text(SAMPLE, provider=MockProvider())
    assert res["report"]["error_count"] >= 0
    assert len(res["suggestions"]) == 4


def test_runner_suggest():
    res = runner.suggest(description="Apply sorting algorithms.", provider=MockProvider())
    assert res["suggestions"][0]["suggested_bloom_level"] == 3


# --- OBE Authoring agent (second OBE agent) ---
def _author_agent():
    return OBEAuthorAgent(db=None, provider=MockProvider(), bus=None)


def test_author_agent_generates_cos():
    out = _author_agent().handle(
        _msg("obe.author", {"subject": "computer science", "count": 4})
    )
    assert out.error is None
    assert len(out.output["cos"]) == 4


def test_author_agent_improve():
    out = _author_agent().handle(
        _msg("obe.improve", {"description": "Explain the design of a system.", "target_level": 6})
    )
    assert out.error is None
    assert out.output["improved"]["improved_description"].startswith("Design")


def test_author_agent_improve_requires_description():
    out = _author_agent().handle(_msg("obe.improve", {}))
    assert out.error is not None


def test_runner_author_and_improve():
    a = runner.author(subject="math", count=3, provider=MockProvider())
    assert len(a["cos"]) == 3
    b = runner.improve(description="Explain recursion.", target_level=4, provider=MockProvider())
    assert b["improved"]["bloom_level"] == 4

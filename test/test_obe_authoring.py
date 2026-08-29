"""Offline tests for the OBE Authoring agent's domain logic (no database)."""

from __future__ import annotations

from adapted.obe import authoring
from adapted.obe import reference as ref


def test_author_default_spread():
    cos = authoring.author_cos(course_title="Data Structures", subject="computer science")
    assert len(cos) == 4
    levels = [c.bloom_level for c in cos]
    assert levels == [3, 4, 5, 6]  # a real Bloom spread, not all one level
    # every generated verb genuinely matches its declared Bloom level
    for c in cos:
        assert ref.cognitive_level_for_verb(c.verb) == c.bloom_level
        assert c.bloom_name


def test_author_uses_topics():
    cos = authoring.author_cos(topics=["sorting", "trees", "graphs", "complexity"])
    assert "sorting" in cos[0].description.lower()
    assert "complexity" in cos[3].description.lower()


def test_author_count_two():
    cos = authoring.author_cos(count=2)
    assert len(cos) == 2
    assert [c.bloom_level for c in cos] == [3, 4]


def test_author_co6_is_complex_and_carries_p():
    cos = authoring.author_cos(topics=["UML"], count=6)
    co6 = next(c for c in cos if c.bloom_level == 6)
    assert "complex" in co6.description.lower()
    assert "P1" in co6.suggested_kpa.p  # complex-problem outcome gets a P attribute


def test_improve_to_target_level():
    imp = authoring.improve_co(
        "Explain the design of a complex system using UML.", target_level=5
    )
    assert imp.improved_description.startswith("Evaluate")
    assert imp.bloom_level == 5
    assert imp.bloom_name == "Evaluating"
    assert imp.changes
    assert ref.cognitive_level_for_verb(imp.verb) == 5


def test_improve_auto_keeps_level():
    imp = authoring.improve_co("Explain the basics of recursion.")
    assert imp.bloom_level == 2  # "explain" is Understanding
    assert imp.improved_description.startswith("Explain")
    assert imp.changes  # at least a PO suggestion


def test_improve_to_create():
    imp = authoring.improve_co("Explain a solution using algorithms.", target_level=6)
    assert imp.improved_description.startswith("Design")
    assert imp.bloom_level == 6
